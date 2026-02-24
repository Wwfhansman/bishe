import asyncio
import threading
import json
import re
import time
try:
    import webrtcvad as _webrtcvad
except Exception:
    _webrtcvad = None
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from ..llm.llm_client import LLMClient
from ..config import GREETING_TEXT, LLM_SYSTEM_PROMPT
from ..config import RATE as ASR_RATE
from ..config import AUTH_JWT_SECRET, AUTH_JWT_EXPIRES, WECHAT_APPID, WECHAT_SECRET
from .. import database
from ..voice import AudioChunk, create_stt_service, create_tts_service, load_voice_registry

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS 中间件 — 允许小程序/Web 前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# Initialize DB on startup
@app.on_event("startup")
async def startup_event():
    database.init_db()

class CreateSessionRequest(BaseModel):
    user_id: Optional[str] = None

@app.post("/api/sessions")
async def create_session_endpoint(req: CreateSessionRequest, request: Request):
    auth = request.headers.get("Authorization")
    user_id = None
    if isinstance(auth, str) and auth.startswith("Bearer "):
        tok = auth.split(" ", 1)[1]
        user_id = _jwt_user(tok)
    if not user_id and isinstance(req.user_id, str):
        user_id = req.user_id
    session_id = database.create_session(user_id)
    return {"session_id": session_id}

@app.get("/api/sessions")
async def get_sessions_endpoint(request: Request, user_id: Optional[str] = None):
    uid = user_id
    if not uid:
        auth = request.headers.get("Authorization")
        if isinstance(auth, str) and auth.startswith("Bearer "):
            tok = auth.split(" ", 1)[1]
            uid = _jwt_user(tok)
    sessions = database.get_user_sessions(uid)
    return {"sessions": sessions}

@app.get("/api/sessions/{session_id}/history")
async def get_session_history_endpoint(session_id: str, request: Request, limit: int = 50):
    """获取某个会话的聊天历史（小程序切换/恢复会话时调用）"""
    messages = database.get_session_history(session_id, limit=limit)
    return {"session_id": session_id, "messages": messages}

@app.delete("/api/sessions/{session_id}")
async def delete_session_endpoint(session_id: str, request: Request):
    """删除会话及其所有聊天记录"""
    ok = database.delete_session(session_id)
    if not ok:
        return {"ok": False, "error": "session_not_found"}
    return {"ok": True}

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
async def ws_voice(websocket: WebSocket, session_id: str, token: Optional[str] = None):
    await websocket.accept()
    loop = asyncio.get_running_loop()
    registry = None
    stt = None
    tts = None
    llm = LLMClient()
    out_audio_q: asyncio.Queue[bytes] = asyncio.Queue()
    tts_lock = threading.Lock()
    send_enabled = True
    recv_bytes = 0
    recv_chunks = 0

    uid = None
    if isinstance(token, str):
        uid = _jwt_user(token)

    # Load history
    history = database.get_session_history(session_id, limit=10)
    print(f"Loaded history for session {session_id}: {len(history)} messages")

    async def send_text_obj(obj: dict):
        try:
            await websocket.send_text(json.dumps(obj, ensure_ascii=False))
        except Exception:
            pass

    def put_audio(b: bytes):
        if send_enabled:
            asyncio.run_coroutine_threadsafe(out_audio_q.put(b), loop)

    use_native_vad = _webrtcvad is not None
    vad = _webrtcvad.Vad(3) if use_native_vad else None  # mode 3: 最严格，只有明确语音才触发
    vad_enabled = True
    min_speech_ms = 1000  # 需要连续说话1秒才确认为真正打断
    start_frames = 15     # 300ms，过滤短暂噪音（咳嗽、碗碟碰撞等）
    silence_end_frames = 15
    frame_ms = 20
    frame_bytes = int(ASR_RATE * frame_ms / 1000) * 2
    vad_buf = b""
    speaking_frames = 0
    silence_frames = 0
    pausepending = False
    interrupt_confirmed = False
    fallback_sensitivity = 0 # 最迟钝档，减少误触发
    noise_floor = 1000.0     # 提高底噪阈值，过滤更强的背景噪音
    tts_cooldown_ms = 500    # TTS 结束后的冷却期(ms)，避免喇叭余音/回声误触发
    def energy_is_speech(fb: bytes) -> bool:
        a = np.frombuffer(fb, dtype=np.int16)
        e = float(np.mean(np.abs(a)))
        # 灵敏度系数：系数越大越难触发（整体上调）
        t = 6.0 if fallback_sensitivity == 0 else 5.0 if fallback_sensitivity == 1 else 4.0 if fallback_sensitivity == 2 else 3.0
        return e > noise_floor * t

    def clear_out_audio_q():
        while True:
            try:
                out_audio_q.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def send_event(obj: dict):
        try:
            await websocket.send_text(json.dumps(obj, ensure_ascii=False))
        except Exception:
            pass

    def interrupt_now():
        nonlocal send_enabled, pausepending
        if not send_enabled and not pausepending: # 如果已经处于暂停或停止状态，不再重复触发
            return
        send_enabled = False
        clear_out_audio_q()
        asyncio.run_coroutine_threadsafe(send_event({"event": "tts_reset"}), loop)
        pausepending = True
        # print("VAD: Potential interrupt detected, pausing audio...")

    def confirm_interrupt():
        nonlocal interrupt_confirmed
        interrupt_confirmed = True
        try:
            if tts is not None:
                tts.stop()
        except Exception:
            pass
        asyncio.run_coroutine_threadsafe(send_event({"event": "tts_interrupted"}), loop)

    def resume_play():
        nonlocal send_enabled, pausepending, speaking_frames, silence_frames, interrupt_confirmed, vad_buf
        send_enabled = True
        pausepending = False
        interrupt_confirmed = False  # 确保状态重置
        speaking_frames = 0
        silence_frames = 0
        vad_buf = b""  # 清空残留音频数据，避免后续误判

    seen_keys = set()
    def normalize_text(s: str):
        try:
            return re.sub(r"[\s，。！？,.!?:;；]+", "", s).lower()
        except Exception:
            return s
    last_seen = {}
    cooldown_sec = 5.0
    last_tts_end_time = 0  # 记录上一次语音结束的时间，用于回声抑制

    def trigger_reply(s: str):
        nonlocal last_tts_end_time
        now = time.time()
        
        # 1. 回声抑制：如果 AI 刚刚说完话（1.5秒内），忽略识别结果
        if now - last_tts_end_time < 1.5:
            return

        key_norm = normalize_text(s)
        ts_prev = last_seen.get(key_norm)
        if ts_prev is not None and (now - ts_prev) < cooldown_sec:
            return
        last_seen[key_norm] = now
        
        print(f"Triggering reply for: {s}")
        
        # Save User Message
        database.add_message(session_id, "user", s)
        history.append({"role": "user", "content": s})
        
        reply = None
        try:
            rag_text = None
            try:
                from ..rag.retriever import best_text
            except Exception:
                try:
                    import sys
                    from pathlib import Path
                    sys.path.append(str(Path(__file__).resolve().parents[1]))
                    from rag.retriever import best_text
                except Exception:
                    best_text = None
            if best_text is not None:
                try:
                    # Only use RAG if query is long enough and not just a simple greeting
                    if len(s) > 3 and not any(g in s.lower() for g in ["你好", "喂", "在吗"]):
                        rag_text = best_text(s, 6, 1200)
                        if rag_text:
                            print(f"RAG Context found (first 50 chars): {rag_text[:50]}...")
                except Exception as e:
                    print(f"RAG search error: {e}")
                    rag_text = None
            sys_prompt = LLM_SYSTEM_PROMPT
            if rag_text:
                sys_prompt = sys_prompt + "\n" + rag_text
            
            # 2. 限制历史记录长度（只取最近 6 条），提升响应速度
            recent_hist = history[-7:-1] if len(history) > 6 else history[:-1]
            reply = llm.chat(s, system=sys_prompt, history=recent_hist)
            print(f"LLM Reply: {reply}")
            asyncio.run_coroutine_threadsafe(send_text_obj({"event": "llm_text", "text": reply}), loop)
            
            # Save Assistant Message
            database.add_message(session_id, "assistant", reply)
            history.append({"role": "assistant", "content": reply})
            
            # 3. 回声抑制：防止 AI 的长回复被它自己触发
            last_seen[normalize_text(reply)] = time.time()
        except Exception as e:
            reply = s
            detail = ""
            try:
                detail = str(e)
            except Exception:
                detail = ""
            asyncio.run_coroutine_threadsafe(send_text_obj({"event": "llm_error", "fallback_text": reply, "detail": detail}), loop)
        
        with tts_lock:
            try:
                nonlocal send_enabled, pausepending, interrupt_confirmed, speaking_frames, silence_frames, vad_buf
                pausepending = False
                interrupt_confirmed = False
                speaking_frames = 0
                silence_frames = 0
                vad_buf = b""
                if tts is None:
                    raise RuntimeError("TTS not initialized")
                try:
                    tts.stop()
                    clear_out_audio_q() # 4. 关键：新回复开始前必须清空旧音频，解决“复读/重音”问题
                except Exception:
                    pass
                asyncio.run_coroutine_threadsafe(send_text_obj({"event": "tts_start", "rate": tts.sample_rate}), loop)
                count = 0
                send_enabled = True
                for ch in tts.synthesize_stream(reply):
                    if getattr(ch, "is_final", False):
                        break
                    b = getattr(ch, "pcm16_bytes", b"")
                    if not b:
                        continue
                    count += 1
                    put_audio(b)
                    if count % 5 == 0:
                        asyncio.run_coroutine_threadsafe(send_text_obj({"event": "tts_chunk", "count": count}), loop)
                asyncio.run_coroutine_threadsafe(send_text_obj({"event": "tts_done", "count": count}), loop)
                last_tts_end_time = time.time() # 5. 记录结束时间，辅助回声抑制
            except Exception as e:
                try:
                    msg = str(e)
                except Exception:
                    msg = ""
                asyncio.run_coroutine_threadsafe(send_text_obj({"event": "error", "stage": "tts", "detail": msg}), loop)

    try:
        registry = load_voice_registry()
        stt = create_stt_service(registry)
        tts = create_tts_service(registry)
        stt.initialize()
        tts.initialize()
        await send_text_obj({"event": "asr_connected"})
    except Exception as e:
        try:
            await send_text_obj({"event": "voice_init_error", "detail": str(e)})
        except Exception:
            pass
        await websocket.close(code=1011)
        return

    # Play Greeting ONLY if history is empty (new session)
    if len(history) == 0:
        def play_greeting():
            try:
                if tts is None:
                    return
                try:
                    tts.stop()
                except Exception:
                    pass
                asyncio.run_coroutine_threadsafe(send_text_obj({"event": "tts_start", "rate": tts.sample_rate}), loop)
                count = 0
                for ch in tts.synthesize_stream(GREETING_TEXT):
                    if getattr(ch, "is_final", False):
                        break
                    b = getattr(ch, "pcm16_bytes", b"")
                    if not b:
                        continue
                    count += 1
                    put_audio(b)
                    if count % 5 == 0:
                        asyncio.run_coroutine_threadsafe(send_text_obj({"event": "tts_chunk", "count": count}), loop)
                asyncio.run_coroutine_threadsafe(send_text_obj({"event": "tts_done", "count": count}), loop)
                
                # Save greeting to history so it's not played again on resume
                database.add_message(session_id, "assistant", GREETING_TEXT)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(send_text_obj({"event": "error", "stage": "greeting", "detail": str(e)}), loop)

        threading.Thread(target=play_greeting, daemon=True).start()
    
    await send_text_obj({"event": "tts_ready"})

    async def poll_stt():
        try:
            while True:
                if stt is not None:
                    results = stt.poll_result()
                    for r in results:
                        if not isinstance(r.text, str) or not r.text.strip():
                            continue
                        if r.is_final:
                            await send_text_obj({"event": "asr_text", "text": r.text})
                            # Run reply in thread to avoid blocking STT loop
                            threading.Thread(target=trigger_reply, args=(r.text,), daemon=True).start()
                        else:
                            await send_text_obj({"event": "asr_partial", "text": r.text})
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"STT poll error: {e}")

    poll_task = asyncio.create_task(poll_stt())
    
    async def sender():
        try:
            while True:
                chunk = await out_audio_q.get()
                if send_enabled:
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
                    if vad_enabled:
                        # TTS 冷却期：刚结束播放后短暂跳过 VAD，避免回声/余音误触发
                        in_cooldown = (time.time() - last_tts_end_time) * 1000 < tts_cooldown_ms if last_tts_end_time > 0 else False
                        if not in_cooldown:
                            vad_buf += bs
                            while len(vad_buf) >= frame_bytes:
                                fb = vad_buf[:frame_bytes]
                                vad_buf = vad_buf[frame_bytes:]
                                v = False
                                try:
                                    v = vad.is_speech(fb, ASR_RATE) if use_native_vad else energy_is_speech(fb)
                                except Exception:
                                    v = False
                                if v:
                                    speaking_frames += 1
                                    silence_frames = 0
                                    if not pausepending and speaking_frames >= start_frames:
                                        interrupt_now()
                                    if pausepending and not interrupt_confirmed:
                                        if speaking_frames * frame_ms >= min_speech_ms:
                                            confirm_interrupt()
                                else:
                                    silence_frames += 1
                                    if silence_frames > 5:  # 100ms 容忍语音中的自然间隙
                                        speaking_frames = 0
                                    if not use_native_vad:
                                        a = np.frombuffer(fb, dtype=np.int16)
                                        e = float(np.mean(np.abs(a)))
                                        noise_floor = noise_floor * 0.95 + e * 0.05
                                    if pausepending and not interrupt_confirmed and silence_frames >= silence_end_frames:
                                        resume_play()
                    recv_bytes += len(bs)
                    recv_chunks += 1
                    if recv_chunks % 10 == 0:
                        await send_text_obj({"event": "audio_stats", "chunks": recv_chunks, "bytes": recv_bytes})
                    try:
                        if stt is None:
                            raise RuntimeError("STT not initialized")
                        stt.accept_audio(AudioChunk(pcm16_bytes=bs, sample_rate=ASR_RATE, channels=1))
                    except Exception as e:
                        try:
                            await send_text_obj({"event": "error", "stage": "asr_send", "detail": str(e)})
                        except Exception:
                            pass
                        break
                elif msg.get("text") is not None:
                    try:
                        data = json.loads(msg["text"])
                        if data.get("cmd") == "stop":
                            if stt is not None:
                                stt.reset()
                        elif data.get("cmd") == "interrupt_config":
                            e = data.get("enable")
                            s = data.get("sensitivity")
                            m = data.get("min_speech_ms")
                            if isinstance(e, bool):
                                vad_enabled = e
                            if isinstance(s, int) and 0 <= s <= 3:
                                if use_native_vad:
                                    try:
                                        vad.set_mode(s)
                                    except Exception:
                                        pass
                                else:
                                    fallback_sensitivity = s
                            if isinstance(m, int) and m > 0:
                                min_speech_ms = m
                            await send_text_obj({"event": "interrupt_config_ok"})
                        elif data.get("cmd") == "interrupt_status":
                            st = {
                                "event": "interrupt_status",
                                "enable": vad_enabled,
                                "min_speech_ms": min_speech_ms,
                                "pausepending": pausepending,
                                "confirmed": interrupt_confirmed,
                                "send_enabled": send_enabled,
                            }
                            await send_text_obj(st)
                    except Exception:
                        pass
            elif msg.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await send_text_obj({"event": "error", "stage": "ws_loop", "detail": str(e)})
        except Exception:
            pass
    try:
        await websocket.close()
    except Exception:
        pass
    poll_task.cancel()
    send_task.cancel()
    try:
        if stt is not None:
            stt.close()
    except Exception:
        pass
    try:
        if tts is not None:
            tts.close()
    except Exception:
        pass

@app.get("/api/tts_probe")
async def tts_probe(text: str = "你好，这是一次测试合成。"):
    count = 0
    total = 0
    first_samples = None
    try:
        registry = load_voice_registry()
        tts = create_tts_service(registry)
        tts.initialize()
        for ch in tts.synthesize_stream(text):
            if getattr(ch, "is_final", False):
                break
            b = getattr(ch, "pcm16_bytes", b"")
            if not b:
                continue
            count += 1
            total += len(b)
            if first_samples is None and len(b) >= 2:
                first_samples = len(b) // 2
    except Exception as e:
        return {"ok": False, "stage": "tts", "chunk_count": count, "total_bytes": total, "error": str(e)}
    try:
        tts.close()
    except Exception:
        pass
    return {"ok": True, "chunk_count": count, "total_bytes": total, "first_chunk_samples": first_samples, "sample_rate": getattr(tts, "sample_rate", None)}

@app.get("/api/rag_query")
async def rag_query(q: str, k: int = 5):
    try:
        from ..rag.retriever import search
    except Exception:
        import sys
        from pathlib import Path
        sys.path.append(str(Path(__file__).resolve().parents[1]))
        from rag.retriever import search
    r = search(q, k)
    return r

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class WechatLoginRequest(BaseModel):
    code: str

def _b64url(b: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

def _jwt_sign(payload: dict) -> str:
    import json, hmac, hashlib, time
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    if "exp" not in payload:
        payload = {**payload, "exp": now + AUTH_JWT_EXPIRES}
    h64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(AUTH_JWT_SECRET.encode(), (h64 + "." + p64).encode(), hashlib.sha256).digest()
    return h64 + "." + p64 + "." + _b64url(sig)

def _jwt_user(token: str) -> Optional[str]:
    import base64, hashlib, hmac, json, time
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h64, p64, s64 = parts
        sig = base64.urlsafe_b64decode(s64 + "=" * (-len(s64) % 4))
        exp_sig = hmac.new(AUTH_JWT_SECRET.encode(), (h64 + "." + p64).encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(sig, exp_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(p64 + "=" * (-len(p64) % 4)))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload.get("sub")
    except Exception:
        return None

@app.post("/api/auth/register")
async def auth_register(req: RegisterRequest):
    uid = database.create_user(req.username, req.password)
    if not uid:
        return {"ok": False}
    tok = _jwt_sign({"sub": uid})
    return {"ok": True, "token": tok, "user_id": uid}

@app.post("/api/auth/login")
async def auth_login(req: LoginRequest):
    uid = database.validate_user(req.username, req.password)
    if not uid:
        return {"ok": False}
    tok = _jwt_sign({"sub": uid})
    return {"ok": True, "token": tok, "user_id": uid}

@app.post("/api/auth/wechat_login")
async def auth_wechat(req: WechatLoginRequest):
    # Mock Login for Development
    if req.code == "mock_login_code":
        uid = database.ensure_user_wechat("mock_openid_123456")
        if not uid:
            return {"ok": False, "error": "db_error"}
        tok = _jwt_sign({"sub": uid})
        return {"ok": True, "token": tok, "user_id": uid, "is_mock": True}

    import urllib.request, urllib.parse, json
    if not WECHAT_APPID or not WECHAT_SECRET:
        return {"ok": False, "error": "missing_config", "detail": "WECHAT_APPID or WECHAT_SECRET not set in env"}
    
    qs = urllib.parse.urlencode({
        "appid": WECHAT_APPID,
        "secret": WECHAT_SECRET,
        "js_code": req.code,
        "grant_type": "authorization_code",
    })
    try:
        with urllib.request.urlopen("https://api.weixin.qq.com/sns/jscode2session?" + qs, timeout=5) as r:
            j = json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "error": "network_error", "detail": str(e)}
    
    openid = j.get("openid")
    if not isinstance(openid, str):
        return {"ok": False, "error": "upstream_error", "upstream_response": j}
        
    uid = database.ensure_user_wechat(openid)
    if not uid:
        return {"ok": False, "error": "db_error"}
    tok = _jwt_sign({"sub": uid})
    return {"ok": True, "token": tok, "user_id": uid}

@app.get("/api/me")
async def api_me(request: Request):
    auth = request.headers.get("Authorization")
    if not isinstance(auth, str) or not auth.startswith("Bearer "):
        return {"ok": False}
    tok = auth.split(" ", 1)[1]
    uid = _jwt_user(tok)
    if not uid:
        return {"ok": False}
    return {"ok": True, "user_id": uid}
