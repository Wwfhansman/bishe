from __future__ import annotations

import os
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ..errors import VoiceServiceConfigError, VoiceServiceInitError
from ..schemas import AudioChunk, SttResult


@dataclass(frozen=True)
class EndpointConfig:
    enabled: bool = True
    rule1_min_trailing_silence: float = 0.8
    rule2_min_trailing_silence: float = 1.2
    rule3_min_utterance_length: float = 200


def _pick_single_file(model_dir: str, patterns: list[str], key: str) -> str:
    import glob

    matches: list[str] = []
    for p in patterns:
        matches.extend(glob.glob(os.path.join(model_dir, p)))
    matches = sorted(set(matches))
    if not matches:
        raise VoiceServiceConfigError(f"No {key} file found in {model_dir}")

    # If multiple files found (e.g. regular and .int8), pick the first one
    # but prefer non-int8 if available
    if len(matches) > 1:
        non_int8 = [f for f in matches if ".int8." not in f]
        if non_int8:
            return non_int8[0]
    return matches[0]


class SherpaOnnxSttService:
    def __init__(
        self,
        model_dir: str,
        sample_rate: int = 16000,
        num_threads: int = 4,
        provider: str = "cpu",
        decoding_method: str = "greedy_search",
        max_active_paths: int = 4,
        endpoint: Optional[dict[str, Any]] = None,
        encoder: Optional[str] = None,
        decoder: Optional[str] = None,
        joiner: Optional[str] = None,
        tokens: Optional[str] = None,
    ):
        self.model_dir = model_dir
        self.sample_rate = int(sample_rate)
        self.num_threads = int(num_threads)
        self.provider = provider
        self.decoding_method = decoding_method
        self.max_active_paths = int(max_active_paths)
        self.endpoint = EndpointConfig(**endpoint) if isinstance(endpoint, dict) else EndpointConfig()
        self.encoder = encoder
        self.decoder = decoder
        self.joiner = joiner
        self.tokens = tokens

        self._rec = None
        self._stream = None
        self._audio_q: queue.Queue[Optional[AudioChunk]] = queue.Queue(maxsize=32)
        self._result_q: queue.Queue[SttResult] = queue.Queue()
        self._stop_evt = threading.Event()
        self._th: Optional[threading.Thread] = None

        self._last_partial: str = ""
        self._initialized = False
        self._last_error: Optional[str] = None
        self._accepted_chunks = 0
        self._decoded_chunks = 0

    def initialize(self) -> None:
        if self._initialized:
            return
        try:
            import sherpa_onnx
        except Exception as e:
            raise VoiceServiceInitError("Missing dependency: sherpa-onnx") from e

        model_dir = os.path.abspath(self.model_dir)
        if not os.path.isdir(model_dir):
            raise VoiceServiceConfigError(f"model_dir not found: {model_dir}")

        encoder = self.encoder or _pick_single_file(model_dir, ["encoder*.onnx"], "encoder")
        decoder = self.decoder or _pick_single_file(model_dir, ["decoder*.onnx"], "decoder")
        joiner = self.joiner or _pick_single_file(model_dir, ["joiner*.onnx"], "joiner")
        tokens = self.tokens or _pick_single_file(model_dir, ["tokens.txt", "token*.txt"], "tokens")

        kwargs: dict[str, Any] = dict(
            encoder=encoder,
            decoder=decoder,
            joiner=joiner,
            tokens=tokens,
            num_threads=self.num_threads,
            provider=self.provider,
            sample_rate=self.sample_rate,
            decoding_method=self.decoding_method,
            max_active_paths=self.max_active_paths,
        )
        if self.endpoint.enabled:
            kwargs.update(
                dict(
                    enable_endpoint_detection=True,
                    rule1_min_trailing_silence=float(self.endpoint.rule1_min_trailing_silence),
                    rule2_min_trailing_silence=float(self.endpoint.rule2_min_trailing_silence),
                    rule3_min_utterance_length=float(self.endpoint.rule3_min_utterance_length),
                )
            )
        else:
            kwargs.update(dict(enable_endpoint_detection=False))

        try:
            self._rec = sherpa_onnx.OnlineRecognizer.from_transducer(**kwargs)
            self._stream = self._rec.create_stream()
        except Exception as e:
            self._last_error = str(e)
            raise VoiceServiceInitError(f"Failed to initialize sherpa-onnx recognizer: {e}") from e

        self._stop_evt.clear()
        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()
        self._initialized = True

    def close(self) -> None:
        if not self._initialized:
            return
        self._stop_evt.set()
        try:
            self._audio_q.put_nowait(None)
        except Exception:
            pass
        if self._th:
            self._th.join(timeout=1.0)
        self._th = None
        self._rec = None
        self._stream = None
        self._initialized = False

    def reset(self) -> None:
        if not self._initialized:
            return
        self._last_partial = ""
        try:
            self._rec.reset(self._stream)
        except Exception:
            try:
                self._stream = self._rec.create_stream()
            except Exception:
                pass

    def accept_audio(self, chunk: AudioChunk) -> None:
        if not self._initialized:
            raise VoiceServiceInitError("STT service not initialized")
        self._accepted_chunks += 1
        try:
            self._audio_q.put_nowait(chunk)
        except queue.Full:
            pass

    def poll_result(self) -> list[SttResult]:
        out: list[SttResult] = []
        while True:
            try:
                out.append(self._result_q.get_nowait())
            except queue.Empty:
                break
        return out

    def health_check(self) -> dict[str, Any]:
        return {
            "type": "sherpa_onnx",
            "initialized": self._initialized,
            "last_error": self._last_error,
            "accepted_chunks": self._accepted_chunks,
            "decoded_chunks": self._decoded_chunks,
        }

    def collect_metrics(self) -> dict[str, Any]:
        return {
            "accepted_chunks": self._accepted_chunks,
            "decoded_chunks": self._decoded_chunks,
        }

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                chunk = self._audio_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if chunk is None:
                break
            try:
                pcm = np.frombuffer(chunk.pcm16_bytes, dtype=np.int16).astype(np.float32)
                if pcm.size == 0:
                    continue
                pcm *= 1.0 / 32768.0
                self._stream.accept_waveform(chunk.sample_rate, pcm)
                self._decoded_chunks += 1
                while self._rec.is_ready(self._stream):
                    self._rec.decode_stream(self._stream)
                
                # Check for result immediately after decode
                # Update: Use a more frequent check for partials
                txt = self._rec.get_result(self._stream)
                if isinstance(txt, str):
                    t = txt.strip()
                else:
                    t = ""
                
                # If we have a non-empty result, or it changed, put it
                if t and t != self._last_partial:
                    self._last_partial = t
                    self._result_q.put(SttResult(text=t, is_final=False))
                    # Log for debugging
                    # print(f"STT Partial: {t}")
                is_endpoint = False
                try:
                    is_endpoint = bool(self._rec.is_endpoint(self._stream))
                except Exception:
                    is_endpoint = False
                if is_endpoint:
                    final_text = (self._rec.get_result(self._stream) or "").strip()
                    if final_text:
                        print(f"STT Endpoint detected: {final_text}") # 新增日志
                        self._result_q.put(SttResult(text=final_text, is_final=True))
                    try:
                        self._rec.reset(self._stream)
                    except Exception:
                        try:
                            self._stream = self._rec.create_stream()
                        except Exception:
                            pass
                    self._last_partial = ""
            except Exception as e:
                self._last_error = str(e)
                time.sleep(0.05)

