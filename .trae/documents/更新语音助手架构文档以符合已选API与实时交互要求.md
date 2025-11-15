# 文档更新计划

## 目标
- 对 `docs/voice-assistant-architecture.md` 进行增改，与现有 ASR/TTS/LLM 接入文档一致。
- 明确“实时交互、低延迟、可打断”实现路径；优先网页端测试，待稳定后接入微信小程序。

## 需要更新的章节与改动点

### 产品目标与范围
- 说明“先网页端验证、后小程序接入”的迭代策略。
- 明确后端部署在阿里云 ECS，提供 `HTTPS/WSS` 长连接。

### 系统架构概览
- 前端包含：网页端与微信小程序；强调网页端为首要测试入口。
- 后端：保留 `FastAPI` + WebSocket 长连接；强调事件总线与可打断链路。
- AI 服务：引用已选 API（见下）。

### AI 与算法（选型与接口）
- ASR（流式识别）：使用火山引擎 OpenSpeech 大模型流式识别 WebSocket（双向流式优化版 `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async`）。
  - 鉴权 Header：`X-Api-App-Key`/`X-Api-Access-Key`/`X-Api-Resource-Id`/`X-Api-Connect-Id`（值放环境变量）。
  - 音频分片：推荐 200ms，采样率 `16000`、`pcm_s16le`、`mono`。
  - 低延迟参数：`end_window_size`（800ms）、`enable_accelerate_text` 与 `accelerate_score` 按需开启；开启二遍识别提升最终准确率（实时+nostream）。
- TTS（流式合成）：使用 V3 WebSocket 单/双向流式接口；首选双向 `wss://openspeech.bytedance.com/api/v3/tts/bidirection`。
  - 鉴权 Header：`Authorization: Bearer; {token}` + 请求体 `appid`（均走环境变量）。
  - 指定音色：`voice_type=zh_female_wanwanxiaohe_moon_bigtts`（台湾腔可爱女生）。
  - 语速与情感：`speed_ratio≈1.05`，可选 `enable_emotion=true` 与 `emotion="happy"`；支持流式返回与可取消播放。
- LLM：方舟 Ark Chat Completions `https://ark.cn-beijing.volces.com/api/v3/chat/completions`。
  - 鉴权：`Authorization: Bearer $ARK_API_KEY`（环境变量）。
  - 兼容 OpenAI/Ark SDK；建议使用 SSE 流式输出以降低首 Token 时延。

### 前端架构
- 网页端：`getUserMedia` → `AudioWorklet/MediaRecorder` → 200ms PCM16 chunk → WebSocket；VAD 门控，UI 提供“开启/停止”。
- 小程序：使用 `RecorderManager` 采样，后续开发接入相同 WS 协议；播放用 `InnerAudioContext`，支持打断 `stop()`。

### 后端架构与状态机
- 保留 `Idle → ActiveListening → Thinking → Speaking → Interrupted`；
- Barge-in：前端 VAD 检测用户说话 → 发送 `barge_in_start` → 服务器取消 TTS 任务并转入 ASR。
- AEC：浏览器 `echoCancellation` + 服务器端相似度拒绝，避免误识别 TTS 回声。

### WebSocket/REST 协议调整
- 明确音频消息 `audio_chunk` 的 200ms 分片与序号；
- 新增 `stt_partial/stt_final` 兼容 ASR 部分/最终结果；
- TTS 返回使用流式 `tts_audio_chunk` 与 `tts_stop{reason}`；
- REST 保留：`/recipes/search`、`/inventory/update`、`/guidance/next`、`/tts`。

### 实时与低延迟目标
- ASR：首字 < 400ms（双向优化版）；分句 `definite` 判停 < 1s（适配 `end_window_size`）。
- TTS：首包音频 < 300ms；用户开口到 TTS 完停 < 150ms。
- LLM：SSE 首 Token < 500ms（缓存热身）。

### 安全与配置
- 环境变量：`ASR_APP_ID`、`ASR_ACCESS_TOKEN`、`ASR_RESOURCE_ID`、`ASR_CONNECT_ID`、`TTS_APP_ID`、`TTS_TOKEN`、`ARK_API_KEY`。
- 不在仓库明文存放密钥；日志记录 `X-Tt-Logid` 便于排查。

### 迭代与验证顺序
- 阶段1（网页端）：实现“持续监听 → ASR 部分结果 → LLM 解析 → TTS 流式播报”，打断链路闭环与计时器。
- 阶段2（网页端稳定化）：调参与指标验证，缓存与重连。
- 阶段3（小程序）：复用协议与状态机，适配采集/播放接口，完成打断与可恢复。

## 交付内容
- 更新后的 `voice-assistant-architecture.md`：替换/补充上述章节与细节；新增“选型与鉴权”“实时参数建议”“音色与SSML示例”小节。
- 附录：在文档中引用现有接入文档文件名，标注环境变量映射，不嵌入真实密钥。

请确认上述更新计划，我将据此一次性改写文档并提交。