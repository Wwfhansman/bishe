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

### 3.1 架构选型
*   **向量数据库**：**ChromaDB**
    *   **理由**：开源、轻量、支持本地持久化存储，Python 生态友好，无需复杂的服务器端配置。
*   **Embedding 模型**：**火山引擎 (Volcengine) Embedding API**
    *   **理由**：
        *   **节省算力**：本地运行 Embedding 模型（如 BERT/m3e）会消耗大量 CPU/RAM，可能导致 2G 内存的服务器卡顿。使用云端 API 可将负载卸载到云端。
        *   **生态统一**：与现有的 ASR 和 LLM 同属火山引擎生态，便于管理。

### 3.2 知识库构建流程
1.  **数据源**：收集烹饪相关的文本数据（菜谱、技巧、营养知识）。
2.  **切片 (Chunking)**：将长文本按语义或字符数切分为短片段（Chunk）。
3.  **向量化 (Embedding)**：调用火山引擎 API 将 Text Chunk 转换为 Vector。
4.  **存储**：将 Vector 和原始 Text 存入 ChromaDB。

### 3.3 检索与生成流程
1.  **用户提问**：用户语音转文字得到 Query。
2.  **Query 向量化**：调用火山引擎 API 将 Query 转换为 Vector。
3.  **相似度搜索**：在 ChromaDB 中检索与 Query Vector 最相似的 Top-K 个知识片段。
4.  **Prompt 组装**：
    ```text
    系统提示词 + 
    [参考知识库]：
    ... (Top-K 片段) ...
    [用户问题]：
    ...
    ```
5.  **生成回复**：LLM 基于增强后的 Prompt 生成回答。

## 4. 性能优化策略 (Performance)
*   **异步并发**：LLM 请求和 RAG 检索均采用异步或线程池执行，避免阻塞主线程导致音频卡顿。
*   **流式输出**：LLM 生成与 TTS 合成并行流水线工作，首字生成即开始合成音频，降低首字延迟 (TTFT)。
