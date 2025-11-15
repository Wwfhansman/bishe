import json
import struct
import threading
import websocket
from ..config import APP_ID, ACCESS_TOKEN, RESOURCE_ID, ENDPOINT, CONNECT_ID, FORMAT, CODEC, RATE, BITS, CHANNELS, LANGUAGE

class ASRClient:
    def __init__(self):
        self.ws = None
        self.receiving = False

    def connect(self):
        headers = [
            f"X-Api-App-Key: {APP_ID}",
            f"X-Api-Access-Key: {ACCESS_TOKEN}",
            f"X-Api-Resource-Id: {RESOURCE_ID}",
            f"X-Api-Connect-Id: {CONNECT_ID}",
        ]
        self.ws = websocket.create_connection(ENDPOINT, header=headers)
        self.ws.settimeout(0.2)

    def _build_header(self, version=1, header_size_units=1, msg_type=1, flags=0, serialization=1, compression=0):
        b0 = ((version & 0xF) << 4) | (header_size_units & 0xF)
        b1 = ((msg_type & 0xF) << 4) | (flags & 0xF)
        b2 = ((serialization & 0xF) << 4) | (compression & 0xF)
        b3 = 0
        return bytes([b0, b1, b2, b3])

    def _send_packet(self, header_bytes, payload_bytes, seq=None):
        parts = [header_bytes]
        if seq is not None:
            parts.append(struct.pack(">i", seq))
        parts.append(struct.pack(">I", len(payload_bytes)))
        parts.append(payload_bytes)
        self.ws.send_binary(b"".join(parts))

    def send_full_request(self):
        audio = {
            "format": FORMAT,
            "codec": CODEC,
            "rate": RATE,
            "bits": BITS,
            "channel": CHANNELS,
        }
        if LANGUAGE and ("bigmodel_nostream" in ENDPOINT):
            audio["language"] = LANGUAGE
        p = {
            "audio": audio,
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "result_type": "single",
                "show_utterances": True,
                "end_window_size": 800,
                "force_to_speech_time": 1000,
            },
        }
        payload = json.dumps(p, ensure_ascii=False).encode("utf-8")
        h = self._build_header(msg_type=1, flags=0, serialization=1, compression=0)
        self._send_packet(h, payload, seq=None)

    def receive_once(self, timeout=2.0):
        try:
            self.ws.settimeout(timeout)
            msg = self.ws.recv()
        except Exception:
            try:
                self.ws.settimeout(0.2)
            except Exception:
                pass
            return None
        try:
            self.ws.settimeout(0.2)
        except Exception:
            pass
        if isinstance(msg, bytes):
            if len(msg) < 8:
                return None
            hb = msg[:4]
            hs = (hb[0] & 0x0F) * 4
            rem = msg[hs:]
            if len(rem) >= 8:
                mt = (hb[1] >> 4) & 0x0F
                ps_off = 4 if mt == 0b1001 else 0
                ps = struct.unpack(">I", rem[ps_off:ps_off+4])[0]
                payload = rem[ps_off+4:ps_off+4+ps]
            else:
                return None
            try:
                return json.loads(payload.decode("utf-8"))
            except Exception:
                return None
        else:
            try:
                return json.loads(msg)
            except Exception:
                return None

    def _extract_text(self, obj):
        if not isinstance(obj, dict):
            return None
        t = obj.get("text")
        if isinstance(t, str) and t.strip():
            return t
        res = obj.get("result")
        if isinstance(res, dict):
            t2 = res.get("text")
            if isinstance(t2, str) and t2.strip():
                return t2
            uts = res.get("utterances")
            if isinstance(uts, list) and len(uts) > 0:
                for u in reversed(uts):
                    if isinstance(u, dict):
                        tu = u.get("text")
                        if isinstance(tu, str) and tu.strip():
                            return tu
        alts = obj.get("alternatives")
        if isinstance(alts, list) and len(alts) > 0:
            a0 = alts[0]
            if isinstance(a0, dict):
                for k2 in ("text","transcript","result"):
                    x = a0.get(k2)
                    if isinstance(x, str) and x.strip():
                        return x
            elif isinstance(a0, str) and a0.strip():
                return a0
        return None

    def start_receiving(self, on_text):
        self.receiving = True
        def loop():
            while self.receiving:
                try:
                    msg = self.ws.recv()
                except Exception:
                    continue
                if isinstance(msg, bytes):
                    if len(msg) < 8:
                        continue
                    hb = msg[:4]
                    hs = (hb[0] & 0x0F) * 4
                    rem = msg[hs:]
                    if len(rem) < 8:
                        continue
                    mt = (hb[1] >> 4) & 0x0F
                    ps_off = 4 if mt == 0b1001 else 0
                    ps = struct.unpack(">I", rem[ps_off:ps_off+4])[0]
                    payload = rem[ps_off+4:ps_off+4+ps]
                    try:
                        obj = json.loads(payload.decode("utf-8"))
                    except Exception:
                        continue
                    t = self._extract_text(obj)
                    if t:
                        on_text(t)
                else:
                    try:
                        obj = json.loads(msg)
                        t = self._extract_text(obj)
                        if t:
                            on_text(t)
                    except Exception:
                        pass
        th = threading.Thread(target=loop, daemon=True)
        th.start()
        return th

    def stream_audio(self, chunks_iter):
        idx = 1
        for chunk in chunks_iter:
            h = self._build_header(header_size_units=1, msg_type=2, flags=0, serialization=0, compression=0)
            self._send_packet(h, chunk, seq=None)
            idx += 1
        h = self._build_header(header_size_units=1, msg_type=2, flags=2, serialization=0, compression=0)
        self._send_packet(h, b"", seq=None)

    def close(self):
        self.receiving = False
        try:
            self.ws.close()
        except Exception:
            pass