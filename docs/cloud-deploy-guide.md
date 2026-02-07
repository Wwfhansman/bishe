 # 云端部署指南（后端）
 
 本文用于在云服务器上部署后端服务，确保语音链路与 RAG 稳定运行，避免因外网下载模型导致阻塞。
 
 ## 1. 服务器准备
 
 - 系统建议：Ubuntu 20.04/22.04 或 CentOS 7/8
 - Python：3.10+
 - 端口：开放 8000（或你自定义端口）
 
 ## 2. 拉取代码
 
 ```bash
 git clone <your-repo-url>
 cd bishe
 ```
 
 ## 3. 安装依赖
 
 ```bash
 python -m venv venv
 source venv/bin/activate
 pip install -r backend/requirements.txt
 ```
 
 ## 4. 配置环境变量
 
 方式一：使用系统环境变量
 
 ```bash
 export ASR_APP_ID=你的ASR_APP_ID
 export ASR_ACCESS_TOKEN=你的ASR_ACCESS_TOKEN
 export ASR_RESOURCE_ID=volc.bigasr.sauc.duration
 export ASR_ENDPOINT=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
 
 export ARK_API_KEY=你的ARK_API_KEY
 export ARK_MODEL_ID=你的ARK_MODEL_ID
 export ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
 
 export TC_APP_ID=你的TC_APP_ID
 export TC_SECRET_ID=你的TC_SECRET_ID
 export TC_SECRET_KEY=你的TC_SECRET_KEY
 export TTS_VOICE_TYPE=601005
 
 export HF_ENDPOINT=https://hf-mirror.com
 export EMBED_LOCAL_DIR=/opt/models/bge-small-zh-v1.5
 ```
 
 方式二：使用 .env 文件（服务启动目录下生效）
 
 ```bash
 ASR_APP_ID=你的ASR_APP_ID
 ASR_ACCESS_TOKEN=你的ASR_ACCESS_TOKEN
 ASR_RESOURCE_ID=volc.bigasr.sauc.duration
 ASR_ENDPOINT=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
 
 ARK_API_KEY=你的ARK_API_KEY
 ARK_MODEL_ID=你的ARK_MODEL_ID
 ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
 
 TC_APP_ID=你的TC_APP_ID
 TC_SECRET_ID=你的TC_SECRET_ID
 TC_SECRET_KEY=你的TC_SECRET_KEY
 TTS_VOICE_TYPE=601005
 
 HF_ENDPOINT=https://hf-mirror.com
 EMBED_LOCAL_DIR=/opt/models/bge-small-zh-v1.5
 ```
 
 ## 5. 本地化嵌入模型（RAG 必做）
 
 若不做本地化，服务会尝试从外网下载模型，容易因镜像不可用而阻塞。
 
 选择其一：
 
 ### 方式 A：直接下载到服务器
 
 ```bash
 mkdir -p /opt/models/bge-small-zh-v1.5
 python - << 'PY'
 from huggingface_hub import snapshot_download
 snapshot_download(
     repo_id="BAAI/bge-small-zh-v1.5",
     local_dir="/opt/models/bge-small-zh-v1.5",
     local_dir_use_symlinks=False
 )
 PY
 ```
 
 ### 方式 B：本地下载后上传
 
 ```bash
 scp -r ./bge-small-zh-v1.5 user@server:/opt/models/
 ```
 
 ## 6. 离线运行建议（可选但推荐）
 
 ```bash
 export TRANSFORMERS_OFFLINE=1
 export HF_HUB_OFFLINE=1
 export HF_HOME=/opt/hf_cache
 export TRANSFORMERS_CACHE=/opt/hf_cache
 ```
 
 ## 7. 启动服务
 
 ```bash
 uvicorn backend.api.server:app --host 0.0.0.0 --port 8000
 ```
 
 浏览器访问：
 
 ```
 http://<server-ip>:8000/frontend/index.html
 ```
 
 ## 8. 常见问题
 
 - 看到 “HF mirror 502”  
   说明 RAG 在在线下载模型，检查 EMBED_LOCAL_DIR 是否指向正确的本地模型目录。
 
 - 可以 TTS 播报但无回复  
   通常是 RAG 卡住或 LLM 请求失败，检查服务日志与环境变量配置。
 
 - WebSocket 无法连接  
   检查云服务器安全组、端口开放以及 Nginx 反向代理配置。
