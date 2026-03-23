import json
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from ..config import AUTH_JWT_SECRET, AUTH_JWT_EXPIRES, WECHAT_APPID, WECHAT_SECRET
from .. import database
from ..voice import create_tts_service, load_voice_registry
from .voice_session import VoiceSessionRunner

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
    if not user_id:
        return {"ok": False, "error": "missing_user_id"}
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
async def get_session_history_endpoint(session_id: str, request: Request, limit: int = 50, user_id: Optional[str] = None):
    """获取某个会话的聊天历史（小程序切换/恢复会话时调用）"""
    auth = request.headers.get("Authorization")
    uid = None
    if isinstance(auth, str) and auth.startswith("Bearer "):
        uid = _jwt_user(auth.split(" ", 1)[1])
    if not uid and isinstance(user_id, str):
        uid = user_id
    if not uid or not database.session_belongs_to(session_id, uid):
        return {"ok": False, "error": "session_forbidden"}
    messages = database.get_session_history(session_id, limit=limit)
    return {"session_id": session_id, "messages": messages}

@app.delete("/api/sessions/{session_id}")
async def delete_session_endpoint(session_id: str, request: Request, user_id: Optional[str] = None):
    """删除会话及其所有聊天记录"""
    auth = request.headers.get("Authorization")
    uid = None
    if isinstance(auth, str) and auth.startswith("Bearer "):
        uid = _jwt_user(auth.split(" ", 1)[1])
    if not uid and isinstance(user_id, str):
        uid = user_id
    if not uid:
        return {"ok": False, "error": "session_forbidden"}
    ok = database.delete_session(session_id, uid)
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
async def ws_voice(websocket: WebSocket, session_id: str, token: Optional[str] = None, user_id: Optional[str] = None):
    await websocket.accept()
    uid = None
    if isinstance(token, str):
        uid = _jwt_user(token)

    session_owner = database.get_session_owner(session_id)
    if session_owner is None:
        await send_text_safely(websocket, {"event": "session_error", "detail": "session_not_found"})
        await websocket.close(code=1008)
        return
    if uid:
        if session_owner != uid:
            await send_text_safely(websocket, {"event": "session_error", "detail": "session_forbidden"})
            await websocket.close(code=1008)
            return
    else:
        if not isinstance(user_id, str) or session_owner != user_id:
            await send_text_safely(websocket, {"event": "session_error", "detail": "session_forbidden"})
            await websocket.close(code=1008)
            return
    runner = VoiceSessionRunner(websocket=websocket, session_id=session_id)
    await runner.run()

async def send_text_safely(websocket: WebSocket, obj: dict):
    try:
        await websocket.send_text(json.dumps(obj, ensure_ascii=False))
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
