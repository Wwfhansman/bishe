# 智能语音厨房助手（妮妮）

基于本地语音模型和 Ark LLM 的实时语音厨房助手。当前主版本由 `FastAPI` 后端、`Flutter` 客户端和一个用于联调的静态 Web 页面组成，支持实时语音识别、RAG 检索增强、多轮对话、语音合成和会话历史存储。

## 当前版本功能

- 本地 `sherpa-onnx` 流式语音识别
- 豆包 Ark Chat Completions 对话生成
- 本地 `piper` 中文语音合成
- 基于 `Chroma + BGE` 的烹饪知识库检索
- WebSocket 实时音频收发与播报打断
- `SQLite` 用户、会话和历史消息存储
- `Flutter` 登录、会话列表、语音主界面
- `frontend/index.html` 联调测试页

## 项目结构

```text
bishe/
├── backend/
│   ├── api/server.py          # FastAPI + WebSocket 入口
│   ├── config.py              # 环境变量和默认配置
│   ├── database.py            # SQLite 数据访问
│   ├── llm/llm_client.py      # Ark LLM 调用
│   ├── rag/                   # RAG 构建与检索
│   └── voice/                 # STT/TTS 抽象层与 provider
├── app-flutter/               # Flutter 客户端
├── frontend/index.html        # 浏览器联调页面
├── data/raw/                  # 烹饪知识库原始文本
├── scripts/                   # 模型下载和基准脚本
└── docs/                      # 设计与接口文档
```

## 环境准备

### 1. 安装后端依赖

```bash
pip install -r backend/requirements.txt
```

### 2. 下载本地模型

```bash
python scripts/download_models.py
```

默认会下载：

- STT：`models/stt/sherpa-onnx`
- TTS：`models/tts/piper-onnx`
- Embedding：`models/bge-small-zh-v1.5`

### 3. 配置 `.env`

项目根目录创建 `.env`：

```bash
ARK_API_KEY=你的ARK_API_KEY
ARK_MODEL_ID=doubao-1-5-pro-32k-250115
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3

# 可选
AUTH_JWT_SECRET=dev-secret
HF_ENDPOINT=https://hf-mirror.com
WECHAT_APPID=
WECHAT_SECRET=
```

## 启动方式

### 后端

```bash
uvicorn backend.api.server:app --host 127.0.0.1 --port 8000 --reload
```

启动后可访问：

- Web 调试页：`http://127.0.0.1:8000/frontend/index.html`
- Swagger：`http://127.0.0.1:8000/docs`

### Flutter 客户端

先安装依赖：

```bash
cd app-flutter
flutter pub get
```

本地桌面调试：

```bash
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000 --dart-define=WS_BASE_URL=ws://127.0.0.1:8000/ws/voice
```

Android 模拟器调试：

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000 --dart-define=WS_BASE_URL=ws://10.0.2.2:8000/ws/voice
```

真机通过 ngrok 调试：

```bash
flutter run --dart-define=API_BASE_URL=https://你的地址.ngrok-free.dev --dart-define=WS_BASE_URL=wss://你的地址.ngrok-free.dev/ws/voice
```

## 测试与诊断

后端测试：

```bash
python -m pytest backend/tests/
```

Flutter 检查：

```bash
cd app-flutter
flutter analyze
flutter test
```

性能脚本：

```bash
python scripts/bench_stt.py path/to/sample.wav
python scripts/bench_tts.py
python scripts/eval_barge_in.py path/to/manifest.jsonl --output-json eval_result.json
```

`eval_barge_in.py` 用于离线评估自适应打断检测。`manifest.jsonl` 每行一个 JSON，例如：

```json
{"path":"samples/interrupt_01.wav","label":"interrupt","expected_interrupt_ms":820,"tts_offset_ms":0}
{"path":"samples/echo_only_01.wav","label":"no_interrupt","tts_offset_ms":0}
```

## 当前版本说明

- 主客户端已经切换到 `Flutter`，旧版 Expo/小程序说明不再适用。
- `frontend/index.html` 仍然保留，主要用于协议联调和后端排障。
- `backend/voice/registry.json` 决定当前 STT/TTS provider。
- `voice_assistant.db` 和 `backend/rag/chroma_db/` 都是本地运行产物，不应提交。
