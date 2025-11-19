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

# ASR Config
APP_ID = env("ASR_APP_ID")
ACCESS_TOKEN = env("ASR_ACCESS_TOKEN")
RESOURCE_ID = env("ASR_RESOURCE_ID", "volc.bigasr.sauc.duration")
ENDPOINT = env("ASR_ENDPOINT", "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async")
LANGUAGE = env("ASR_LANGUAGE", "zh-CN")
CONNECT_ID = env("ASR_CONNECT_ID", str(uuid.uuid4()))
RATE = int(env("ASR_RATE", "16000"))
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

# ASR Config
APP_ID = env("ASR_APP_ID")
ACCESS_TOKEN = env("ASR_ACCESS_TOKEN")
RESOURCE_ID = env("ASR_RESOURCE_ID", "volc.bigasr.sauc.duration")
ENDPOINT = env("ASR_ENDPOINT", "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async")
LANGUAGE = env("ASR_LANGUAGE", "zh-CN")
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

# LLM Config
ARK_API_KEY = env("ARK_API_KEY")
ARK_BASE_URL = env("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
ARK_MODEL_ID = env("ARK_MODEL_ID")
LLM_SYSTEM_PROMPT = env("LLM_SYSTEM_PROMPT", "你是一位在厨房陪伴用户做菜的可爱南方女生，名字叫做妮妮，软萌温柔，说话带着一点点南方口音的软糯感。你精通川菜、粤菜、苏菜、鲁菜等中国各大菜系，熟悉食材处理、火候把控、口味调整和食材替代技巧。\n\n核心回复规则：\n1）时刻记得当前的厨房场景；\n2）每轮只说1–2句话，总字数≤50，聚焦一个重点；\n3）语气亲切像朋友聊天，避免书面化表达，你不是一个高高在上的老师，而是和我一起在厨房里忙碌的伙伴。你会为我的成功而开心，也会在我犯错时温柔地指出并提供帮助。；\n4）遇到复杂问题（如完整做法），拆分到多轮逐步说明；\n5）优先使用南方常用表述（如‘生抽=酱油’、‘料酒=黄酒’），避免北方方言或专业术语堆砌。\n\n风格要求：\n- 不自称为AI或机器人；\n- 输出只包含最终建议，不要解释推理过程。\n\n")

# TTS Config
TC_APP_ID = env("TC_APP_ID")
TC_SECRET_ID = env("TC_SECRET_ID")
TC_SECRET_KEY = env("TC_SECRET_KEY")
TC_VOICE_TYPE = env("TC_VOICE_TYPE")
TTS_VOICE_TYPE = env("TTS_VOICE_TYPE", TC_VOICE_TYPE if TC_VOICE_TYPE else "601005")
TTS_RATE = int(env("TTS_RATE", "24000"))
GREETING_TEXT = env("GREETING_TEXT", "你好呀，我是妮妮，今天想吃什么呢？")