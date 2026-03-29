import asyncio
import json
import queue
import re
import threading
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

try:
    import webrtcvad as _webrtcvad
except Exception:
    _webrtcvad = None

from .. import database
from ..config import (
    GREETING_TEXT,
    LLM_SYSTEM_PROMPT,
    RATE as ASR_RATE,
)
from ..llm.llm_client import LLMClient
from ..voice import (
    AdaptiveBargeInDetector,
    AudioChunk,
    BargeInEventKind,
    SpeechState,
    StreamingNoiseSuppressor,
    create_stt_service,
    create_tts_service,
    load_voice_registry,
)


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
        self.reply_q: queue.Queue[Optional[ReplyTask]] = queue.Queue(maxsize=4)
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
        self.last_tts_start_time = 0.0

        self.perf_asr_partial_ts: Optional[float] = None
        self.perf_asr_final_ts: Optional[float] = None
        self.perf_llm_start_ts: Optional[float] = None
        self.perf_llm_end_ts: Optional[float] = None
        self.perf_rag_ms: Optional[float] = None
        self.perf_tts_start_ts: Optional[float] = None
        self.perf_tts_first_chunk_ts: Optional[float] = None
        self.perf_tts_end_ts: Optional[float] = None

        self.barge_in_detector = AdaptiveBargeInDetector(sample_rate=ASR_RATE)
        self.barge_in = self.barge_in_detector.state
        self.frame_bytes = self.barge_in_detector.frame_bytes
        self.noise_suppressor = StreamingNoiseSuppressor(sample_rate=ASR_RATE)
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
            self._enqueue_reply_task(ReplyTask(kind="greeting", text=GREETING_TEXT))

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

    def _enqueue_reply_task(self, task: ReplyTask) -> None:
        try:
            self.reply_q.put_nowait(task)
            return
        except queue.Full:
            pass

        retained: list[Optional[ReplyTask]] = []
        while True:
            try:
                queued = self.reply_q.get_nowait()
            except queue.Empty:
                break
            if queued is None or queued.kind == "greeting":
                retained.append(queued)
        for item in retained:
            try:
                self.reply_q.put_nowait(item)
            except queue.Full:
                break
        try:
            self.reply_q.put_nowait(task)
        except queue.Full:
            pass

    def _normalize_text(self, text: str) -> str:
        try:
            return re.sub(r"[\s，。！？,.!?:;；]+", "", text).lower()
        except Exception:
            return text

    def _energy_is_speech(self, frame: bytes) -> bool:
        return self.barge_in_detector.energy_is_speech(frame)

    def _frame_energy(self, frame: bytes) -> float:
        return self.barge_in_detector.frame_energy(frame)

    def _update_noise_floor(self, energy: float, is_speech: bool) -> None:
        self.barge_in_detector.update_noise_floor(energy, is_speech)

    def _append_speech_flag(self, is_speech: bool) -> float:
        return self.barge_in_detector.append_speech_flag(is_speech)

    def _echo_risk(self) -> float:
        return self.barge_in_detector.echo_risk(
            last_tts_chunk_time=self.last_tts_chunk_time,
            last_tts_end_time=self.last_tts_end_time,
        )

    def _barge_in_score(self, is_speech: bool, energy: float, speech_ratio: float, echo_risk: float) -> float:
        return self.barge_in_detector.score(is_speech, energy, speech_ratio, echo_risk)

    def _confirm_frames_required(self, score: float) -> int:
        return self.barge_in_detector.confirm_frames_required(score)

    def _interrupt_now(self, force: bool = False) -> None:
        if not force and self.barge_in.speech_state != SpeechState.SPEAKING:
            return
        self.send_enabled = False
        self._clear_out_audio_q()
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._send_text_obj({"event": "tts_reset"}),
                self.loop,
            )
        self.barge_in.speech_state = SpeechState.INTERRUPT_PENDING

    def _confirm_interrupt(self, force: bool = False) -> None:
        if not force and self.barge_in.speech_state == SpeechState.INTERRUPTED:
            return
        self.barge_in.speech_state = SpeechState.INTERRUPTED
        try:
            if self.tts is not None:
                self.tts.stop()
        except Exception:
            pass
        self._clear_out_audio_q()
        self.last_tts_end_time = time.time()
        self.last_tts_chunk_time = self.last_tts_end_time
        self.last_tts_start_time = 0.0
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._send_text_obj(
                    {
                        "event": "barge_in",
                        "speech_state": self.barge_in.speech_state.value,
                        "score": round(self.barge_in.last_score, 3),
                        "speech_ratio": round(self.barge_in.last_speech_ratio, 3),
                        "echo_risk": round(self.barge_in.last_echo_risk, 3),
                        "noise_floor": round(self.barge_in.noise_floor, 2),
                        "peak_gate": round(self.barge_in.last_peak_gate, 2),
                        "peak_frames": self.barge_in.peak_frames,
                        "max_peak_run": self.barge_in.max_peak_run,
                        "ts": time.time(),
                    }
                ),
                self.loop,
            )
            asyncio.run_coroutine_threadsafe(
                self._send_text_obj({"event": "tts_interrupted"}),
                self.loop,
            )

    def _resume_play(self) -> None:
        self.send_enabled = True
        self.barge_in_detector.reset_runtime(speech_state=SpeechState.SPEAKING)

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
        self.barge_in_detector.reset_runtime(speech_state=SpeechState.IDLE)
        self.last_tts_end_time = time.time()
        self.last_tts_chunk_time = self.last_tts_end_time
        self.last_tts_start_time = 0.0
        self.send_enabled = True

    def _reply_worker(self) -> None:
        # LLM requests and TTS synthesis are intentionally kept off the event loop.
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
        key_norm = self._normalize_text(text)
        # Only deduplicate assistant greetings; user repeats should still be processed.
        if text.strip() == GREETING_TEXT.strip():
            ts_prev = self.last_seen.get(key_norm)
            if ts_prev is not None and (time.time() - ts_prev) < self.cooldown_sec:
                return
            self.last_seen[key_norm] = time.time()

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
                self.barge_in_detector.reset_runtime(speech_state=SpeechState.SPEAKING)
                self.last_tts_start_time = time.time()
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
                interrupted_early = False
                self.send_enabled = True
                for chunk in self.tts.synthesize_stream(text):
                    if not self.send_enabled:
                        interrupted_early = True
                        break
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
                self.last_tts_start_time = 0.0
                self.barge_in_detector.reset_runtime(speech_state=SpeechState.IDLE)
                with self.perf_lock:
                    self.perf_tts_end_ts = time.perf_counter()
                if self.loop is not None and not interrupted_early:
                    asyncio.run_coroutine_threadsafe(
                        self._send_text_obj({"event": "tts_done", "count": count}),
                        self.loop,
                    )
            except Exception as e:
                self.barge_in_detector.reset_runtime(speech_state=SpeechState.IDLE)
                self.last_tts_end_time = time.time()
                self.last_tts_start_time = 0.0
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
                            if (
                                self.last_tts_start_time > 0
                                and self.barge_in.speech_state in {SpeechState.SPEAKING, SpeechState.INTERRUPT_PENDING}
                            ):
                                self._interrupt_now(force=True)
                                self._confirm_interrupt(force=True)
                            with self.perf_lock:
                                self.perf_asr_final_ts = time.perf_counter()
                            await self._send_text_obj({"event": "asr_text", "text": result.text})
                            self._enqueue_reply_task(ReplyTask(kind="reply", text=result.text))
                        else:
                            if (
                                self.last_tts_start_time > 0
                                and self.barge_in.speech_state in {SpeechState.SPEAKING, SpeechState.INTERRUPT_PENDING}
                                and len(result.text.strip()) >= 2
                            ):
                                self._interrupt_now(force=True)
                                self._confirm_interrupt(force=True)
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
                if not self.send_enabled:
                    self._clear_out_audio_q()
                    continue
                await self.websocket.send_bytes(chunk)
        except WebSocketDisconnect:
            return
        except Exception:
            return

    def _handle_barge_in(self, audio_bytes: bytes) -> None:
        def detect_speech(frame: bytes) -> bool:
            try:
                if self.use_native_vad and self.vad is not None:
                    return bool(self.vad.is_speech(frame, ASR_RATE))
                return self._energy_is_speech(frame)
            except Exception:
                return False

        events = self.barge_in_detector.process_audio(
            audio_bytes=audio_bytes,
            detect_speech=detect_speech,
            last_tts_chunk_time=self.last_tts_chunk_time,
            last_tts_end_time=self.last_tts_end_time,
            tts_start_time=self.last_tts_start_time,
        )
        for event in events:
            if event.kind == BargeInEventKind.PENDING:
                self._interrupt_now(force=True)
            elif event.kind == BargeInEventKind.CONFIRMED:
                self._confirm_interrupt(force=True)
            elif event.kind == BargeInEventKind.RESUMED:
                self._resume_play()

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

        if data.get("cmd") == "interrupt":
            self._interrupt_now(force=True)
            self._confirm_interrupt(force=True)
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
                    "peak_gate": round(self.barge_in.last_peak_gate, 2),
                    "peak_frames": self.barge_in.peak_frames,
                    "max_peak_run": self.barge_in.max_peak_run,
                    "pending_tts_elapsed_ms": round(self.barge_in.pending_tts_elapsed_ms, 2) if self.barge_in.pending_tts_elapsed_ms is not None else None,
                    "late_window_ms": self.barge_in.late_window_ms,
                }
            )
            return

        if data.get("cmd") == "noise_suppression_config":
            changed = self.noise_suppressor.update_config(
                enabled=data.get("enable"),
                noise_floor=data.get("noise_floor"),
                noise_alpha=data.get("noise_alpha"),
                spectral_alpha=data.get("spectral_alpha"),
                min_gain=data.get("min_gain"),
                over_subtraction=data.get("over_subtraction"),
                speech_margin=data.get("speech_margin"),
            )
            if data.get("reset") is True:
                self.noise_suppressor.reset()
                changed = True
            await self._send_text_obj(
                {
                    "event": "noise_suppression_config_ok",
                    "changed": changed,
                    "noise_suppression": self.noise_suppressor.collect_metrics(),
                }
            )
            return

        if data.get("cmd") == "noise_suppression_status":
            await self._send_text_obj(
                {
                    "event": "noise_suppression_status",
                    "noise_suppression": self.noise_suppressor.collect_metrics(),
                }
            )
            return

    async def _receive_loop(self) -> None:
        while True:
            msg = await self.websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("type") != "websocket.receive":
                continue
            if msg.get("bytes") is not None:
                audio_bytes = msg["bytes"]
                processed_audio = self.noise_suppressor.process(audio_bytes)
                self.recv_bytes += len(audio_bytes)
                self.recv_chunks += 1
                if self.recv_chunks % 10 == 0:
                    await self._send_text_obj(
                        {
                            "event": "audio_stats",
                            "chunks": self.recv_chunks,
                            "bytes": self.recv_bytes,
                            "noise_suppression": self.noise_suppressor.collect_metrics(),
                        }
                    )
                if not processed_audio:
                    continue
                self._handle_barge_in(processed_audio)
                try:
                    if self.stt is None:
                        raise RuntimeError("STT not initialized")
                    self.stt.accept_audio(
                        AudioChunk(pcm16_bytes=processed_audio, sample_rate=ASR_RATE, channels=1)
                    )
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
        self.noise_suppressor.reset()
