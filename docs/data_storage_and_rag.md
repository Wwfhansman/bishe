# 数据存储与 RAG 方案设计文档

## 1. 核心目标
构建一个具备**上下文记忆**和**专业烹饪知识库**的语音助手。考虑到毕业设计的演示需求及服务器性能限制（阿里云 2核2G），方案需兼顾**轻量化**、**低延迟**和**易部署**。

## 2. 上下文记忆模块 (Context Memory)

### 2.1 选型：SQLite
*   **理由**：
    *   **轻量级**：无需单独安装数据库服务（如 MySQL/PostgreSQL），单文件（`chat.db`）即可运行。
    *   **零维护**：适合单机部署和毕设演示。
    *   **性能足够**：对于单用户或少量并发用户的对话历史存取，性能完全满足需求。

### 2.2 数据库设计
*   **表名**：`conversations`
*   **字段设计**：
    *   `id`: INTEGER PRIMARY KEY (自增主键)
    *   `user_id`: TEXT (用户唯一标识，由前端生成并存储在 localStorage)
    *   `role`: TEXT (角色，枚举值：`user` / `assistant`)
    *   `content`: TEXT (对话内容)
    *   `timestamp`: DATETIME (创建时间，默认当前时间)

### 2.3 交互流程
1.  **连接建立**：前端 WebSocket 连接时携带 `user_id`。
2.  **加载历史**：后端从 SQLite 读取该 `user_id` 最近的 N 条（如 10 条）记录。
3.  **对话存储**：
    *   收到用户语音转文字后，存入 `role='user'` 记录。
    *   LLM 生成回复后，存入 `role='assistant'` 记录。
4.  **LLM 调用**：将“历史记录 + 当前问题”组合发送给 LLM，实现多轮对话。

---

## 3. RAG 增强检索模块 (Retrieval-Augmented Generation)

### 3.1 架构选型（ChromaDB 持久化 + 本地中文小模型）
- 向量化模型：`bge-small-zh v1.5`（384 维），优先通过 `fastembed`（ONNX，CPU 友好、内存占用低）。
- 向量数据库：`ChromaDB` 持久化客户端，路径例如 `backend/rag/chroma_db/`。集合名建议使用 `kb`，距离度量配置 `metadata={'hnsw:space': 'cosine'}`。
- 运行方式：离线在本地批量向量化知识库并将“文本 + 向量 + 元信息”一次性写入 Chroma；线上仅对 Query 在本地向量化，在 Chroma 中进行 Top-K 检索。

### 3.2 离线构建流程（在本地）
1. 数据收集：整理烹饪相关文本（菜谱、技巧、营养、食材百科），保留来源与主题标记。
2. 切片策略：按 512–1024 汉字或句子边界切分，去除噪声与重复；为每个 Chunk 生成唯一 `id` 与 `tags`。
3. 向量化：加载本地嵌入模型，批量生成 384 维 `float32` 向量。
4. 写入 Chroma：创建持久化客户端与集合，将 `documents/ids/metadatas/embeddings` 一次性加入集合；目录如 `backend/rag/chroma_db/`。
5. 验证与评估：抽样检索检查相关性与覆盖率，记录评估日志与版本号（如 `kb/2025-11-26`）。

示例代码（离线构建到 Chroma）：
```python
# 安装：pip install chromadb fastembed onnxruntime numpy tqdm
import chromadb, json, numpy as np
from fastembed import TextEmbedding
from tqdm import tqdm

chunks = load_chunks_from_folder('data/')  # 返回 [{'id': 'xxx', 'text': '...', 'tags': ['...'], 'source': '...'}]
texts = [c['text'] for c in chunks]
ids = [c['id'] for c in chunks]
metas = [{"source": c.get("source"), "tags": c.get("tags", [])} for c in chunks]

embedding = TextEmbedding(model_name="bge-small-zh-v1.5")
vectors = list(embedding.embed(texts))  # List[List[float]] 长度=384

client = chromadb.PersistentClient(path="backend/rag/chroma_db")
coll = client.get_or_create_collection(name="kb", metadata={"hnsw:space": "cosine"})
coll.add(documents=texts, ids=ids, metadatas=metas, embeddings=vectors)
```

### 3.3 在线查询流程（服务器 2核2G）
- 启动加载：服务启动时创建 `chromadb.PersistentClient(path="backend/rag/chroma_db")` 并获取集合 `kb`；预热本地嵌入模型单例。
- 每次提问：
  - 使用本地嵌入模型对 ASR 文本生成 384 维向量。
  - 调用 `coll.query(query_embeddings=[vec], n_results=5)` 获取 Top-K。
  - 取出 `documents/metadatas` 组装 Prompt（系统提示词 + Top-K 摘要 + 用户问题），调用 LLM 生成回复。
- 并发与资源：
  - 限制嵌入并发（如 4），单例模型避免重复加载；对热门 Query 做向量缓存 5–10 分钟。
  - 如果数据规模较大，合理配置集合与分片（多个集合按主题拆分），分批加载与查询。

### 3.4 参数与性能建议
- 模型：`bge-small-zh v1.5`（fastembed/ONNX），权重约 20–30MB；加载后内存峰值在 200–300MB（含运行时）。
- Chroma 集合：`metadata={'hnsw:space':'cosine'}`，Top-K=5；对于较大规模数据，建议拆分多个集合（菜谱/技巧/营养）。
- 延迟：Query 向量化 20–50ms；Chroma 查询 10–30ms；总体<120ms（不含 LLM）。
- 规模：50k Chunk 在 2GB 内存内可运行；如更大，分集合与按主题检索可控资源占用。

### 3.5 版本管理与部署
- 产物版本：为 `backend/rag/chroma_db/` 标注版本号与时间戳（如 `backend/rag/chroma_db/kb_2025-11-26/`）。
- 回滚策略：保留上一个版本目录，出现问题时切换配置指针或软链接到稳定版本。
- 部署流程：
  - 本地向量化并写入 Chroma 持久目录 → 打包上传到服务器指定路径 → 服务重启并加载集合。
  - 启动时进行集合一致性校验（元素数量与元数据条数一致）。

## 4. 性能优化策略 (Performance)
- 线程池与限流：对 Query 向量化与索引检索分别设置并发上限，避免 CPU 抢占导致端到端延迟上升。
- 模型预热：服务启动时完成模型初始化，避免首请求冷启动抖动；若内存紧张，优先选择 ONNX/fastembed。
- 索引预加载：启动阶段完成索引加载并设置 `ef`，避免运行时频繁切换参数。
- 缓存：对热门 Query 做向量缓存与 Top-K 结果缓存（短 TTL），进一步降低负载。
- 降级策略：在高负载或内存不足时降低 Top-K、调低 `ef`，或启用分片索引。
