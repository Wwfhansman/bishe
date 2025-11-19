import asyncio
import threading
import json
import re
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ..stt.asr_client import ASRClient
from ..llm.llm_client import LLMClient
from ..tts.tts_client import TTSClient
from ..config import TTS_VOICE_TYPE, GREETING_TEXT, LLM_SYSTEM_PROMPT
from .. import database

app = FastAPI()
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# Initialize DB on startup
@app.on_event("startup")
async def startup_event():
    database.init_db()

class CreateSessionRequest(BaseModel):
    user_id: str

@app.post("/api/sessions")
async def create_session_endpoint(req: CreateSessionRequest):
    session_id = database.create_session(req.user_id)
    return {"session_id": session_id}

@app.get("/api/sessions")
async def get_sessions_endpoint(user_id: str):
    sessions = database.get_user_sessions(user_id)
    return {"sessions": sessions}

@app.get("/")
async def root():
    return HTMLResponse("""
    <!doctype html>
    <html><head><meta charset='utf-8'><title>Voice Test</title></head>
    <body>
      <a href='/frontend/index.html'>Open Test Page</a>
    </body></html>
    """)

@app.websocket("/ws/voice")
async def ws_voice(websocket: WebSocket, session_id: str):
    await websocket.accept()
    loop = asyncio.get_running_loop()
    asr = ASRClient()
    llm = LLMClient()
    out_audio_q: asyncio.Queue[bytes] = asyncio.Queue()
    tts_lock = threading.Lock()
    recv_bytes = 0
    recv_chunks = 0

    # Load history
    history = database.get_session_history(session_id, limit=10)
    print(f"Loaded history for session {session_id}: {len(history)} messages")

    async def send_text_obj(obj: dict):
        try:
            await websocket.send_text(json.dumps(obj, ensure_ascii=False))
        except Exception:
            pass

    def put_audio(b: bytes):
        asyncio.run_coroutine_threadsafe(out_audio_q.put(b), loop)

    seen_keys = set()
    def normalize_text(s: str):
        try:
            return re.sub(r"[\s，。！？,.!?:;；]+", "", s).lower()
        except Exception:
            return s
    last_seen = {}
    cooldown_sec = 5.0
    def trigger_reply(s: str):
        key_norm = normalize_text(s)
        now = time.time()
        ts_prev = last_seen.get(key_norm)
        if ts_prev is not None and (now - ts_prev) < cooldown_sec:
            return
        last_seen[key_norm] = now
        
        # Save User Message
        database.add_message(session_id, "user", s)
        history.append({"role": "user", "content": s})
        
        reply = None
        try:
            # Pass history to LLM
            reply = llm.chat(s, system=LLM_SYSTEM_PROMPT, history=history[:-1])
            asyncio.run_coroutine_threadsafe(send_text_obj({"event": "llm_text", "text": reply}), loop)
            
            # Save Assistant Message
            database.add_message(session_id, "assistant", reply)
            history.append({"role": "assistant", "content": reply})
        except Exception:
            reply = s
            asyncio.run_coroutine_threadsafe(send_text_obj({"event": "llm_error", "fallback_text": reply}), loop)
        
        # TTS Logic
        with tts_lock:
            try:
                client = TTSClient(voice_type=TTS_VOICE_TYPE)
                client.connect()
                client.submit_text(reply)
                asyncio.run_coroutine_threadsafe(send_text_obj({"event": "tts_start", "rate": client.rate}), loop)
                count = 0
                def on_chunk(b: bytes):
                    nonlocal count
                    count += 1
                    put_audio(b)
                    if count % 5 == 0:
                        asyncio.run_coroutine_threadsafe(send_text_obj({"event": "tts_chunk", "count": count}), loop)
                client.stream_chunks(on_chunk)
                asyncio.run_coroutine_threadsafe(send_text_obj({"event": "tts_done", "count": count}), loop)
                client.close()
            except Exception as e:
                try:
                    msg = str(e)
                except Exception:
                    msg = ""
                asyncio.run_coroutine_threadsafe(send_text_obj({"event": "error", "stage": "tts", "detail": msg}), loop)

    try:
        asr.connect()
        asr.send_full_request()
        await send_text_obj({"event": "asr_connected"})
    except Exception:
        await send_text_obj({"event": "error", "stage": "asr_connect"})
        await websocket.close(code=1011)
        return

    # Play Greeting ONLY if history is empty (new session)
    if len(history) == 0:
        def play_greeting():
            try:
                tg = TTSClient(voice_type=TTS_VOICE_TYPE)
                tg.connect()
                tg.submit_text(GREETING_TEXT)
                asyncio.run_coroutine_threadsafe(send_text_obj({"event": "tts_start", "rate": tg.rate}), loop)
                count = 0
                def on_chunk(b: bytes):
                    nonlocal count
                    count += 1
                    put_audio(b)
                    if count % 5 == 0:
                        asyncio.run_coroutine_threadsafe(send_text_obj({"event": "tts_chunk", "count": count}), loop)
                tg.stream_chunks(on_chunk)
                asyncio.run_coroutine_threadsafe(send_text_obj({"event": "tts_done", "count": count}), loop)
                tg.close()
                
                # Save greeting to history so it's not played again on resume
                database.add_message(session_id, "assistant", GREETING_TEXT)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(send_text_obj({"event": "error", "stage": "greeting", "detail": str(e)}), loop)

        threading.Thread(target=play_greeting, daemon=True).start()
    
    await send_text_obj({"event": "tts_ready"})

    def on_obj(obj: dict):
        try:
            res = obj.get("result")
            if isinstance(res, dict):
                uts = res.get("utterances")
                if isinstance(uts, list) and len(uts) > 0:
                    for u in reversed(uts):
                        if isinstance(u, dict) and u.get("definite") is True:
                            tt = u.get("text")
                            if isinstance(tt, str) and tt.strip():
                                asyncio.run_coroutine_threadsafe(send_text_obj({"event": "asr_text", "text": tt}), loop)
                                trigger_reply(tt)
                                break
        except Exception:
            asyncio.run_coroutine_threadsafe(send_text_obj({"event": "error", "stage": "asr_recv"}), loop)

    recv_thread = asr.start_receiving_objects(on_obj)

    async def sender():
        try:
            while True:
                chunk = await out_audio_q.get()
                await websocket.send_bytes(chunk)
        except WebSocketDisconnect:
            return
        except Exception:
            return

    send_task = asyncio.create_task(sender())
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.receive":
                if msg.get("bytes") is not None:
                    bs = msg["bytes"]
                    recv_bytes += len(bs)
                    recv_chunks += 1
                    if recv_chunks % 10 == 0:
                        await send_text_obj({"event": "audio_stats", "chunks": recv_chunks, "bytes": recv_bytes})
                    asr.send_audio_chunk(bs)
                elif msg.get("text") is not None:
                    try:
                        data = json.loads(msg["text"])
                        if data.get("cmd") == "stop":
                            asr.finish_stream()
                    except Exception:
                        pass
            elif msg.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        await send_text_obj({"event": "error", "stage": "ws_loop"})
    try:
        asr.finish_stream()
    except Exception:
        pass
    try:
        await websocket.close()
    except Exception:
        pass
    send_task.cancel()
    recv_thread.join(timeout=1.0)
    asr.close()

@app.get("/api/tts_probe")
async def tts_probe(text: str = "你好，这是一次测试合成。"):
    try:
        tts = TTSClient(voice_type=TTS_VOICE_TYPE)
        tts.connect()
    except Exception as e:
        return {"ok": False, "stage": "connect", "error": str(e)}
    status = None
    logid = None
    count = 0
    total = 0
    first_samples = None
    def on_chunk(b: bytes):
        nonlocal count, total, first_samples
        count += 1
        total += len(b)
        if first_samples is None and len(b) >= 2:
            first_samples = len(b) // 2
    try:
        tts.submit_text(text)
        tts.stream_chunks(on_chunk)
    except Exception as e:
        try:
            tts.close()
        except Exception:
            pass
        return {"ok": False, "stage": "stream", "status": status, "logid": logid, "chunk_count": count, "total_bytes": total, "error": str(e)}
    try:
        tts.close()
    except Exception:
        pass
    return {"ok": True, "status": status, "logid": logid, "chunk_count": count, "total_bytes": total, "first_chunk_samples": first_samples}