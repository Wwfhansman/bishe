# 自适应打断检测算法设计与实现指南

## 1. 文档目标

本文档用于同时指导两件事：

1. 后续代码实现与调参
2. 毕业论文中“算法设计、系统实现、实验评估”章节的撰写

当前项目已经具备完整的实时语音链路：客户端录音、服务端 STT、RAG、LLM、TTS、回传播放。打断检测位于服务端语音会话运行时，是影响交互自然度的关键环节。本文将现有规则型实现升级为“自适应打断检测算法”。

## 2. 研究背景与问题定义

厨房场景的语音交互与普通安静室内场景不同，主要存在三类干扰：

1. 环境噪声强，且随时间变化明显，例如油烟机、排风扇、水流声、锅铲碰撞声。
2. 系统播报语音会通过设备扬声器回放，麦克风可能再次采集到回声。
3. 用户打断行为具有突发性，既要尽快响应，又要避免误判系统回声为用户插话。

如果只使用固定阈值和固定时长确认，会出现两个问题：

1. 噪声环境变强时，漏检真实打断。
2. TTS 回声较强时，误判回声为打断。

因此，需要一种能够根据环境噪声、语音连续性和回声风险动态调整判断条件的算法。

## 3. 算法目标

本算法的目标是：

1. 在系统播报期间检测用户是否正在插话。
2. 将“疑似打断”与“确认打断”分层处理，降低误判。
3. 根据环境噪声和最近帧分布动态调整判断阈值。
4. 在回声高风险时间窗内抑制误触发。

## 4. 算法整体思路

算法以 20ms 音频帧为基本处理单元，对每一帧计算以下特征：

1. `vad_result`
   来自 `webrtcvad` 或能量回退判定，表示该帧是否可能为语音。

2. `energy`
   当前帧平均绝对能量。

3. `noise_floor`
   动态噪声底线，在非语音帧或低置信语音帧中持续更新。

4. `speech_ratio`
   最近若干帧中判为语音的比例，用于反映“连续说话”趋势。

5. `echo_risk`
   根据最近一次 TTS 输出时间计算当前回声风险，越接近播报时刻风险越高。

在每帧上构造综合评分：

```text
score = vad_score + energy_score + ratio_score - echo_penalty
```

其中：

```text
energy_gain = max(0, (energy - noise_floor) / noise_floor)
energy_score = min(1.5, energy_gain / adaptive_energy_margin)
vad_score = 0.8 if vad_result else 0
ratio_score = min(1.0, speech_ratio * 1.2)
echo_penalty = echo_risk * 0.9
```

然后基于双阈值状态机做判定：

1. 当 `score >= pending_score` 且连续语音帧达到起始门限时，进入 `INTERRUPT_PENDING`
2. 当 `score >= confirm_score` 且达到动态确认帧数时，进入 `INTERRUPTED`
3. 若处于 `INTERRUPT_PENDING` 后又连续静音，则恢复到 `SPEAKING`

## 5. 状态机设计

算法运行在以下显式状态上：

1. `IDLE`
   当前系统未播报。

2. `SPEAKING`
   当前系统正在播报 TTS。

3. `INTERRUPT_PENDING`
   已检测到疑似用户插话，暂停音频发送，但尚未确认打断。

4. `INTERRUPTED`
   已确认用户插话，停止当前 TTS。

状态迁移规则：

1. `IDLE -> SPEAKING`
   TTS 开始播报时进入。

2. `SPEAKING -> INTERRUPT_PENDING`
   当前帧评分超过疑似打断阈值，且连续语音帧足够。

3. `INTERRUPT_PENDING -> INTERRUPTED`
   当前帧评分超过确认阈值，且累计语音帧达到动态确认门限。

4. `INTERRUPT_PENDING -> SPEAKING`
   疑似打断后未持续说话，转为静音回退。

5. `SPEAKING/INTERRUPT_PENDING/INTERRUPTED -> IDLE`
   当前播报结束或被手动停止。

## 6. 动态确认策略

传统方案通常固定要求“连续说话 800ms 或 1000ms 才算打断”。这种做法过于死板。

本方案将确认帧数设计为动态值：

1. 若当前 `score` 明显高于确认阈值，缩短确认时长，提高响应速度。
2. 若当前 `score` 仅略高于确认阈值，保持较长确认时长，避免误判。

实现形式如下：

```text
base_frames = min_speech_ms / frame_ms

if score >= confirm_score + 0.75:
    confirm_frames = base_frames / 3
elif score >= confirm_score + 0.35:
    confirm_frames = base_frames / 2
else:
    confirm_frames = base_frames
```

## 7. 当前代码落点

本算法目前落在以下代码位置：

1. [voice_session.py](C:/Users/34222/Desktop/bishe/backend/api/voice_session.py)
   语音会话主运行时，核心方法为 `_handle_barge_in()`

2. [config.py](C:/Users/34222/Desktop/bishe/backend/config.py)
   自适应打断参数配置

3. [test_voice_session_runner.py](C:/Users/34222/Desktop/bishe/backend/tests/test_voice_session_runner.py)
   基础回归测试

当前已经接入的关键变量包括：

1. `noise_floor`
2. `noise_floor_alpha`
3. `adaptive_energy_margin`
4. `speech_ratio_window`
5. `pending_score`
6. `confirm_score`
7. `echo_suppression_window_ms`

## 8. 参数说明

建议论文和代码中统一使用下表中的参数名称。

| 参数名 | 含义 | 当前默认值 |
| --- | --- | --- |
| `BARGE_IN_MIN_SPEECH_MS` | 基础确认时长 | `1000` |
| `BARGE_IN_START_FRAMES` | 进入疑似打断前的最少连续语音帧 | `15` |
| `BARGE_IN_NOISE_FLOOR` | 初始噪声底线 | `1000.0` |
| `BARGE_IN_NOISE_FLOOR_ALPHA` | 噪声底线更新速率 | `0.05` |
| `BARGE_IN_ADAPTIVE_ENERGY_MARGIN` | 能量增益归一化边界 | `0.35` |
| `BARGE_IN_PENDING_SCORE` | 疑似打断评分阈值 | `1.15` |
| `BARGE_IN_CONFIRM_SCORE` | 确认打断评分阈值 | `1.45` |
| `BARGE_IN_SPEECH_RATIO_WINDOW` | 连续语音比例统计窗口 | `12` |
| `BARGE_IN_ECHO_SUPPRESSION_WINDOW_MS` | 回声抑制窗口 | `900` |
| `BARGE_IN_TTS_COOLDOWN_MS` | 播报结束后短冷却时间 | `500` |

## 9. 后续代码工作建议

为了把这一部分继续做扎实，建议后续按下面顺序推进：

1. 增加日志或调试事件
   将 `noise_floor`、`score`、`speech_ratio`、`echo_risk` 记录下来，便于调参和论文画图。

2. 增加假数据集成测试
   构造伪造音频帧序列，验证三种情况：
   - 正常播报不应误打断
   - 用户短句插话能成功打断
   - 回声残留不应误打断

3. 增加真实样本离线评估脚本
   用录制的厨房语音样本批量跑检测，输出误打断率、漏打断率和响应时延。
   当前仓库已提供 [eval_barge_in.py](C:/Users/34222/Desktop/bishe/scripts/eval_barge_in.py)，可直接基于 `jsonl` 标注清单批量评估。

4. 将算法模块独立化
   后续可以把打断逻辑进一步抽到 `backend/voice/barge_in_detector.py`，让论文章节结构更清晰。

## 10. 论文写法建议

### 10.1 可用题目表述

可以采用如下题目方向：

1. 面向厨房场景的实时语音助手设计与实现
2. 面向厨房噪声环境的自适应语音打断检测方法研究与实现
3. 基于本地语音识别与自适应打断策略的厨房智能助手系统设计

### 10.2 创新点写法

可归纳为两个层次：

1. 系统层创新
   构建了“本地 STT + RAG + LLM + TTS + 实时打断控制”的端到端语音交互系统。

2. 算法层创新
   提出一种面向厨房噪声场景的自适应打断检测方法，融合动态噪声估计、连续语音比例和回声风险抑制，实现比固定阈值方法更稳定的插话检测。

### 10.3 实验对比建议

至少做一组 baseline 对比：

1. Baseline
   固定阈值 + 固定确认时长

2. Proposed
   动态噪声底线 + 综合评分 + 动态确认帧数

建议指标：

1. 误打断率
2. 漏打断率
3. 平均打断响应时延
4. 用户主观满意度

推荐使用离线评估脚本的输出作为实验原始数据。样本清单建议至少包含：

1. `label`
   `interrupt` 或 `no_interrupt`

2. `expected_interrupt_ms`
   用户真实开始插话后的参考时间点，用于统计时延偏差

3. `tts_offset_ms`
   样本开始时距离最近一次 TTS 输出的时间，用于模拟回声敏感区

### 10.4 图表建议

论文中建议至少准备以下图表：

1. 系统架构图
2. 打断状态机图
3. 不同场景下 `score` 随时间变化曲线
4. Baseline 与 Proposed 的指标对比表

## 11. 当前阶段结论

对于本项目，自适应打断检测算法是一个投入产出比很高的增强点：

1. 与现有系统强相关，不需要推翻架构
2. 代码工作量真实，能够形成可展示的工程改进
3. 论文里可以自然写成“问题分析 -> 算法设计 -> 系统实现 -> 对比实验”

因此，建议将其作为毕业设计的核心算法增强点之一持续推进。
