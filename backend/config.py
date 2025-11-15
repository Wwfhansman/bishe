import os
import uuid
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def env(name, default=None):
    v = os.environ.get(name)
    return v if v is not None and v != "" else default

APP_ID = env("ASR_APP_ID")
ACCESS_TOKEN = env("ASR_ACCESS_TOKEN")
RESOURCE_ID = env("ASR_RESOURCE_ID", "volc.bigasr.sauc.duration")
ENDPOINT = env("ASR_ENDPOINT", "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async")
LANGUAGE = env("ASR_LANGUAGE")
CONNECT_ID = env("ASR_CONNECT_ID", str(uuid.uuid4()))
RATE = int(env("ASR_RATE", "16000"))
BITS = int(env("ASR_BITS", "16"))
CHANNELS = int(env("ASR_CHANNELS", "1"))
FORMAT = env("ASR_FORMAT", "pcm")
CODEC = env("ASR_CODEC", "raw")
INPUT_DEVICE = env("ASR_INPUT_DEVICE")
CHUNK_MS = int(env("ASR_CHUNK_MS", "200"))