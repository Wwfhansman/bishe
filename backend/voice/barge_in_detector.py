from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import numpy as np

from ..config import (
    BARGE_IN_ADAPTIVE_ENERGY_MARGIN,
    BARGE_IN_CONFIRM_SCORE,
    BARGE_IN_ECHO_SUPPRESSION_WINDOW_MS,
    BARGE_IN_ENABLED,
    BARGE_IN_FALLBACK_SENSITIVITY,
    BARGE_IN_FRAME_MS,
    BARGE_IN_LATE_PEAK_MIN_FRAMES,
    BARGE_IN_LATE_PLATEAU_LIMIT,
    BARGE_IN_LATE_WINDOW_MS,
    BARGE_IN_MIN_SPEECH_MS,
    BARGE_IN_NOISE_FLOOR,
    BARGE_IN_NOISE_FLOOR_ALPHA,
    BARGE_IN_PENDING_SCORE,
    BARGE_IN_PEAK_GATE_MIN,
    BARGE_IN_PEAK_GATE_SCALE,
    BARGE_IN_PEAK_MIN_FRAMES,
    BARGE_IN_PEAK_PLATEAU_LIMIT,
    BARGE_IN_SILENCE_END_FRAMES,
    BARGE_IN_SILENCE_RESET_FRAMES,
    BARGE_IN_SPEECH_RATIO_WINDOW,
    BARGE_IN_START_FRAMES,
    BARGE_IN_TTS_COOLDOWN_MS,
)


class SpeechState(str, Enum):
    IDLE = "idle"
    SPEAKING = "speaking"
    INTERRUPT_PENDING = "interrupt_pending"
    INTERRUPTED = "interrupted"


class BargeInEventKind(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    RESUMED = "resumed"


@dataclass(frozen=True)
class BargeInEvent:
    kind: BargeInEventKind
    score: float
    speech_ratio: float
    echo_risk: float
    noise_floor: float
    energy: float


@dataclass
class BargeInState:
    enabled: bool = BARGE_IN_ENABLED
    min_speech_ms: int = BARGE_IN_MIN_SPEECH_MS
    start_frames: int = BARGE_IN_START_FRAMES
    silence_end_frames: int = BARGE_IN_SILENCE_END_FRAMES
    silence_reset_frames: int = BARGE_IN_SILENCE_RESET_FRAMES
    frame_ms: int = BARGE_IN_FRAME_MS
    fallback_sensitivity: int = BARGE_IN_FALLBACK_SENSITIVITY
    noise_floor: float = BARGE_IN_NOISE_FLOOR
    noise_floor_alpha: float = BARGE_IN_NOISE_FLOOR_ALPHA
    adaptive_energy_margin: float = BARGE_IN_ADAPTIVE_ENERGY_MARGIN
    pending_score: float = BARGE_IN_PENDING_SCORE
    confirm_score: float = BARGE_IN_CONFIRM_SCORE
    tts_cooldown_ms: int = BARGE_IN_TTS_COOLDOWN_MS
    echo_suppression_window_ms: int = BARGE_IN_ECHO_SUPPRESSION_WINDOW_MS
    speech_ratio_window: int = BARGE_IN_SPEECH_RATIO_WINDOW
    peak_gate_min: float = BARGE_IN_PEAK_GATE_MIN
    peak_gate_scale: float = BARGE_IN_PEAK_GATE_SCALE
    peak_min_frames: int = BARGE_IN_PEAK_MIN_FRAMES
    peak_plateau_limit: int = BARGE_IN_PEAK_PLATEAU_LIMIT
    late_window_ms: int = BARGE_IN_LATE_WINDOW_MS
    late_peak_min_frames: int = BARGE_IN_LATE_PEAK_MIN_FRAMES
    late_plateau_limit: int = BARGE_IN_LATE_PLATEAU_LIMIT
    speaking_frames: int = 0
    silence_frames: int = 0
    speech_state: SpeechState = SpeechState.IDLE
    vad_buf: bytes = b""
    recent_speech_flags: deque[int] = field(default_factory=deque)
    last_frame_energy: float = 0.0
    last_score: float = 0.0
    last_speech_ratio: float = 0.0
    last_echo_risk: float = 0.0
    last_peak_gate: float = 0.0
    peak_frames: int = 0
    peak_run: int = 0
    max_peak_run: int = 0
    pending_tts_elapsed_ms: float | None = None


class AdaptiveBargeInDetector:
    def __init__(self, state: BargeInState | None = None, sample_rate: int = 16000):
        self.state = state or BargeInState()
        self.sample_rate = int(sample_rate)
        self.frame_bytes = int(self.sample_rate * self.state.frame_ms / 1000) * 2

    def reset_runtime(self, speech_state: SpeechState | None = None) -> None:
        if speech_state is not None:
            self.state.speech_state = speech_state
        self.state.speaking_frames = 0
        self.state.silence_frames = 0
        self.state.vad_buf = b""
        self.state.recent_speech_flags.clear()
        self.state.peak_frames = 0
        self.state.peak_run = 0
        self.state.max_peak_run = 0
        self.state.pending_tts_elapsed_ms = None

    def frame_energy(self, frame: bytes) -> float:
        samples = np.frombuffer(frame, dtype=np.int16)
        if samples.size == 0:
            return 0.0
        return float(np.mean(np.abs(samples)))

    def energy_is_speech(self, frame: bytes) -> bool:
        energy = self.frame_energy(frame)
        threshold = (
            6.0 if self.state.fallback_sensitivity == 0
            else 5.0 if self.state.fallback_sensitivity == 1
            else 4.0 if self.state.fallback_sensitivity == 2
            else 3.0
        )
        return energy > self.state.noise_floor * threshold

    def update_noise_floor(self, energy: float, is_speech: bool) -> None:
        alpha = self.state.noise_floor_alpha
        if is_speech:
            alpha *= 0.25
        if self.state.speech_state == SpeechState.SPEAKING:
            alpha *= 0.5
        self.state.noise_floor = self.state.noise_floor * (1.0 - alpha) + energy * alpha
        self.state.noise_floor = max(50.0, self.state.noise_floor)

    def append_speech_flag(self, is_speech: bool) -> float:
        self.state.recent_speech_flags.append(1 if is_speech else 0)
        while len(self.state.recent_speech_flags) > self.state.speech_ratio_window:
            self.state.recent_speech_flags.popleft()
        if not self.state.recent_speech_flags:
            return 0.0
        return sum(self.state.recent_speech_flags) / len(self.state.recent_speech_flags)

    def echo_risk(
        self,
        last_tts_chunk_time: float,
        last_tts_end_time: float,
        now: float | None = None,
    ) -> float:
        if self.state.speech_state == SpeechState.IDLE and last_tts_chunk_time <= 0:
            return 0.0
        current_time = time.time() if now is None else now
        elapsed_ms = (current_time - max(last_tts_chunk_time, last_tts_end_time)) * 1000
        if elapsed_ms <= 0:
            return 1.0
        if elapsed_ms >= self.state.echo_suppression_window_ms:
            return 0.0
        return 1.0 - (elapsed_ms / self.state.echo_suppression_window_ms)

    def score(
        self,
        is_speech: bool,
        energy: float,
        speech_ratio: float,
        echo_risk: float,
    ) -> float:
        noise_floor = max(self.state.noise_floor, 1.0)
        energy_gain = max(0.0, (energy - noise_floor) / noise_floor)
        energy_score = min(1.5, energy_gain / max(self.state.adaptive_energy_margin, 0.05))
        vad_score = 0.8 if is_speech else 0.0
        ratio_score = min(1.0, speech_ratio * 1.2)
        echo_penalty = echo_risk * 0.9
        score = vad_score + energy_score + ratio_score - echo_penalty
        return max(0.0, score)

    def confirm_frames_required(self, score: float) -> int:
        base_frames = max(1, self.state.min_speech_ms // self.state.frame_ms)
        if score >= self.state.confirm_score + 0.75:
            return max(1, base_frames // 3)
        if score >= self.state.confirm_score + 0.35:
            return max(1, base_frames // 2)
        return base_frames

    def process_audio(
        self,
        audio_bytes: bytes,
        detect_speech: Callable[[bytes], bool],
        last_tts_chunk_time: float,
        last_tts_end_time: float,
        tts_start_time: float | None = None,
        now: float | None = None,
    ) -> list[BargeInEvent]:
        if not self.state.enabled:
            return []

        current_time = time.time() if now is None else now
        in_cooldown = (
            last_tts_end_time > 0
            and (current_time - last_tts_end_time) * 1000 < self.state.tts_cooldown_ms
        )
        if in_cooldown:
            return []

        events: list[BargeInEvent] = []
        self.state.vad_buf += audio_bytes
        while len(self.state.vad_buf) >= self.frame_bytes:
            frame = self.state.vad_buf[: self.frame_bytes]
            self.state.vad_buf = self.state.vad_buf[self.frame_bytes :]
            try:
                is_speech = bool(detect_speech(frame))
            except Exception:
                is_speech = False

            energy = self.frame_energy(frame)
            speech_ratio = self.append_speech_flag(is_speech)
            echo_risk = self.echo_risk(
                last_tts_chunk_time=last_tts_chunk_time,
                last_tts_end_time=last_tts_end_time,
                now=current_time,
            )
            score = self.score(
                is_speech=is_speech,
                energy=energy,
                speech_ratio=speech_ratio,
                echo_risk=echo_risk,
            )

            self.state.last_frame_energy = energy
            self.state.last_speech_ratio = speech_ratio
            self.state.last_echo_risk = echo_risk
            self.state.last_score = score
            peak_gate = max(
                self.state.peak_gate_min,
                self.state.noise_floor * self.state.peak_gate_scale,
            )
            self.state.last_peak_gate = peak_gate
            high_peak = energy >= peak_gate

            if is_speech:
                self.state.speaking_frames += 1
                self.state.silence_frames = 0
                if high_peak:
                    self.state.peak_frames += 1
                    self.state.peak_run += 1
                    self.state.max_peak_run = max(self.state.max_peak_run, self.state.peak_run)
                else:
                    self.state.peak_run = 0
                if (
                    self.state.speech_state == SpeechState.SPEAKING
                    and self.state.speaking_frames >= self.state.start_frames
                    and score >= self.state.pending_score
                ):
                    self.state.speech_state = SpeechState.INTERRUPT_PENDING
                    if tts_start_time and tts_start_time > 0:
                        self.state.pending_tts_elapsed_ms = (current_time - tts_start_time) * 1000.0
                    else:
                        self.state.pending_tts_elapsed_ms = None
                    events.append(
                        BargeInEvent(
                            kind=BargeInEventKind.PENDING,
                            score=score,
                            speech_ratio=speech_ratio,
                            echo_risk=echo_risk,
                            noise_floor=self.state.noise_floor,
                            energy=energy,
                        )
                    )

                if self.state.speech_state == SpeechState.INTERRUPT_PENDING:
                    confirm_frames = self.confirm_frames_required(score)
                    required_peak_frames = self.state.peak_min_frames
                    allowed_peak_run = self.state.peak_plateau_limit
                    if (
                        self.state.pending_tts_elapsed_ms is not None
                        and self.state.pending_tts_elapsed_ms > self.state.late_window_ms
                    ):
                        required_peak_frames = max(
                            required_peak_frames,
                            self.state.late_peak_min_frames,
                        )
                        allowed_peak_run = min(
                            allowed_peak_run,
                            self.state.late_plateau_limit,
                        )
                    if (
                        self.state.speaking_frames >= confirm_frames
                        and score >= self.state.confirm_score
                        and self.state.peak_frames >= required_peak_frames
                        and self.state.max_peak_run <= allowed_peak_run
                    ):
                        self.state.speech_state = SpeechState.INTERRUPTED
                        events.append(
                            BargeInEvent(
                                kind=BargeInEventKind.CONFIRMED,
                                score=score,
                                speech_ratio=speech_ratio,
                                echo_risk=echo_risk,
                                noise_floor=self.state.noise_floor,
                                energy=energy,
                            )
                        )
            else:
                self.state.silence_frames += 1
                self.state.peak_run = 0
                if self.state.silence_frames > self.state.silence_reset_frames:
                    self.state.speaking_frames = 0
                    self.state.peak_frames = 0
                    self.state.max_peak_run = 0
                if (
                    self.state.speech_state == SpeechState.INTERRUPT_PENDING
                    and self.state.silence_frames >= self.state.silence_end_frames
                ):
                    self.reset_runtime(speech_state=SpeechState.SPEAKING)
                    events.append(
                        BargeInEvent(
                            kind=BargeInEventKind.RESUMED,
                            score=score,
                            speech_ratio=speech_ratio,
                            echo_risk=echo_risk,
                            noise_floor=self.state.noise_floor,
                            energy=energy,
                        )
                    )

            self.update_noise_floor(energy, is_speech)

        return events
