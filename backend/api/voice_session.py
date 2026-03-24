import asyncio
import json
import queue
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

try:
    import webrtcvad as _webrtcvad
except Exception:
    _webrtcvad = None

from .. import database
from ..config import (
    BARGE_IN_ADAPTIVE_ENERGY_MARGIN,
    BARGE_IN_CONFIRM_SCORE,
    BARGE_IN_ECHO_SUPPRESSION_WINDOW_MS,
    BARGE_IN_ENABLED,
    BARGE_IN_FALLBACK_SENSITIVITY,
    BARGE_IN_FRAME_MS,
    BARGE_IN_MIN_SPEECH_MS,
    BARGE_IN_NOISE_FLOOR,
    BARGE_IN_NOISE_FLOOR_ALPHA,
    BARGE_IN_PENDING_SCORE,
    BARGE_IN_SILENCE_END_FRAMES,
    BARGE_IN_SILENCE_RESET_FRAMES,
    BARGE_IN_SPEECH_RATIO_WINDOW,
    BARGE_IN_START_FRAMES,
    BARGE_IN_TTS_COOLDOWN_MS,
    GREETING_TEXT,
    LLM_SYSTEM_PROMPT,
    RATE as ASR_RATE,
)
from ..llm.llm_client import LLMClient
from ..voice import AudioChunk, create_stt_service, create_tts_service, load_voice_registry


class SpeechState(str, Enum):
    IDLE = "idle"
    SPEAKING = "speaking"
    INTERRUPT_PENDING = "interrupt_pending"
    INTERRUPTED = "interrupted"


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
    speaking_frames: int = 0
    silence_frames: int = 0
    speech_state: SpeechState = SpeechState.IDLE
    vad_buf: bytes = b""
    recent_speech_flags: deque[int] = field(default_factory=deque)
    last_frame_energy: float = 0.0
    last_score: float = 0.0
    last_speech_ratio: float = 0.0
    last_echo_risk: float = 0.0


@dataclass
class ReplyTask:
    kind: str
    text: str


class VoiceSessionRunner:
    def __init__(self, websocket: WebSocket, session_id: str):
        self.websocket = websocket
        self.session_id = session_id
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        self.registry = None
        self.stt = None
        self.tts = None
        self.llm = LLMClient()

        self.out_audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=64)
        self.reply_q: queue.Queue[Optional[ReplyTask]] = queue.Queue()
        self.reply_stop_evt = threading.Event()
        self.reply_thread: Optional[threading.Thread] = None
        self.tts_lock = threading.Lock()
        self.perf_lock = threading.Lock()

        self.send_enabled = True
        self.recv_bytes = 0
        self.recv_chunks = 0
        self.history = database.get_session_history(session_id, limit=10)
        self.last_seen: dict[str, float] = {}
        self.cooldown_sec = 5.0
        self.last_tts_end_time = 0.0
        self.last_tts_chunk_time = 0.0

        self.perf_asr_partial_ts: Optional[float] = None
        self.perf_asr_final_ts: Optional[float] = None
        self.perf_llm_start_ts: Optional[float] = None
        self.perf_llm_end_ts: Optional[float] = None
        self.perf_rag_ms: Optional[float] = None
        self.perf_tts_start_ts: Optional[float] = None
        self.perf_tts_first_chunk_ts: Optional[float] = None
        self.perf_tts_end_ts: Optional[float] = None

        self.barge_in = BargeInState()
        self.frame_bytes = int(ASR_RATE * self.barge_in.frame_ms / 1000) * 2
        self.use_native_vad = _webrtcvad is not None
        self.vad = _webrtcvad.Vad(3) if self.use_native_vad else None

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        print(f"Loaded history for session {self.session_id}: {len(self.history)} messages")

        if not await self._initialize_voice_services():
            return

        self.reply_thread = threading.Thread(target=self._reply_worker, daemon=True)
        self.reply_thread.start()

        if len(self.history) == 0:
            self.reply_q.put(ReplyTask(kind="greeting", text=GREETING_TEXT))

        await self._send_text_obj({"event": "tts_ready"})

        poll_task = asyncio.create_task(self._poll_stt())
        send_task = asyncio.create_task(self._sender())
        try:
            await self._receive_loop()
        except WebSocketDisconnect:
            pass
        except Exception as e:
            await self._send_text_obj({"event": "error", "stage": "ws_loop", "detail": str(e)})
        finally:
            await self._shutdown(poll_task, send_task)

    async def _initialize_voice_services(self) -> bool:
        try:
            self.registry = load_voice_registry()
            self.stt = create_stt_service(self.registry)
            self.tts = create_tts_service(self.registry)
            self.stt.initialize()
            self.tts.initialize()
            await self._send_text_obj({"event": "asr_connected"})
            return True
        except Exception as e:
            await self._send_text_obj({"event": "voice_init_error", "detail": str(e)})
            try:
                await self.websocket.close(code=1011)
            except Exception:
                pass
            return False

    async def _send_text_obj(self, obj: dict) -> None:
        try:
            await self.websocket.send_text(json.dumps(obj, ensure_ascii=False))
        except Exception:
            pass

    def _enqueue_audio_chunk(self, chunk: bytes) -> None:
        try:
            self.out_audio_q.put_nowait(chunk)
        except asyncio.QueueFull:
            try:
                self.out_audio_q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self.out_audio_q.put_nowait(chunk)
            except asyncio.QueueFull:
                pass

    def _put_audio(self, chunk: bytes) -> None:
        if self.send_enabled and self.loop is not None:
            self.loop.call_soon_threadsafe(self._enqueue_audio_chunk, chunk)

    def _clear_out_audio_q(self) -> None:
        while True:
            try:
                self.out_audio_q.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _normalize_text(self, text: str) -> str:
        try:
            return re.sub(r"[\s，。！？,.!?:;；]+", "", text).lower()
        except Exception:
            return text

    def _energy_is_speech(self, frame: bytes) -> bool:
        energy = self._frame_energy(frame)
        threshold = (
            6.0 if self.barge_in.fallback_sensitivity == 0
            else 5.0 if self.barge_in.fallback_sensitivity == 1
            else 4.0 if self.barge_in.fallback_sensitivity == 2
            else 3.0
        )
        return energy > self.barge_in.noise_floor * threshold

    def _frame_energy(self, frame: bytes) -> float:
        samples = np.frombuffer(frame, dtype=np.int16)
        if samples.size == 0:
            return 0.0
        return float(np.mean(np.abs(samples)))

    def _update_noise_floor(self, energy: float, is_speech: bool) -> None:
        alpha = self.barge_in.noise_floor_alpha
        if is_speech:
            alpha *= 0.25
        if self.barge_in.speech_state == SpeechState.SPEAKING:
            alpha *= 0.5
        self.barge_in.noise_floor = (
            self.barge_in.noise_floor * (1.0 - alpha) + energy * alpha
        )
        self.barge_in.noise_floor = max(50.0, self.barge_in.noise_floor)

    def _append_speech_flag(self, is_speech: bool) -> float:
        self.barge_in.recent_speech_flags.append(1 if is_speech else 0)
        while len(self.barge_in.recent_speech_flags) > self.barge_in.speech_ratio_window:
            self.barge_in.recent_speech_flags.popleft()
        if not self.barge_in.recent_speech_flags:
            return 0.0
        return sum(self.barge_in.recent_speech_flags) / len(self.barge_in.recent_speech_flags)

    def _echo_risk(self) -> float:
        if self.barge_in.speech_state == SpeechState.IDLE and self.last_tts_chunk_time <= 0:
            return 0.0
        elapsed_ms = (time.time() - max(self.last_tts_chunk_time, self.last_tts_end_time)) * 1000
        if elapsed_ms <= 0:
            return 1.0
        if elapsed_ms >= self.barge_in.echo_suppression_window_ms:
            return 0.0
        return 1.0 - (elapsed_ms / self.barge_in.echo_suppression_window_ms)

    def _barge_in_score(self, is_speech: bool, energy: float, speech_ratio: float, echo_risk: float) -> float:
        noise_floor = max(self.barge_in.noise_floor, 1.0)
        energy_gain = max(0.0, (energy - noise_floor) / noise_floor)
        energy_score = min(1.5, energy_gain / max(self.barge_in.adaptive_energy_margin, 0.05))
        vad_score = 0.8 if is_speech else 0.0
        ratio_score = min(1.0, speech_ratio * 1.2)
        echo_penalty = echo_risk * 0.9
        score = vad_score + energy_score + ratio_score - echo_penalty
        return max(0.0, score)

    def _confirm_frames_required(self, score: float) -> int:
        base_frames = max(1, self.barge_in.min_speech_ms // self.barge_in.frame_ms)
        if score >= self.barge_in.confirm_score + 0.75:
            return max(1, base_frames // 3)
        if score >= self.barge_in.confirm_score + 0.35:
            return max(1, base_frames // 2)
        return base_frames

    def _interrupt_now(self) -> None:
        if self.barge_in.speech_state != SpeechState.SPEAKING:
            return
        self.send_enabled = False
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._send_text_obj({"event": "tts_reset"}),
                self.loop,
            )
        self.barge_in.speech_state = SpeechState.INTERRUPT_PENDING

    def _confirm_interrupt(self) -> None:
        self.barge_in.speech_state = SpeechState.INTERRUPTED
        try:
            if self.tts is not None:
                self.tts.stop()
        except Exception:
            pass
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._send_text_obj({"event": "tts_interrupted"}),
                self.loop,
            )

    def _resume_play(self) -> None:
        self.send_enabled = True
        self.barge_in.speech_state = SpeechState.SPEAKING
        self.barge_in.speaking_frames = 0
        self.barge_in.silence_frames = 0
        self.barge_in.vad_buf = b""
        self.barge_in.recent_speech_flags.clear()

    def _stop_current_tts(self) -> None:
        self.send_enabled = False
        self._clear_out_audio_q()
        try:
            if self.tts is not None:
                self.tts.stop()
        except Exception:
            pass
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._send_text_obj({"event": "tts_reset"}),
                self.loop,
            )
        self.barge_in.speech_state = SpeechState.IDLE
        self.barge_in.speaking_frames = 0
        self.barge_in.silence_frames = 0
        self.barge_in.vad_buf = b""
        self.barge_in.recent_speech_flags.clear()
        self.last_tts_end_time = time.time()
        self.last_tts_chunk_time = self.last_tts_end_time
        self.send_enabled = True

    def _reply_worker(self) -> None:
        while not self.reply_stop_evt.is_set():
            try:
                task = self.reply_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if task is None:
                break
            try:
                if task.kind == "greeting":
                    self._play_greeting(task.text)
                else:
                    self._handle_reply(task.text)
            except Exception as e:
                print(f"Reply worker error: {e}")

    def _handle_reply(self, text: str) -> None:
        now = time.time()
        if now - self.last_tts_end_time < 1.5:
            return

        key_norm = self._normalize_text(text)
        ts_prev = self.last_seen.get(key_norm)
        if ts_prev is not None and (now - ts_prev) < self.cooldown_sec:
            return
        self.last_seen[key_norm] = now

        database.add_message(self.session_id, "user", text)
        self.history.append({"role": "user", "content": text})

        reply = text
        try:
            rag_t0 = time.perf_counter()
            rag_text = self._build_rag_context(text)
            rag_ms = (time.perf_counter() - rag_t0) * 1000.0
            with self.perf_lock:
                self.perf_rag_ms = rag_ms
                self.perf_llm_start_ts = time.perf_counter()
            sys_prompt = LLM_SYSTEM_PROMPT if not rag_text else LLM_SYSTEM_PROMPT + "\n" + rag_text
            recent_hist = self.history[-7:-1] if len(self.history) > 6 else self.history[:-1]
            reply = self.llm.chat(text, system=sys_prompt, history=recent_hist)
            with self.perf_lock:
                self.perf_llm_end_ts = time.perf_counter()
            if self.loop is not None:
                asyncio.run_coroutine_threadsafe(
                    self._send_text_obj({"event": "llm_text", "text": reply}),
                    self.loop,
                )
            database.add_message(self.session_id, "assistant", reply)
            self.history.append({"role": "assistant", "content": reply})
            self.last_seen[self._normalize_text(reply)] = time.time()
        except Exception as e:
            if self.loop is not None:
                asyncio.run_coroutine_threadsafe(
                    self._send_text_obj(
                        {"event": "llm_error", "fallback_text": reply, "detail": str(e)}
                    ),
                    self.loop,
                )

        self._speak_text(reply)
        self._emit_perf_metrics()

    def _build_rag_context(self, text: str) -> Optional[str]:
        try:
            from ..rag.retriever import best_text
        except Exception:
            return None
        if len(text) <= 3 or any(greet in text.lower() for greet in ["你好", "喂", "在吗"]):
            return None
        try:
            return best_text(text, 6, 1200)
        except Exception as e:
            print(f"RAG search error: {e}")
            return None

    def _speak_text(self, text: str) -> None:
        with self.tts_lock:
            try:
                with self.perf_lock:
                    self.perf_tts_start_ts = time.perf_counter()
                    self.perf_tts_first_chunk_ts = None
                self.barge_in.speech_state = SpeechState.SPEAKING
                self.barge_in.speaking_frames = 0
                self.barge_in.silence_frames = 0
                self.barge_in.vad_buf = b""
                self.barge_in.recent_speech_flags.clear()
                if self.tts is None:
                    raise RuntimeError("TTS not initialized")
                try:
                    self.tts.stop()
                    self._clear_out_audio_q()
                except Exception:
                    pass
                if self.loop is not None:
                    asyncio.run_coroutine_threadsafe(
                        self._send_text_obj({"event": "tts_start", "rate": self.tts.sample_rate}),
                        self.loop,
                    )
                count = 0
                self.send_enabled = True
                for chunk in self.tts.synthesize_stream(text):
                    if getattr(chunk, "is_final", False):
                        break
                    data = getattr(chunk, "pcm16_bytes", b"")
                    if not data:
                        continue
                    count += 1
                    self.last_tts_chunk_time = time.time()
                    with self.perf_lock:
                        if self.perf_tts_first_chunk_ts is None:
                            self.perf_tts_first_chunk_ts = time.perf_counter()
                    self._put_audio(data)
                    if count % 5 == 0 and self.loop is not None:
                        asyncio.run_coroutine_threadsafe(
                            self._send_text_obj({"event": "tts_chunk", "count": count}),
                            self.loop,
                        )
                self.last_tts_end_time = time.time()
                self.last_tts_chunk_time = self.last_tts_end_time
                self.barge_in.speech_state = SpeechState.IDLE
                with self.perf_lock:
                    self.perf_tts_end_ts = time.perf_counter()
                if self.loop is not None:
                    asyncio.run_coroutine_threadsafe(
                        self._send_text_obj({"event": "tts_done", "count": count}),
                        self.loop,
                    )
            except Exception as e:
                self.barge_in.speech_state = SpeechState.IDLE
                self.last_tts_end_time = time.time()
                with self.perf_lock:
                    self.perf_tts_end_ts = time.perf_counter()
                if self.loop is not None:
                    asyncio.run_coroutine_threadsafe(
                        self._send_text_obj({"event": "error", "stage": "tts", "detail": str(e)}),
                        self.loop,
                    )

    def _emit_perf_metrics(self) -> None:
        with self.perf_lock:
            asr_partial_ms = None
            asr_final_ms = None
            if self.perf_asr_partial_ts and self.perf_asr_final_ts:
                asr_partial_ms = (self.perf_asr_final_ts - self.perf_asr_partial_ts) * 1000.0
            if self.perf_asr_final_ts and self.perf_tts_end_ts:
                asr_final_ms = (self.perf_tts_end_ts - self.perf_asr_final_ts) * 1000.0

            llm_ms = None
            if self.perf_llm_start_ts and self.perf_llm_end_ts:
                llm_ms = (self.perf_llm_end_ts - self.perf_llm_start_ts) * 1000.0

            tts_first_chunk_ms = None
            if self.perf_tts_start_ts and self.perf_tts_first_chunk_ts:
                tts_first_chunk_ms = (self.perf_tts_first_chunk_ts - self.perf_tts_start_ts) * 1000.0

            tts_ms = None
            if self.perf_tts_start_ts and self.perf_tts_end_ts:
                tts_ms = (self.perf_tts_end_ts - self.perf_tts_start_ts) * 1000.0

            metrics = {
                "rag_ms": round(self.perf_rag_ms, 2) if self.perf_rag_ms is not None else None,
                "llm_ms": round(llm_ms, 2) if llm_ms is not None else None,
                "tts_first_chunk_ms": round(tts_first_chunk_ms, 2) if tts_first_chunk_ms is not None else None,
                "tts_ms": round(tts_ms, 2) if tts_ms is not None else None,
                "asr_partial_to_final_ms": round(asr_partial_ms, 2) if asr_partial_ms is not None else None,
                "asr_final_to_tts_end_ms": round(asr_final_ms, 2) if asr_final_ms is not None else None,
                "speech_state": self.barge_in.speech_state.value,
            }

            self.perf_asr_partial_ts = None
            self.perf_asr_final_ts = None
            self.perf_llm_start_ts = None
            self.perf_llm_end_ts = None
            self.perf_rag_ms = None
            self.perf_tts_start_ts = None
            self.perf_tts_first_chunk_ts = None
            self.perf_tts_end_ts = None

        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._send_text_obj({"event": "perf", "metrics": metrics}),
                self.loop,
            )

    def _play_greeting(self, text: str) -> None:
        try:
            database.add_message(self.session_id, "assistant", text)
            self.history.append({"role": "assistant", "content": text})
            self._speak_text(text)
        except Exception as e:
            if self.loop is not None:
                asyncio.run_coroutine_threadsafe(
                    self._send_text_obj({"event": "error", "stage": "greeting", "detail": str(e)}),
                    self.loop,
                )

    async def _poll_stt(self) -> None:
        try:
            while True:
                if self.stt is not None:
                    results = self.stt.poll_result()
                    for result in results:
                        if not isinstance(result.text, str) or not result.text.strip():
                            continue
                        if result.is_final:
                            with self.perf_lock:
                                self.perf_asr_final_ts = time.perf_counter()
                            await self._send_text_obj({"event": "asr_text", "text": result.text})
                            self.reply_q.put(ReplyTask(kind="reply", text=result.text))
                        else:
                            with self.perf_lock:
                                if self.perf_asr_partial_ts is None:
                                    self.perf_asr_partial_ts = time.perf_counter()
                            await self._send_text_obj({"event": "asr_partial", "text": result.text})
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"STT poll error: {e}")

    async def _sender(self) -> None:
        try:
            while True:
                chunk = await self.out_audio_q.get()
                if self.send_enabled:
                    await self.websocket.send_bytes(chunk)
        except WebSocketDisconnect:
            return
        except Exception:
            return

    def _handle_barge_in(self, audio_bytes: bytes) -> None:
        if not self.barge_in.enabled:
            return
        in_cooldown = (
            self.last_tts_end_time > 0
            and (time.time() - self.last_tts_end_time) * 1000 < self.barge_in.tts_cooldown_ms
        )
        if in_cooldown:
            return

        self.barge_in.vad_buf += audio_bytes
        while len(self.barge_in.vad_buf) >= self.frame_bytes:
            frame = self.barge_in.vad_buf[:self.frame_bytes]
            self.barge_in.vad_buf = self.barge_in.vad_buf[self.frame_bytes:]
            try:
                is_speech = self.vad.is_speech(frame, ASR_RATE) if self.use_native_vad else self._energy_is_speech(frame)
            except Exception:
                is_speech = False
            energy = self._frame_energy(frame)
            speech_ratio = self._append_speech_flag(is_speech)
            echo_risk = self._echo_risk()
            score = self._barge_in_score(is_speech, energy, speech_ratio, echo_risk)
            self.barge_in.last_frame_energy = energy
            self.barge_in.last_speech_ratio = speech_ratio
            self.barge_in.last_echo_risk = echo_risk
            self.barge_in.last_score = score

            if is_speech:
                self.barge_in.speaking_frames += 1
                self.barge_in.silence_frames = 0
                if (
                    self.barge_in.speech_state == SpeechState.SPEAKING
                    and self.barge_in.speaking_frames >= self.barge_in.start_frames
                    and score >= self.barge_in.pending_score
                ):
                    self._interrupt_now()
                if self.barge_in.speech_state == SpeechState.INTERRUPT_PENDING:
                    confirm_frames = self._confirm_frames_required(score)
                    if self.barge_in.speaking_frames >= confirm_frames and score >= self.barge_in.confirm_score:
                        self._confirm_interrupt()
            else:
                self.barge_in.silence_frames += 1
                if self.barge_in.silence_frames > self.barge_in.silence_reset_frames:
                    self.barge_in.speaking_frames = 0
                if (
                    self.barge_in.speech_state == SpeechState.INTERRUPT_PENDING
                    and self.barge_in.silence_frames >= self.barge_in.silence_end_frames
                ):
                    self._resume_play()
            self._update_noise_floor(energy, is_speech)

    async def _handle_text_command(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except Exception:
            return

        if data.get("cmd") == "stop":
            if self.stt is not None:
                self.stt.reset()
            self._stop_current_tts()
            return

        if data.get("cmd") == "interrupt_config":
            enable = data.get("enable")
            sensitivity = data.get("sensitivity")
            min_speech_ms = data.get("min_speech_ms")
            adaptive_energy_margin = data.get("adaptive_energy_margin")
            pending_score = data.get("pending_score")
            confirm_score = data.get("confirm_score")
            noise_floor_alpha = data.get("noise_floor_alpha")
            echo_window_ms = data.get("echo_suppression_window_ms")
            if isinstance(enable, bool):
                self.barge_in.enabled = enable
            if isinstance(sensitivity, int) and 0 <= sensitivity <= 3:
                if self.use_native_vad and self.vad is not None:
                    try:
                        self.vad.set_mode(sensitivity)
                    except Exception:
                        pass
                else:
                    self.barge_in.fallback_sensitivity = sensitivity
            if isinstance(min_speech_ms, int) and min_speech_ms > 0:
                self.barge_in.min_speech_ms = min_speech_ms
            if isinstance(adaptive_energy_margin, (int, float)) and adaptive_energy_margin > 0:
                self.barge_in.adaptive_energy_margin = float(adaptive_energy_margin)
            if isinstance(pending_score, (int, float)) and pending_score > 0:
                self.barge_in.pending_score = float(pending_score)
            if isinstance(confirm_score, (int, float)) and confirm_score > 0:
                self.barge_in.confirm_score = float(confirm_score)
            if isinstance(noise_floor_alpha, (int, float)) and 0 < noise_floor_alpha < 1:
                self.barge_in.noise_floor_alpha = float(noise_floor_alpha)
            if isinstance(echo_window_ms, int) and echo_window_ms > 0:
                self.barge_in.echo_suppression_window_ms = echo_window_ms
            await self._send_text_obj({"event": "interrupt_config_ok"})
            return

        if data.get("cmd") == "interrupt_status":
            await self._send_text_obj(
                {
                    "event": "interrupt_status",
                    "enable": self.barge_in.enabled,
                    "min_speech_ms": self.barge_in.min_speech_ms,
                    "pausepending": self.barge_in.speech_state == SpeechState.INTERRUPT_PENDING,
                    "confirmed": self.barge_in.speech_state == SpeechState.INTERRUPTED,
                    "speech_state": self.barge_in.speech_state.value,
                    "send_enabled": self.send_enabled,
                    "noise_floor": round(self.barge_in.noise_floor, 2),
                    "last_score": round(self.barge_in.last_score, 3),
                    "speech_ratio": round(self.barge_in.last_speech_ratio, 3),
                    "echo_risk": round(self.barge_in.last_echo_risk, 3),
                }
            )

    async def _receive_loop(self) -> None:
        while True:
            msg = await self.websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("type") != "websocket.receive":
                continue
            if msg.get("bytes") is not None:
                audio_bytes = msg["bytes"]
                self._handle_barge_in(audio_bytes)
                self.recv_bytes += len(audio_bytes)
                self.recv_chunks += 1
                if self.recv_chunks % 10 == 0:
                    await self._send_text_obj({"event": "audio_stats", "chunks": self.recv_chunks, "bytes": self.recv_bytes})
                try:
                    if self.stt is None:
                        raise RuntimeError("STT not initialized")
                    self.stt.accept_audio(AudioChunk(pcm16_bytes=audio_bytes, sample_rate=ASR_RATE, channels=1))
                except Exception as e:
                    await self._send_text_obj({"event": "error", "stage": "asr_send", "detail": str(e)})
                    break
            elif msg.get("text") is not None:
                await self._handle_text_command(msg["text"])

    async def _shutdown(self, poll_task: asyncio.Task, send_task: asyncio.Task) -> None:
        self.reply_stop_evt.set()
        try:
            self.reply_q.put_nowait(None)
        except Exception:
            pass
        try:
            await self.websocket.close()
        except Exception:
            pass
        poll_task.cancel()
        send_task.cancel()
        if self.reply_thread is not None and self.reply_thread.is_alive():
            self.reply_thread.join(timeout=1.0)
        try:
            if self.stt is not None:
                self.stt.close()
        except Exception:
            pass
        try:
            if self.tts is not None:
                self.tts.close()
        except Exception:
            pass
