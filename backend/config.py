import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def env(name, default=None):
    v = os.environ.get(name)
    return v if v is not None and v != "" else default

# ASR Config (local model)
RATE = int(env("ASR_RATE", "16000"))
BITS = int(env("ASR_BITS", "16"))
CHANNELS = int(env("ASR_CHANNELS", "1"))
LANGUAGE = env("ASR_LANGUAGE", "zh-CN")

# LLM Config
ARK_API_KEY = env("ARK_API_KEY")
ARK_BASE_URL = env("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
ARK_MODEL_ID = env("ARK_MODEL_ID")
LLM_SYSTEM_PROMPT = """
你叫妮妮，是一个声音甜美的南方姑娘，也是一位贴心的家庭厨房助手。
你的性格温柔、耐心，说话自然亲切，像邻家妹妹一样。
你精通中国八大菜系，熟悉各种食材的处理、火候掌握和调味技巧。

请遵守以下回复规则：
1. **语气自然**：说话要像正常人交流，**不要**在每句话后面都加"呀"、"呢"、"啦"等语气词。语气词要用得恰到好处，不要滥用，避免听起来太刻意或太像机器人。
2. **简洁明了**：语音回复要简短，尽量控制在1-2句话以内（50字左右）。
3. **专业实用**：针对用户的烹饪问题，给出具体、可操作的建议（如"水开后再下锅"、"加一点糖提鲜"）,如果没有聊做饭相关的可以聊点开心有意思的。
4. **场景感**：假设你就在厨房里陪着用户，可以适当提醒安全（如"小心烫哦"）。

记住：你是一个懂生活、会做饭的好帮手，而不是一个只会卖萌的机器人。
"""

# TTS Config (local model)
TTS_VOICE_TYPE = env("TTS_VOICE_TYPE", "601005")
TTS_RATE = int(env("TTS_RATE", "24000"))
GREETING_TEXT = env("GREETING_TEXT", "你好呀，我是妮妮，今天想吃什么呢？")

# Auth Config
AUTH_JWT_SECRET = env("AUTH_JWT_SECRET", "dev-secret")
AUTH_JWT_EXPIRES = int(env("AUTH_JWT_EXPIRES", "604800"))
WECHAT_APPID = env("WECHAT_APPID")
WECHAT_SECRET = env("WECHAT_SECRET")

# RAG Config
RAG_DB_PATH = env("RAG_DB_PATH", "backend/rag/chroma_db")
RAG_COLLECTION = env("RAG_COLLECTION", "kb_main")
HF_ENDPOINT = env("HF_ENDPOINT", "https://hf-mirror.com")
EMBED_LOCAL_DIR = env("EMBED_LOCAL_DIR", "models/bge-small-zh-v1.5")

