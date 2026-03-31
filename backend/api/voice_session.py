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
    BARGE_IN_PRE_ROLL_MS,
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

        self.out_audio_q: asyncio.Queue[tuple[int, bytes]] = asyncio.Queue(maxsize=64)
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
        self._next_assistant_turn_id = 0
        self._active_assistant_turn_id: Optional[int] = None
        self._turn_start_buf = b""
        self._turn_start_speech_frames = 0
        self._suppressed_partial: Optional[tuple[str, float]] = None
        self._suppressed_final: Optional[tuple[str, float]] = None
        self._last_forwarded_asr_final_norm = ""
        self._last_forwarded_asr_final_ts = 0.0
        self._pre_roll_pcm = bytearray()
        self._pre_roll_max_bytes = max(0, int(ASR_RATE * 2 * BARGE_IN_PRE_ROLL_MS / 1000))
        self._interrupt_collecting = False
        self._pre_roll_seeded = False
        self._skip_direct_stt_once = False

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

    def _enqueue_audio_chunk(self, turn_id: int, chunk: bytes) -> None:
        try:
            self.out_audio_q.put_nowait((turn_id, chunk))
        except asyncio.QueueFull:
            try:
                self.out_audio_q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self.out_audio_q.put_nowait((turn_id, chunk))
            except asyncio.QueueFull:
                pass

    def _put_audio(self, turn_id: int, chunk: bytes) -> None:
        if self.send_enabled and self.loop is not None and self._active_assistant_turn_id == turn_id:
            self.loop.call_soon_threadsafe(self._enqueue_audio_chunk, turn_id, chunk)

    def _clear_out_audio_q(self) -> None:
        while True:
            try:
                self.out_audio_q.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _reset_turn_start_gate(self) -> None:
        self._turn_start_buf = b""
        self._turn_start_speech_frames = 0

    def _reset_suppressed_asr(self) -> None:
        self._suppressed_partial = None
        self._suppressed_final = None

    def _reset_interrupt_collection(self) -> None:
        self._interrupt_collecting = False
        self._pre_roll_seeded = False
        self._skip_direct_stt_once = False

    def _append_pre_roll(self, audio_bytes: bytes) -> None:
        if self._pre_roll_max_bytes <= 0 or not audio_bytes:
            return
        self._pre_roll_pcm.extend(audio_bytes)
        overflow = len(self._pre_roll_pcm) - self._pre_roll_max_bytes
        if overflow > 0:
            del self._pre_roll_pcm[:overflow]

    def _get_pre_roll_bytes(self) -> bytes:
        if not self._pre_roll_pcm:
            return b""
        return bytes(self._pre_roll_pcm)

    def _feed_stt_audio(self, audio_bytes: bytes) -> None:
        if not audio_bytes or self.stt is None:
            return
        chunk_bytes = max(self.frame_bytes, 640)
        for offset in range(0, len(audio_bytes), chunk_bytes):
            part = audio_bytes[offset : offset + chunk_bytes]
            if not part:
                continue
            self.stt.accept_audio(
                AudioChunk(pcm16_bytes=part, sample_rate=ASR_RATE, channels=1)
            )

    def _start_interrupt_collection(self, trigger_kind: str) -> None:
        if self._interrupt_collecting:
            return
        self._interrupt_collecting = True
        self._pre_roll_seeded = False
        self._skip_direct_stt_once = True
        self._reset_suppressed_asr()
        self._interrupt_now(force=True, hard_stop=True)
        if self.stt is not None:
            try:
                self.stt.reset()
            except Exception:
                pass
            pre_roll = self._get_pre_roll_bytes()
            if pre_roll:
                self._feed_stt_audio(pre_roll)
                self._pre_roll_seeded = True
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._send_text_obj(
                    {
                        "event": "early_trigger",
                        "kind": trigger_kind,
                        "pre_roll_bytes": len(self._pre_roll_pcm),
                        "assistant_turn_id": self._active_assistant_turn_id,
                        "ts": time.time(),
                    }
                ),
                self.loop,
            )

    def _begin_assistant_turn(self) -> int:
        self._next_assistant_turn_id += 1
        turn_id = self._next_assistant_turn_id
        self._active_assistant_turn_id = turn_id
        self.send_enabled = True
        self._reset_turn_start_gate()
        self._reset_suppressed_asr()
        self._reset_interrupt_collection()
        self.barge_in_detector.reset_runtime(speech_state=SpeechState.SPEAKING)
        self.last_tts_start_time = time.time()
        return turn_id

    def _finish_assistant_turn(self, turn_id: int, interrupted: bool = False) -> bool:
        if self._active_assistant_turn_id != turn_id:
            return False
        self.last_tts_end_time = time.time()
        self.last_tts_chunk_time = self.last_tts_end_time
        self.last_tts_start_time = 0.0
        self._active_assistant_turn_id = None
        self._reset_turn_start_gate()
        if interrupted:
            self.barge_in_detector.reset_runtime(speech_state=SpeechState.INTERRUPTED)
            self.send_enabled = False
        else:
            self.barge_in_detector.reset_runtime(speech_state=SpeechState.IDLE)
            self._reset_suppressed_asr()
            self._reset_interrupt_collection()
        return True

    def _should_skip_final_text(self, text: str) -> bool:
        now = time.time()
        norm = self._normalize_text(text)
        if norm and norm == self._last_forwarded_asr_final_norm and (now - self._last_forwarded_asr_final_ts) < 2.0:
            return True
        self._last_forwarded_asr_final_norm = norm
        self._last_forwarded_asr_final_ts = now
        return False

    async def _forward_final_text(self, text: str) -> None:
        if self._should_skip_final_text(text):
            return
        self._reset_interrupt_collection()
        with self.perf_lock:
            self.perf_asr_final_ts = time.perf_counter()
        await self._send_text_obj({"event": "asr_text", "text": text})
        self._enqueue_reply_task(ReplyTask(kind="reply", text=text))

    async def _flush_suppressed_final_if_any(self) -> None:
        if not self._suppressed_final:
            return
        text, ts = self._suppressed_final
        self._reset_suppressed_asr()
        if not text.strip() or (time.time() - ts) > 2.0:
            return
        await self._forward_final_text(text)

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

    def _interrupt_now(self, force: bool = False, hard_stop: bool = False) -> None:
        if not force and self.barge_in.speech_state != SpeechState.SPEAKING:
            return
        turn_id = self._active_assistant_turn_id
        self.send_enabled = False
        self._clear_out_audio_q()
        if hard_stop:
            try:
                if self.tts is not None:
                    self.tts.stop()
            except Exception:
                pass
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._send_text_obj({"event": "tts_reset", "assistant_turn_id": turn_id}),
                self.loop,
            )
        self.barge_in.speech_state = SpeechState.INTERRUPT_PENDING

    def _confirm_interrupt(self, force: bool = False) -> None:
        if not force and self.barge_in.speech_state == SpeechState.INTERRUPTED:
            return
        turn_id = self._active_assistant_turn_id
        self.barge_in.speech_state = SpeechState.INTERRUPTED
        try:
            if self.tts is not None:
                self.tts.stop()
        except Exception:
            pass
        self._clear_out_audio_q()
        self._finish_assistant_turn(turn_id or -1, interrupted=True)
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._send_text_obj(
                    {
                        "event": "barge_in",
                        "assistant_turn_id": turn_id,
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
                self._send_text_obj({"event": "tts_interrupted", "assistant_turn_id": turn_id}),
                self.loop,
            )
            asyncio.run_coroutine_threadsafe(self._flush_suppressed_final_if_any(), self.loop)

    def _resume_play(self) -> None:
        self.send_enabled = True
        self._reset_interrupt_collection()
        self.barge_in_detector.reset_runtime(speech_state=SpeechState.SPEAKING)

    def _stop_current_tts(self) -> None:
        turn_id = self._active_assistant_turn_id
        self.send_enabled = False
        self._clear_out_audio_q()
        try:
            if self.tts is not None:
                self.tts.stop()
        except Exception:
            pass
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._send_text_obj({"event": "tts_reset", "assistant_turn_id": turn_id}),
                self.loop,
            )
        self._finish_assistant_turn(turn_id or -1)
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

        reply_text: Optional[str] = None
        try:
            rag_t0 = time.perf_counter()
            rag_text = self._build_rag_context(text)
            rag_ms = (time.perf_counter() - rag_t0) * 1000.0
            with self.perf_lock:
                self.perf_rag_ms = rag_ms
                self.perf_llm_start_ts = time.perf_counter()
            sys_prompt = LLM_SYSTEM_PROMPT if not rag_text else LLM_SYSTEM_PROMPT + "\n" + rag_text
            recent_hist = self.history[-7:-1] if len(self.history) > 6 else self.history[:-1]
            reply_text = self.llm.chat(text, system=sys_prompt, history=recent_hist)
            with self.perf_lock:
                self.perf_llm_end_ts = time.perf_counter()
            if self.loop is not None:
                asyncio.run_coroutine_threadsafe(
                    self._send_text_obj({"event": "llm_text", "text": reply_text}),
                    self.loop,
                )
            database.add_message(self.session_id, "assistant", reply_text)
            self.history.append({"role": "assistant", "content": reply_text})
            self.last_seen[self._normalize_text(reply_text)] = time.time()
        except Exception as e:
            reply_text = "我刚刚没连上大模型，请再说一遍。"
            if self.loop is not None:
                asyncio.run_coroutine_threadsafe(
                    self._send_text_obj(
                        {"event": "llm_error", "fallback_text": reply_text, "detail": str(e)}
                    ),
                    self.loop,
                )
                asyncio.run_coroutine_threadsafe(
                    self._send_text_obj({"event": "llm_text", "text": reply_text}),
                    self.loop,
                )
            database.add_message(self.session_id, "assistant", reply_text)
            self.history.append({"role": "assistant", "content": reply_text})
            self.last_seen[self._normalize_text(reply_text)] = time.time()

        if reply_text:
            self._speak_text(reply_text)
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
                turn_id = self._begin_assistant_turn()
                if self.tts is None:
                    raise RuntimeError("TTS not initialized")
                try:
                    self.tts.stop()
                    self._clear_out_audio_q()
                except Exception:
                    pass
                if self.loop is not None:
                    asyncio.run_coroutine_threadsafe(
                        self._send_text_obj({"event": "tts_start", "rate": self.tts.sample_rate, "assistant_turn_id": turn_id}),
                        self.loop,
                    )
                count = 0
                interrupted_early = False
                playback_deadline = time.perf_counter()
                for chunk in self.tts.synthesize_stream(text):
                    if not self.send_enabled or self._active_assistant_turn_id != turn_id:
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
                    self._put_audio(turn_id, data)
                    chunk_duration_s = len(data) / max(float(self.tts.sample_rate) * 2.0, 1.0)
                    playback_deadline += chunk_duration_s
                    while True:
                        if not self.send_enabled or self._active_assistant_turn_id != turn_id:
                            interrupted_early = True
                            break
                        remain = playback_deadline - time.perf_counter()
                        if remain <= 0:
                            break
                        time.sleep(min(0.01, remain))
                    if interrupted_early:
                        break
                    if count % 5 == 0 and self.loop is not None:
                        asyncio.run_coroutine_threadsafe(
                            self._send_text_obj({"event": "tts_chunk", "count": count, "assistant_turn_id": turn_id}),
                            self.loop,
                        )
                finished_normally = self._finish_assistant_turn(turn_id, interrupted=interrupted_early)
                with self.perf_lock:
                    self.perf_tts_end_ts = time.perf_counter()
                if self.loop is not None and finished_normally and not interrupted_early:
                    asyncio.run_coroutine_threadsafe(
                        self._send_text_obj({"event": "tts_done", "count": count, "assistant_turn_id": turn_id}),
                        self.loop,
                    )
            except Exception as e:
                active_turn_id = self._active_assistant_turn_id
                if active_turn_id is not None:
                    self._finish_assistant_turn(active_turn_id)
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
            if len(self.history) == 0:
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
                        assistant_speaking = self.last_tts_start_time > 0
                        detector_open = self.barge_in.speech_state in {
                            SpeechState.INTERRUPT_PENDING,
                            SpeechState.INTERRUPTED,
                        } or not self.send_enabled
                        if result.is_final:
                            if assistant_speaking and not detector_open:
                                self._suppressed_final = (result.text, time.time())
                                continue
                            if assistant_speaking:
                                self._interrupt_now(force=True, hard_stop=True)
                                self._confirm_interrupt(force=True)
                            await self._forward_final_text(result.text)
                        else:
                            if assistant_speaking and not detector_open:
                                self._suppressed_partial = (result.text, time.time())
                                continue
                            if (
                                assistant_speaking
                                and len(result.text.strip()) >= 2
                            ):
                                self._interrupt_now(force=True, hard_stop=True)
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
                turn_id, chunk = await self.out_audio_q.get()
                if not self.send_enabled or self._active_assistant_turn_id != turn_id:
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

        self._reset_turn_start_gate()

        events = self.barge_in_detector.process_audio(
            audio_bytes=audio_bytes,
            detect_speech=detect_speech,
            last_tts_chunk_time=self.last_tts_chunk_time,
            last_tts_end_time=self.last_tts_end_time,
            tts_start_time=self.last_tts_start_time,
        )
        for event in events:
            if event.kind == BargeInEventKind.EARLY_TRIGGER:
                self._start_interrupt_collection(event.kind.value)
            elif event.kind == BargeInEventKind.PENDING:
                continue
            elif event.kind == BargeInEventKind.CONFIRMED:
                self._interrupt_now(force=True, hard_stop=True)
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
                    "assistant_turn_id": self._active_assistant_turn_id,
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
                self._append_pre_roll(processed_audio)
                self._handle_barge_in(processed_audio)
                try:
                    if self.stt is None:
                        raise RuntimeError("STT not initialized")
                    if self._skip_direct_stt_once:
                        self._skip_direct_stt_once = False
                    else:
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
