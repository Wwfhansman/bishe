import json
import requests
from ..config import ARK_API_KEY, ARK_BASE_URL, ARK_MODEL_ID

class LLMClient:
    def __init__(self):
        self.session = requests.Session()

    def chat(self, content, system=None, history=None, timeout=30):
        if not ARK_API_KEY or not ARK_MODEL_ID:
            raise RuntimeError("Missing ARK_API_KEY or ARK_MODEL_ID")
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        if history:
            for m in history:
                msgs.append(m)
        msgs.append({"role": "user", "content": content})
        headers = {
            "Authorization": f"Bearer {ARK_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {"model": ARK_MODEL_ID, "messages": msgs}
        r = self.session.post(f"{ARK_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except Exception:
            return json.dumps(data, ensure_ascii=False)