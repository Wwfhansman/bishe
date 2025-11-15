# 厨房语音助手：总体功能与技术架构

## 产品目标与范围
- 面向中文厨房场景的语音助手，支持持续监听、可打断播报、对话记忆。
- 终端包含网页端与微信小程序；云服务与本地推理可切换，保证演示与落地。
- 后端部署在阿里云服务器（ECS），对外提供 HTTPS 与长连接服务。
- 迭代策略：优先网页端完成功能测试与调参，稳定后再开发微信小程序接入相同协议。

## 核心用户体验
- 一键开启持续监听，无需重复点击；说“停止/做完菜”或手动关闭结束。
- 做饭过程中自然对话：播报时可随时打断提问，系统立即停播并回答。
- 记住当前菜谱步骤、已完成动作、用户偏好与库存；支持“下一步/重复/暂停/继续/设定计时”。
- 在油烟机、水声等噪声环境保持较高识别率与低延迟反馈。
- 语音回答使用台湾腔可爱女生音色，营造温馨的家庭厨房氛围。

## 功能清单
- 语音输入与实时识别（STT），支持部分结果与连续识别。
- 菜谱检索与推荐（RAG），解释推荐理由、缺失食材与替代建议。
- 分步烹饪指导与计时器提醒，支持指令控制与自然问答。
- 用户库存管理与偏好记录，同义词与替代规则管理。
- 可打断的播报（TTS），中断后可恢复或等待继续指令。

## 系统架构概览
- 前端 Web：`React/Vue + Vite`，`WebAudio/WebRTC` 采集，`WebSocket` 双向流。
- 前端 微信小程序：使用录音接口与 `WebSocket`，与后端协议保持一致；音频播放采用 `InnerAudioContext`。
- 会话后端：`FastAPI`（Python）提供长连接与 REST 接口；异步事件总线调度。
- AI 服务：云端 STT/TTS、LLM；本地备选 `Whisper`、`Ollama`；向量库 `Chroma`。
- 数据层：`SQLite`（菜谱、步骤、食材、替代规则、用户与库存）；会话态与计时器缓存 `Redis` 或内存。
- 部署：阿里云服务器（ECS）+ `Nginx` 反向代理 + `HTTPS`（阿里云证书或 Let’s Encrypt）。
 - 开发顺序：网页端优先实现与验收，随后小程序复用协议快速接入。

## 前端架构
- 音频链路：`getUserMedia` 采集 → `AudioWorklet/MediaRecorder` → 20ms PCM16 分片通过 `WebSocket` 上传。
- 监听模式：唤醒词模式与持续倾听模式可选；支持“开启监听/停止”。
- UI 组件：录音按钮、推荐菜列表、库存管理、烹饪步骤面板与计时器、播报控制。
- TTS 播放：`AudioContext` 控制，支持 `fade-out` 停播与与 AEC 联动，避免回声自识别。
- 微信小程序：`RecorderManager` 采集音频、`WebSocket` 传输；TTS 播放使用 `InnerAudioContext`，收到打断事件立即 `stop()` 并进入识别。
 - 实时分片：与 ASR 推荐对齐，网页端分片时长建议 `≈200ms`，同时保留 20ms 作预研选项。

## 后端架构
- 长连接：`WS /dialog` 持续连接承载音频、识别、播报与指令；REST 提供搜索与库存接口。
- 事件总线：`asyncio` 队列模块化处理 `stt_stream`、`nlu`、`rag_search`、`planner`、`tts_stream`、`session_state`。
- 打断机制：收到前端 `barge_in` 事件或检测到用户开口，立即取消当前 TTS 任务并转入识别。
- 会话状态机：`Idle → ActiveListening → Thinking → Speaking → Interrupted`；静默或指令结束。

## AI 与算法（选型与接口）
- STT（实时识别）：火山引擎 OpenSpeech 大模型流式识别 WebSocket，优先双向流式优化版 `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async`。
  - 鉴权 Header：`X-Api-App-Key`、`X-Api-Access-Key`、`X-Api-Resource-Id`、`X-Api-Connect-Id`（值走环境变量）。
  - 音频参数：`pcm_s16le`、采样率 `16000`、单声道；推荐分包 `200ms`，发包间隔 `100~200ms`。
  - 低延迟/准确率：开启二遍识别（实时+nostream）、`end_window_size≈800ms`、按需启用 `enable_accelerate_text` 与 `accelerate_score` 提升首字速度。
- TTS（流式合成）：使用 V3 WebSocket，优先 `wss://openspeech.bytedance.com/api/v3/tts/bidirection`（双向流式）。
  - 鉴权：`Authorization: Bearer; {token}`（环境变量）与请求体 `appid`。
  - 指定音色：`voice_type=zh_female_wanwanxiaohe_moon_bigtts`（台湾腔可爱女生），`speed_ratio≈1.05`；可选 `enable_emotion=true`、`emotion="happy"` 营造温馨氛围。
  - 播报：流式返回音频片段；客户端可随时取消以实现打断。
- LLM：方舟 Ark Chat Completions `https://ark.cn-beijing.volces.com/api/v3/chat/completions`（兼容 OpenAI/Ark SDK）。
  - 鉴权：`Authorization: Bearer $ARK_API_KEY`（环境变量）。
  - 建议使用 SSE 流式输出降低首 Token 时延；消息格式按 Chat Completions 规范。
- NLU：LLM 结构化解析意图与实体（食材、调料、数量/单位、设备、时间、温度、偏好）；规则后处理与同义词映射（如“生抽=酱油”）。
- 检索（RAG）：嵌入模型 `bge-m3`；双通道召回（向量检索 + 关键词过滤），打分维度含食材匹配率、缺失项、设备匹配、时长难度、用户偏好。
- 解释生成：LLM 对 Top-K 菜谱生成推荐理由与替代建议。

## 选型与鉴权配置
- 环境变量：`ASR_APP_ID`、`ASR_ACCESS_TOKEN`、`ASR_RESOURCE_ID`、`ASR_CONNECT_ID`、`TTS_APP_ID`、`TTS_TOKEN`、`ARK_API_KEY`。
- 密钥仅在后端环境变量中配置；不在仓库明文存放；记录服务端返回 `X-Tt-Logid` 便于排查。

## 数据与存储
- 结构化表（示例）：
  - `recipe(id, title, desc, duration_min, difficulty, device_tags, cuisine_tags)`
  - `ingredient(id, name, aliases, category)`
  - `recipe_ingredient(recipe_id, ingredient_id, amount_text, required_bool)`
  - `steps(recipe_id, step_index, action_type, text, timer_sec, equipment)`
  - `user(id, name, prefs_json)`
  - `user_pantry(user_id, ingredient_id, amount_text, updated_at)`
- 向量库：`Chroma` 存菜谱与步骤嵌入；导入或更新后自动生成嵌入。
- 同义词与替代规则：维护 `aliases` 与 `substitution` 配置，优先结构化规则，LLM 作为建议来源。

## 会话状态机与计时器
- 状态字段：`current_recipe_id`、`step_index`、`completed_steps[]`、`last_user_intent`、`pantry_snapshot`。
- 步骤标准化：`Action/Check/Timer/Note` 四类，便于播报与计时。
- 计时器：后端异步任务，完成时推送 `timer_done` 并触发 TTS 提醒。
- 打断后的恢复：问答完成后返回到上一未完成步骤或等待“继续”指令。

## WebSocket 与 REST 接口
- 客户端→服务端：
  - `start_listen {mode:'keyword'|'continuous'}`
  - `audio_chunk {pcm16_le, seq, ts, duration_ms:200}`
  - `barge_in_start {ts}`
  - `user_cmd {type:'next|repeat|pause|resume|stop'}`
- 服务端→客户端：
  - `stt_partial {text, confidence, seq}`
  - `stt_final {text, confidence, ts}`
  - `nlu {intent, entities, slots, normalized_text}`
  - `recommendations {items:[{recipe_id,title,reason,missing,substitutions}]}`
  - `guidance_step {step_index, text, action_type, timer_sec}`
  - `tts_audio_chunk {pcm16, seq}` / `tts_stop {reason:'barge_in|finish'}`
  - `session_state {recipe_id, step_index, timers[]}`
- REST：
  - `POST /recipes/search` 食材与偏好检索菜谱
  - `POST /inventory/update` 更新用户库存
  - `POST /guidance/next` 推进并返回下一步
  - `GET /tts` 文本转语音调试

## 噪声鲁棒与打断
- 采集：`echoCancellation`、`noiseSuppression`、`autoGainControl` 打开；采样率 16kHz，帧长 20ms。
- VAD：前端 `WebRTC VAD` 门控，后端 `Silero VAD` 二次确认，双阈值自适应环境噪声。
- 回声抑制：浏览器 AEC + 服务器端相似度拒绝；TTS 播放音量上限与淡出停止。
- 打断时延：目标用户开口到 TTS 完全停止 < 150ms；回答开始 < 600ms。

## 安全与隐私
- 仅保存文本与操作摘要，不存原始音频；全程 `HTTPS/WSS` 传输。
- 秘钥保存在后端环境变量；前端不暴露；日志脱敏。
- 会话态定期清理与长连接健康检查。

## 部署与运维
- 单机演示：`FastAPI + SQLite + Chroma`，云 STT/TTS 与 LLM；`uvicorn` 运行。
- 云端演示（阿里云）：ECS（Ubuntu/CentOS）部署后端与向量库，前端静态资源可放在 OSS；`Nginx` 反代与 `HTTPS`（阿里云免费证书或 Let’s Encrypt）；开放 `WSS` 端口与安全组规则；健康检查与断线重连策略；日志与指标采集。

## 指标与评估
- 识别：厨房噪声下词错率与指令识别成功率。
- 交互：首条推荐延迟、打断响应时延、连续互动稳定性。
- 推荐：可做率（缺失≤1且可替代）、用户满意度与解释可理解度。
 - 实时：ASR 首字/尾字时延与分句 `definite` 产出时延；TTS 首包时延；LLM 首 Token 时延。

## 迭代里程碑与 MVP
- 第1周：搭建前后端与 WS；接入云 STT/TTS；完成持续监听闭环。
- 第2周：状态机与打断；VAD 与 AEC 联动；静默结束逻辑。
- 第3周：NLU/指令集与同义映射；菜谱库与 RAG；Top-K 推荐与解释。
- 第4周：分步指导与计时器；错误兜底与移动端适配。
- 第5周：调参与评估；演示部署与小程序接口对齐。
- MVP：持续监听→口述食材→返回 3 个可做菜→选择菜谱→分步播报并可打断→完成总结。

## TTS 语音风格示例（SSML 与参数）
- 音色：`voice_type=zh_female_wanwanxiaohe_moon_bigtts`，`speed_ratio=1.05`，可选 `emotion="happy"`。
- 文本类型：`text_type=ssml` 可加入停顿与强调，例如：

```xml
<speak>
  <p>哈囉～我們今天來做<span>番茄炒蛋</span>喔！</p>
  <break time="500ms"/>
  <p>先把番茄切塊，蛋液加一點點鹽，攪拌均勻～</p>
  <break time="400ms"/>
  <p>熱鍋下油，先把蛋滑熟後盛出，接著炒番茄，再把蛋回鍋拌勻就完成啦！</p>
</speak>
```
