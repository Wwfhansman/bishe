from __future__ import annotations

import os
import queue
import threading
import time
from typing import Any, Iterable, Optional

from ..errors import VoiceServiceConfigError, VoiceServiceInitError
from ..schemas import TtsChunk


class PiperOnnxTtsService:
    def __init__(
        self,
        model_path: str,
        config_path: Optional[str] = None,
        sample_rate: int = 22050,
        speaker_id: int = 0,
        length_scale: float = 1.0,
        noise_scale: float = 0.667,
    ):
        self.model_path = model_path
        self.config_path = config_path
        self._sample_rate = int(sample_rate)
        self.speaker_id = int(speaker_id)
        self.length_scale = float(length_scale)
        self.noise_scale = float(noise_scale)

        self._voice = None
        self._initialized = False
        self._last_error: Optional[str] = None

        self._active_stop: Optional[threading.Event] = None
        self._active_thread: Optional[threading.Thread] = None
        self._active_q: Optional[queue.Queue[Optional[bytes]]] = None

        self._synth_calls = 0
        self._bytes_out = 0

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def initialize(self) -> None:
        if self._initialized:
            return
        model_path = os.path.abspath(self.model_path)
        if not os.path.exists(model_path):
            raise VoiceServiceConfigError(f"model_path not found: {model_path}")
        cfg_path = self.config_path
        # Piper library strictly requires the config file to be named <model_path>.json
        # or be in the same directory. Let's ensure we find the right one.
        actual_cfg = None
        possible_configs = []
        if cfg_path:
            possible_configs.append(os.path.abspath(cfg_path))
        
        possible_configs.extend([
            model_path + ".json",
            model_path.replace(".onnx", "") + ".json",
            os.path.join(os.path.dirname(model_path), "voice.json"),
            os.path.join(os.path.dirname(model_path), "voice.onnx.json")
        ])

        for p in possible_configs:
            if os.path.exists(p):
                actual_cfg = p
                break
        
        if not actual_cfg:
            raise VoiceServiceConfigError(f"config_path not found for model: {model_path}")
        
        # Critical: If the file is named 'voice.json', Piper might still fail internally 
        # if it expects 'voice.onnx.json'. We've advised the user to rename it, 
        # but we use the found path here.
        cfg_path = actual_cfg

        try:
            from piper.voice import PiperVoice
        except Exception as e:
            raise VoiceServiceInitError("Missing dependency: piper-tts") from e

        try:
            # Use both model and config for loading if possible
            self._voice = PiperVoice.load(model_path, config_path=cfg_path)
            sr = getattr(getattr(self._voice, "config", None), "sample_rate", None)
            if isinstance(sr, int) and sr > 0:
                self._sample_rate = sr
        except Exception as e:
            self._last_error = str(e)
            raise VoiceServiceInitError(f"Failed to load piper model: {e}") from e
        self._initialized = True

    def close(self) -> None:
        if not self._initialized:
            return
        self.stop()
        self._voice = None
        self._initialized = False

    def health_check(self) -> dict[str, Any]:
        return {
            "type": "piper",
            "initialized": self._initialized,
            "sample_rate": self._sample_rate,
            "last_error": self._last_error,
            "synth_calls": self._synth_calls,
            "bytes_out": self._bytes_out,
        }

    def collect_metrics(self) -> dict[str, Any]:
        return {
            "synth_calls": self._synth_calls,
            "bytes_out": self._bytes_out,
        }

    def stop(self) -> None:
        ev = self._active_stop
        if ev is not None:
            ev.set()
        q = self._active_q
        if q is not None:
            try:
                q.put_nowait(None)
            except Exception:
                pass
        th = self._active_thread
        if th is not None:
            th.join(timeout=0.5)
        self._active_stop = None
        self._active_thread = None
        self._active_q = None

    def synthesize_stream(self, text: str) -> Iterable[TtsChunk]:
        if not self._initialized:
            raise VoiceServiceInitError("TTS service not initialized")
        t = (text or "").strip()
        if not t:
            return []
        self.stop()
        self._synth_calls += 1
        q: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=64)
        stop_evt = threading.Event()
        self._active_stop = stop_evt
        self._active_q = q

        def run() -> None:
            try:
                # print(f"Piper: Starting synthesis for '{t[:20]}...'")
                voice = self._voice
                if voice is None:
                    raise RuntimeError("voice is not loaded")
                
                # PiperVoice uses 'synthesize' to get an iterator of raw bytes
                # IMPORTANT: PiperVoice.synthesize returns bytes in chunks
                sid = self.speaker_id if self.speaker_id > 0 else None
                try:
                    it = voice.synthesize(
                        t,
                        speaker_id=sid,
                        length_scale=self.length_scale,
                        noise_scale=self.noise_scale,
                    )
                except Exception:
                    it = voice.synthesize(t)
                
                chunk_count = 0
                for b in it:
                    if stop_evt.is_set():
                        break
                    if not b:
                        continue
                    try:
                        # Piper-tts (1.2.0+) returns AudioChunk objects when using synthesize()
                        # These have 'audio_int16_bytes' property.
                        data = None
                        if isinstance(b, bytes):
                            data = b
                        elif hasattr(b, "audio_int16_bytes"):
                            data = b.audio_int16_bytes
                        elif hasattr(b, "pcm16_bytes"):
                            data = b.pcm16_bytes
                        else:
                            # Last resort: try to convert to numpy array then to bytes
                            import numpy as np
                            try:
                                data = np.array(b, dtype=np.int16).tobytes()
                            except Exception:
                                # If it's still failing, it might be the AudioChunk object itself
                                # that numpy doesn't know how to handle.
                                data = None
                        
                        if data:
                            q.put(data, timeout=1.0)
                            chunk_count += 1
                        else:
                            print(f"Piper: Could not extract PCM bytes from {type(b)}")
                    except Exception as e:
                        # Log error more specifically
                        print(f"Piper: Queue put failed for type {type(b)}: {e}")
                
                # print(f"Piper: Finished synthesis, sent {chunk_count} chunks")
                try:
                    q.put(None, timeout=1.0)
                except Exception:
                    pass
            except Exception as e:
                print(f"Piper synthesis error: {e}")
                self._last_error = str(e)
                try:
                    q.put_nowait(None)
                except Exception:
                    pass

        th = threading.Thread(target=run, daemon=True)
        self._active_thread = th
        th.start()

        def gen() -> Iterable[TtsChunk]:
            while True:
                if stop_evt.is_set():
                    break
                try:
                    b = q.get(timeout=0.2)
                except queue.Empty:
                    continue
                if b is None:
                    break
                self._bytes_out += len(b)
                yield TtsChunk(pcm16_bytes=b, sample_rate=self._sample_rate, is_final=False)
            yield TtsChunk(pcm16_bytes=b"", sample_rate=self._sample_rate, is_final=True)

        return gen()

