import json
import uuid
import time
import hmac
import base64
import hashlib
import websocket
from urllib.parse import urlencode, quote
from ..config import TC_APP_ID, TC_SECRET_ID, TC_SECRET_KEY, TTS_RATE, CHANNELS, TTS_VOICE_TYPE

TC_WS_ENDPOINT = "wss://tts.cloud.tencent.com/stream_wsv2"

class TTSClient:
    def __init__(self, voice_type: str, rate: int = TTS_RATE, encoding: str = "pcm"):
        self.voice_type = voice_type
        self.rate = rate
        self.encoding = encoding
        self.ws = None
        self.session_id = None

    def connect(self):
        if not TC_APP_ID or not TC_SECRET_ID or not TC_SECRET_KEY:
            raise RuntimeError("Missing Tencent TTS credentials")
        self.session_id = str(uuid.uuid4())
        ts = int(time.time())
        exp = ts + 3600
        params = {
            "Action": "TextToStreamAudioWSv2",
            "AppId": int(TC_APP_ID),
            "SecretId": TC_SECRET_ID,
            "Timestamp": ts,
            "Expired": exp,
            "SessionId": self.session_id,
            "SampleRate": int(self.rate),
            "Codec": self.encoding if self.encoding in ("pcm", "mp3") else "pcm",
        }
        vt = None
        try:
            vt = int(self.voice_type)
        except Exception:
            try:
                vt = int(TTS_VOICE_TYPE) if TTS_VOICE_TYPE else None
            except Exception:
                vt = None
        if vt is not None:
            params["VoiceType"] = vt
        base_q = "&".join([f"{k}={quote(str(params[k]))}" for k in sorted(params.keys())])
        sign_str = f"GETtts.cloud.tencent.com/stream_wsv2?{base_q}"
        dig = hmac.new(TC_SECRET_KEY.encode("utf-8"), sign_str.encode("utf-8"), hashlib.sha1).digest()
        signature = base64.b64encode(dig).decode("utf-8")
        params["Signature"] = signature
        url = f"{TC_WS_ENDPOINT}?{urlencode(params)}"
        self.ws = websocket.create_connection(url)
        self.ws.settimeout(1.0)

    def _send_text(self, obj: dict):
        self.ws.send(json.dumps(obj, ensure_ascii=False))

    def submit_text(self, text: str):
        if not self.session_id:
            self.session_id = str(uuid.uuid4())
        mid = str(uuid.uuid4())
        msg = {"session_id": self.session_id, "message_id": mid, "action": "ACTION_SYNTHESIS", "data": text}
        self._send_text(msg)
        end_msg = {"session_id": self.session_id, "message_id": str(uuid.uuid4()), "action": "ACTION_COMPLETE", "data": ""}
        self._send_text(end_msg)

    def stream_chunks(self, on_chunk):
        while True:
            try:
                msg = self.ws.recv()
            except Exception:
                break
            if isinstance(msg, bytes):
                if len(msg) == 0:
                    continue
                on_chunk(msg)
            else:
                try:
                    data = json.loads(msg)
                except Exception:
                    continue
                if isinstance(data, dict):
                    c = data.get("code")
                    if c is not None and c != 0:
                        raise RuntimeError(json.dumps(data, ensure_ascii=False))
                    if data.get("final") == 1:
                        break

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass