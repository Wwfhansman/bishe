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
ASR_END_WINDOW_SIZE = int(env("ASR_END_WINDOW_SIZE", "800"))
ASR_FORCE_TO_SPEECH_TIME = int(env("ASR_FORCE_TO_SPEECH_TIME", "1000"))
ARK_API_KEY = env("ARK_API_KEY")
ARK_BASE_URL = env("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
ARK_MODEL_ID = env("ARK_MODEL_ID")
TC_APP_ID = env("TC_APP_ID")
TC_SECRET_ID = env("TC_SECRET_ID")
TC_SECRET_KEY = env("TC_SECRET_KEY")
TC_VOICE_TYPE = env("TC_VOICE_TYPE")
TTS_VOICE_TYPE = env("TTS_VOICE_TYPE", TC_VOICE_TYPE if TC_VOICE_TYPE else "601005")
TTS_RATE = int(env("TTS_RATE", "24000"))