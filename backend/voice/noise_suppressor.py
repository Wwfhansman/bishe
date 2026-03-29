from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ..config import (
    NOISE_SUPPRESSION_ENABLED,
    NOISE_SUPPRESSION_FRAME_MS,
    NOISE_SUPPRESSION_MIN_GAIN,
    NOISE_SUPPRESSION_NOISE_ALPHA,
    NOISE_SUPPRESSION_NOISE_FLOOR,
    NOISE_SUPPRESSION_OVER_SUBTRACTION,
    NOISE_SUPPRESSION_SPEECH_MARGIN,
    NOISE_SUPPRESSION_SPECTRAL_ALPHA,
)


@dataclass
class NoiseSuppressorState:
    enabled: bool = NOISE_SUPPRESSION_ENABLED
    frame_ms: int = NOISE_SUPPRESSION_FRAME_MS
    noise_floor: float = NOISE_SUPPRESSION_NOISE_FLOOR
    noise_alpha: float = NOISE_SUPPRESSION_NOISE_ALPHA
    spectral_alpha: float = NOISE_SUPPRESSION_SPECTRAL_ALPHA
    min_gain: float = NOISE_SUPPRESSION_MIN_GAIN
    over_subtraction: float = NOISE_SUPPRESSION_OVER_SUBTRACTION
    speech_margin: float = NOISE_SUPPRESSION_SPEECH_MARGIN
    last_input_energy: float = 0.0
    last_output_energy: float = 0.0
    last_gain_mean: float = 1.0
    processed_frames: int = 0


class StreamingNoiseSuppressor:
    def __init__(self, state: Optional[NoiseSuppressorState] = None, sample_rate: int = 16000):
        self.state = state or NoiseSuppressorState()
        self.sample_rate = int(sample_rate)
        self.frame_bytes = int(self.sample_rate * self.state.frame_ms / 1000) * 2
        self._buf = b""
        self._noise_mag: Optional[np.ndarray] = None
        self._analysis_window = np.hanning(max(2, self.frame_bytes // 2)).astype(np.float32)
        self._crossfade_samples = max(1, (self.frame_bytes // 2) // 4)
        self._prev_tail: Optional[np.ndarray] = None

    def reset(self) -> None:
        self._buf = b""
        self._noise_mag = None
        self._prev_tail = None
        self.state.last_input_energy = 0.0
        self.state.last_output_energy = 0.0
        self.state.last_gain_mean = 1.0
        self.state.processed_frames = 0

    def update_config(self, **kwargs: Any) -> bool:
        changed = False
        validators = {
            "enabled": lambda v: isinstance(v, bool),
            "noise_floor": lambda v: isinstance(v, (int, float)) and v > 0,
            "noise_alpha": lambda v: isinstance(v, (int, float)) and 0 < float(v) < 1,
            "spectral_alpha": lambda v: isinstance(v, (int, float)) and 0 < float(v) < 1,
            "min_gain": lambda v: isinstance(v, (int, float)) and 0 < float(v) <= 1,
            "over_subtraction": lambda v: isinstance(v, (int, float)) and float(v) > 0,
            "speech_margin": lambda v: isinstance(v, (int, float)) and float(v) > 0,
        }
        for key, value in kwargs.items():
            validate = validators.get(key)
            if validate is None or not validate(value):
                continue
            normalized = value
            if key != "enabled":
                normalized = float(value)
            if getattr(self.state, key) != normalized:
                setattr(self.state, key, normalized)
                changed = True
        if changed:
            self._buf = b""
            self._prev_tail = None
        return changed

    def frame_energy(self, frame: bytes) -> float:
        samples = np.frombuffer(frame, dtype=np.int16)
        if samples.size == 0:
            return 0.0
        return float(np.mean(np.abs(samples)))

    def _update_noise_floor(self, energy: float, speech_like: bool) -> None:
        alpha = self.state.noise_alpha
        if speech_like:
            alpha *= 0.2
        self.state.noise_floor = self.state.noise_floor * (1.0 - alpha) + energy * alpha
        self.state.noise_floor = max(50.0, self.state.noise_floor)

    def _update_noise_mag(self, mag: np.ndarray, speech_like: bool) -> None:
        alpha = self.state.spectral_alpha
        if self._noise_mag is None:
            self._noise_mag = mag.astype(np.float32, copy=True)
            return
        if speech_like:
            alpha *= 0.1
        self._noise_mag = (1.0 - alpha) * self._noise_mag + alpha * mag

    def _process_frame(self, frame: bytes) -> bytes:
        if not self.state.enabled:
            self.state.last_input_energy = self.frame_energy(frame)
            self.state.last_output_energy = self.state.last_input_energy
            self.state.last_gain_mean = 1.0
            self.state.processed_frames += 1
            return frame

        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
        if samples.size == 0:
            return frame

        input_energy = float(np.mean(np.abs(samples)))
        speech_like = input_energy > self.state.noise_floor * self.state.speech_margin

        if self._analysis_window.size != samples.size:
            self._analysis_window = np.hanning(max(2, samples.size)).astype(np.float32)
            self._crossfade_samples = max(1, samples.size // 4)
        windowed = samples * self._analysis_window

        spectrum = np.fft.rfft(windowed)
        magnitude = np.abs(spectrum).astype(np.float32)
        phase = np.angle(spectrum)
        self._update_noise_mag(magnitude, speech_like)
        noise_mag = magnitude if self._noise_mag is None else self._noise_mag

        denom = np.maximum(magnitude, 1e-6)
        raw_gain = 1.0 - self.state.over_subtraction * (noise_mag / denom)
        gain = np.clip(raw_gain, self.state.min_gain, 1.0)
        enhanced_mag = magnitude * gain
        enhanced = np.fft.irfft(enhanced_mag * np.exp(1j * phase), n=samples.size)
        enhanced = enhanced / np.maximum(self._analysis_window, 0.08)
        if self._prev_tail is not None and self._prev_tail.size == self._crossfade_samples:
            fade = np.linspace(0.0, 1.0, self._crossfade_samples, dtype=np.float32)
            enhanced[: self._crossfade_samples] = (
                self._prev_tail * (1.0 - fade) + enhanced[: self._crossfade_samples] * fade
            )
        self._prev_tail = enhanced[-self._crossfade_samples :].astype(np.float32, copy=True)
        enhanced = np.clip(np.round(enhanced), -32768, 32767).astype(np.int16)

        output_energy = float(np.mean(np.abs(enhanced.astype(np.float32))))
        self.state.last_input_energy = input_energy
        self.state.last_output_energy = output_energy
        self.state.last_gain_mean = float(np.mean(gain)) if gain.size else 1.0
        self.state.processed_frames += 1
        self._update_noise_floor(input_energy, speech_like)
        return enhanced.tobytes()

    def process(self, audio_bytes: bytes) -> bytes:
        if not audio_bytes:
            return b""
        if not self.state.enabled:
            self.state.last_input_energy = self.frame_energy(audio_bytes)
            self.state.last_output_energy = self.state.last_input_energy
            self.state.last_gain_mean = 1.0
            return audio_bytes
        self._buf += audio_bytes
        out = bytearray()
        while len(self._buf) >= self.frame_bytes:
            frame = self._buf[: self.frame_bytes]
            self._buf = self._buf[self.frame_bytes :]
            out.extend(self._process_frame(frame))
        return bytes(out)

    def flush(self) -> bytes:
        if not self._buf:
            return b""
        padding = b"\x00" * (self.frame_bytes - len(self._buf))
        frame = self._buf + padding
        self._buf = b""
        processed = self._process_frame(frame)
        return processed[: len(frame) - len(padding)]

    def collect_metrics(self) -> dict[str, float | int | bool]:
        return {
            "enabled": self.state.enabled,
            "noise_floor": round(self.state.noise_floor, 2),
            "noise_alpha": round(self.state.noise_alpha, 4),
            "spectral_alpha": round(self.state.spectral_alpha, 4),
            "min_gain": round(self.state.min_gain, 4),
            "over_subtraction": round(self.state.over_subtraction, 4),
            "speech_margin": round(self.state.speech_margin, 4),
            "last_input_energy": round(self.state.last_input_energy, 2),
            "last_output_energy": round(self.state.last_output_energy, 2),
            "last_gain_mean": round(self.state.last_gain_mean, 4),
            "processed_frames": self.state.processed_frames,
        }
