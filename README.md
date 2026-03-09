# 智能语音厨房助手（妮妮）

第一步：在 app-mobile 目录下打开终端，运行：
bash
npx expo start
第二步：在终端里按下 a 键，Expo 会自动在您的 Android 模拟器上打开这个 App。
第三步：您只要在编辑器（如 VS Code）里保存（Ctrl+S）代码，模拟器上的画面就会瞬间自动刷新出最新效果！您刚才看到的那个红色报错界面，只要改对了代码一保存，它也会自动变成正常的界面。
基于本地 AI 模型的实时语音交互厨房助手，支持语音识别、智能对话、语音合成和知识库检索，通过 FastAPI + WebSocket 提供服务，前端支持 Web 和微信小程序。

## 功能特性

- **语音识别（STT）**：本地 sherpa-onnx 模型，实时流式识别，中英双语支持
- **智能对话（LLM）**：豆包大模型，精通中国八大菜系的厨房助手人设
- **语音合成（TTS）**：本地 piper 模型，中文语音实时合成
- **知识库检索（RAG）**：Chroma + BGE 向量嵌入，本地烹饪知识库增强回答
- **语音打断**：用户说话时自动打断 AI 回复，实现自然对话
- **多端支持**：Web 前端 + 微信小程序
- **会话管理**：SQLite 存储用户/会话/对话历史

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端框架 | FastAPI + WebSocket |
| 语音识别 | sherpa-onnx (本地 ONNX 模型) |
| 语音合成 | piper-tts (本地 ONNX 模型) |
| 大语言模型 | 豆包 Doubao (Ark API) |
| 知识增强 | ChromaDB + BGE-small-zh-v1.5 |
| 数据库 | SQLite |
| 前端 | HTML/JS (Web) + 微信小程序 |

## 项目结构

```
bishe/
├── backend/
│   ├── api/server.py          # FastAPI 主服务（WebSocket 语音通道 + REST API）
│   ├── config.py              # 环境变量配置
│   ├── database.py            # SQLite 数据库管理
│   ├── llm/llm_client.py      # 豆包 LLM 调用
│   ├── rag/
│   │   ├── retriever.py       # RAG 知识检索
│   │   └── offline_build.py   # 离线构建知识库
│   └── voice/                 # 语音服务抽象层
│       ├── protocols.py       # STT/TTS 接口协议
│       ├── factory.py         # 服务工厂
│       ├── registry.json      # Provider 注册表
│       └── providers/
│           ├── sherpa_onnx_stt.py  # 本地 STT 实现
│           └── piper_onnx_tts.py   # 本地 TTS 实现
├── frontend/index.html        # Web 前端（语音助手界面）
├── wxapp/                     # 微信小程序
├── models/                    # 本地模型（不上传 Git，需自行下载）
│   ├── stt/sherpa-onnx/       # STT 模型文件
│   ├── tts/piper-onnx/        # TTS 模型文件
│   └── bge-small-zh-v1.5/     # Embedding 模型
├── data/raw/                  # 知识库原始数据
├── scripts/
│   ├── download_models.py     # 模型自动下载脚本
│   ├── bench_stt.py           # STT 性能基准测试
│   └── bench_tts.py           # TTS 性能基准测试
└── docs/                      # 设计文档与 API 文档
```

## 快速开始

### 1) 克隆项目

```bash
git clone https://github.com/Wwfhansman/bishe.git
cd bishe
```

### 2) 创建虚拟环境并安装依赖

```bash
python -m venv venv

# Windows PowerShell:
.\venv\Scripts\Activate.ps1

# Linux / Mac:
source venv/bin/activate

pip install -r backend/requirements.txt
```

### 3) 下载本地模型

模型文件较大（约 500MB），不包含在 Git 仓库中，使用自动下载脚本：

```bash
python scripts/download_models.py
```

脚本会自动下载以下三个模型到 `models/` 目录：

| 模型 | 大小 | 说明 |
|------|------|------|
| sherpa-onnx zipformer | ~300MB | STT 语音识别（中英双语流式） |
| piper huayan | ~60MB | TTS 中文语音合成 |
| bge-small-zh-v1.5 | ~100MB | Embedding 向量化（RAG 用） |

> **国内加速**：脚本默认使用 HuggingFace 镜像 `hf-mirror.com`。如需更换，设置环境变量：
> ```bash
> set HF_ENDPOINT=https://hf-mirror.com   # Windows
> export HF_ENDPOINT=https://hf-mirror.com # Linux/Mac
> ```

也可以单独下载某个模型：
```bash
python scripts/download_models.py --stt     # 只下载 STT 模型
python scripts/download_models.py --tts     # 只下载 TTS 模型
python scripts/download_models.py --embed   # 只下载 Embedding 模型
```

### 4) 配置环境变量

在项目根目录创建 `.env` 文件（此文件不上传 Git）：

```bash
# 必填：豆包大模型 API
ARK_API_KEY=你的ARK_API_KEY
ARK_MODEL_ID=doubao-1-5-pro-32k-250115
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3

# 可选：HuggingFace 镜像
HF_ENDPOINT=https://hf-mirror.com

# 可选：微信小程序（不用小程序可以不填）
WECHAT_APPID=你的微信APPID
WECHAT_SECRET=你的微信SECRET
```

### 5) 启动服务

```bash
uvicorn backend.api.server:app --reload
```

服务启动后访问：
- **Web 界面**: http://localhost:8000/frontend/index.html
- **API 文档**: http://localhost:8000/docs

## 交互流程

```
用户说话 → 麦克风采集 PCM 音频
    → WebSocket 发送到后端
    → sherpa-onnx 实时语音识别
    → RAG 知识库检索相关内容
    → 豆包 LLM 生成回复
    → piper TTS 合成语音
    → WebSocket 推送音频流到前端
    → 前端播放 AI 语音回复
```

支持**语音打断**：用户在 AI 说话期间开口说话（≥1秒），AI 会自动停止当前回复并响应新的输入。

## 常用命令

```bash
# 启动开发服务器
uvicorn backend.api.server:app --reload

# 运行测试
pytest backend/tests/

# STT 性能测试
python scripts/bench_stt.py path/to/16k_mono.wav

# TTS 性能测试
python scripts/bench_tts.py
```

## 系统要求

- Python 3.9+
- Windows / Linux
- 4GB+ 内存（本地模型需要）
- 豆包大模型 API Key（[火山方舟](https://www.volcengine.com/docs/82379)）

## 许可证

本项目仅供学术研究使用。
