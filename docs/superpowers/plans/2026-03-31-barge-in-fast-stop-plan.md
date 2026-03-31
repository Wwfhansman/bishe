# 打断功能快停与整句保留实现计划

关联设计文档：

- `docs/superpowers/specs/2026-03-31-barge-in-fast-stop-design.md`

## 1. 目标

本计划对应的实现目标是：

1. 用户一开口时更快停掉当前 TTS。
2. 打断时尽量保住用户开头的几个字，不再频繁只识别到后半句。
3. 继续保持 `partial` 只用于显示/打断，`final` 才提交给 LLM。
4. 保留现有动态打断算法，不推翻论文主算法。

## 2. 实施范围

本轮实现只允许修改以下模块：

- `backend/api/voice_session.py`
- `backend/voice/barge_in_detector.py`
- 必要时补充对应测试文件

默认不改：

- Flutter 主逻辑
- Web 调试页逻辑
- STT provider 本体
- LLM/TTS provider 协议

如果实现中发现必须改 provider，则先停下来重新确认。

## 3. 实施阶段

### 阶段 A：补预滚动音频缓冲

目标：

- 在服务端持续保存最近 `300~500ms` 原始麦克风 PCM

任务：

1. 在 `VoiceSessionRunner` 中新增 pre-roll 缓冲字段
2. 在 `_receive_loop()` 中每次收音先写入该缓冲
3. 提供读取最近 pre-roll PCM 的辅助方法

验收：

- 不影响现有普通对话
- pre-roll 数据长度稳定、不会无限增长

### 阶段 B：新增“早停触发”路径

目标：

- 在不等待正式 confirmed 的情况下，更快停掉 TTS

任务：

1. 在 `barge_in_detector` 中增加工程级 `EARLY_TRIGGER`
2. 让 `EARLY_TRIGGER` 的门槛低于 `CONFIRMED`
3. 在 `voice_session.py` 中接入：
   - `EARLY_TRIGGER` -> `_interrupt_now()`
   - `CONFIRMED` -> `_confirm_interrupt()`

验收：

- 打断时能更早看到 `tts_reset`
- `CONFIRMED` 语义仍保留，用于论文与日志

### 阶段 C：补头并重建用户 utterance

目标：

- 打断发生后，将 pre-roll 音频并入当前用户语音开头

任务：

1. 新增“本轮用户语音是否已注入 pre-roll”的状态位
2. 在打断后进入用户收集状态时：
   - 如 STT 需 reset，则先 reset
   - 立刻将 pre-roll 回灌到 STT
   - 再继续喂当前帧与后续实时音频
3. 确保 pre-roll 只注入一次

验收：

- 打断句的 final 文本更完整
- 不出现明显重复识别

### 阶段 D：保持 final-only 提交

目标：

- 不因早停而把 partial 直接送给 LLM

任务：

1. 保持 `partial` 仅用于前端展示
2. `final` 才进入 `_handle_reply()`
3. 检查现有 suppressed final / duplicate guard 是否仍然成立

验收：

- 不出现“半句就触发 LLM 回复”
- 不出现同一句 final 重复提交

### 阶段 E：日志与测试

目标：

- 让这轮调优可验证、可回归

任务：

1. 增加服务端关键日志/事件观测点：
   - `EARLY_TRIGGER`
   - `CONFIRMED`
   - `tts_reset`
   - `tts_interrupted`
   - pre-roll 是否已注入
2. 补单元测试或最小状态测试：
   - pre-roll 缓冲长度控制
   - early trigger 先于 confirmed
   - 打断后 pre-roll 仅注入一次
   - final-only 提交不变

验收：

- 能清楚区分“早停发生了但 final 不完整”还是“根本没触发早停”

## 4. 参数策略

第一轮实现先用固定默认值，不做大量调参：

- `pre_roll_ms = 400`
- `early_trigger_min_frames = 2`
- `early_trigger_energy_scale = 1.4`

原则：

- 先打通链路
- 再用真机日志做微调

## 5. 测试顺序

实现后按下面顺序验证：

1. greeting 正常播报
2. 不说话时不应频繁自动停播
3. 说固定短句打断：
   - `你好`
   - `你叫什么名字`
   - `你重新说一遍刚刚那句话`
4. 检查事件链：
   - `tts_start`
   - `tts_reset`
   - `tts_interrupted`
   - `asr_partial`
   - `asr_text`
5. 对比 final 文本是否比当前更完整

## 6. 风险控制

### 风险 1：误打断增加

处理方式：

- 先接受，作为“更快停播优先”的 trade-off
- 通过 `EARLY_TRIGGER` 与 `CONFIRMED` 分层观测来源

### 风险 2：回灌 pre-roll 造成重复或脏识别

处理方式：

- 明确“仅注入一次”
- 对 final 保持去重保护

### 风险 3：状态机再次复杂化

处理方式：

- 只在 `voice_session.py` 聚合状态
- 不把相同职责拆散到 Flutter 与后端两边

## 7. 完成标准

本轮实现完成的标准是：

1. 真机打断时，TTS 停播明显更快
2. 打断后 final 文本比当前更完整
3. 仍然保持 `final -> LLM`
4. 不引入新的“对话彻底卡死”回归

## 8. 执行顺序摘要

1. 先加 pre-roll buffer
2. 再加 `EARLY_TRIGGER`
3. 再做打断后 pre-roll 回灌
4. 最后补测试和日志

这样可以把风险压在最小范围内，并且每一步都能单独验证。
