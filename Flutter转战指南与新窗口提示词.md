# 🚀 厨房助手 AI：转战独立 App (Flutter 版) 开发指北与 AI 提示词

这份文档用于帮助你在开启**全新的对话窗口**时，让新的 AI 助手瞬间了解当前项目的背景、后端接口状态以及采用 Flutter 进行移动端开发的最佳实践。

 提示：每次重启 ngrok 后，域名可能会变。如果以后换了 ngrok 地址，只需要改 

lib/core/utils/constants.dart
 里的这两行 URL 即可。
---

## 📋 给新对话窗口的“系统级提示词”

**使用方法：** 复制以下带引用的整段文字，作为你在新窗口的**第一句话**发给 AI。

> 你好！我现在要做一个基于手机平台（iOS/Android）的**全双工智能语音助手（厨房助理 妮妮）**。
> 
> 【背景介绍】
> 我的后端已经用 Python FastAPI 完全写好并在运行（采用 WebSocket 实时推流对讲，集成大模型、数据库和语音合成识别）。之前我们是用微信小程序和 React Native Expo 尝试做前端，但因为微信小程序回声消除能力拉胯，而 Expo 框架在部分机型上调试太坑、模拟器麦克风支持差，我决定**全盘废弃之前的所有前端代码**，直接使用 **Flutter** 从零开发独立的手机 App。这样可以直接编译成原生 APK/IPA 安装到真机测试，不受限于任何第三方沙盒 App（如Expo Go或微信）。
> 手机app所有代码都在C:\Users\34222\Desktop\bishe\app-flutter里面，你的权限也只在这里面，不要更改任何后端代码，如果有需要更改的请一定要先告诉我
> 
> 【核心技术挑战与诉求】
> 这个 App 最核心的技术难点是**实时双向语音通话（必须要完美的回声消除，不能把 AI 播放的声音录进去当成用户的输入）**。因此在 Flutter 端：
> 1. 录音层：必须能以 `16000Hz`、单声道、`PCM (16-bit)` 格式，提取连续的二进制数据流交给 WebSocket 推送给后端。
> 2. 播放层：能接收后端 WebSocket 传来的连续 `PCM` 流并实时顺滑播放。
> 3. 回声消除（AEC）：这是采用原生/Flutter 的绝对核心！在初始化录音时，必须配置使用支持系统级回声消音（Echo Cancellation/AEC）和通话模式（Voice Communication）的音频类库（如 `record` 库的 hardware AEC 选项，或更硬核的平台通道方案）。
> 
> 【已有后端接口文档 (BaseURL: `/api` 和 WS: `/ws`)】
> 1. 认证：`POST /auth/login` 和 `POST /auth/register` (需传 JSON 参数 `username`, `password`) → 返回 `{"ok": true, "token": "...", "user_id": "..."}`。
> 2. 会话管理：`GET /sessions` (需带 Bearer Token)；`POST /sessions` (创建新会话返回 `session_id`)；`GET /sessions/{id}/history`。
> 3. 语音引擎 (WebSocket)：`ws://.../ws/voice?session_id=xxx&token=xxx`
>    - WebSocket 通信协议：既会发送/接收 JSON 文本，也会直接发送/接收二进制 ArrayBuffer (PCM)。
>    - 客户端发二进制：用户的麦克风 PCM16 数据
>    - 客户端发指令 (JSON)：`{"cmd": "stop"}` (停止回答) 或 `{"cmd": "interrupt_tts"}` (打断语音合成)。
>    - 服务端发指令 (JSON)：`asr_text` (识别结果)、`llm_text` (模型文本)、`tts_start` (合成开始，带 `rate` 如 22050)、`tts_done` (合成结束)、`tts_interrupted`、`tts_reset` (前端应立即清空音频播放队列)。
>    - 服务端发二进制：TTS 生成的 PCM 音频块，需拼接入队播放。

你可以使用已有的skills来帮助开发，同时也可以用find-skills找一下对这个项目开发的相关skills，然后使用skills来帮助我开发。
> 
> 【UI 规划】
> 主题色以科技厨房风格为主：
> 原型图参考工程文件中的C:\Users\34222\Desktop\bishe\yuanxing.png
> 1. LoginPage (注册/登录)
> 2. HomePage (中间一个大大的波纹动效语音按钮，显示当前识别和对话状态)
> 3. HistoryPage (历史对话列表)
> 4. ProfilePage (含登出功能)
> 
> 【第一阶段任务】
> 请你现在作为资深 Flutter 与音视频开发专家：
> 1. 帮我梳理在电脑上创建这套 Flutter 项目骨架的起步指令（我是 Windows 环境，可以真机 USB 调试）。
> 2. 特别是对音视频重中之重的几个库（WebSocket库、可以连续流式拿PCM并自带回声消除的录音库、PCM流式播放库）给出最靠谱的选型推荐。
> 3. 给出下一步的行动计划。

---

## 💡 开发备忘录（写给你自己看的补充知识）

1. 关于模拟器麦克风：Android Studio 模拟器其实是**支持电脑麦克风**的，你需要去虚拟机的设置 (Extended Controls -> Microphone) 把 "Virtual microphone uses host audio input" 打开。不过**做音视频项目，永远永远用一根 USB 线连着真实的安卓或苹果手机进行调试**，效果才是最真实的！
2. Flutter 的架构：Flutter 是用 Dart 语言写的，和 JS 完全是两个世界，所以你没办法直接“改写”之前的代码。最稳妥的方式是在 `bishe` 目录旁边（或者里面）新建一个空的 Flutter 项目（比如叫 `app-flutter`），然后以前那些微信的文件（如 `wxapp`、`app-mobile`）全部删掉眼不见为净。
3. Ngrok：真机通过 USB 调试时，手机的网络和电脑哪怕不在同一个局域网，只要你用之前的 `ngrok http 8001` 把内网穿透代理出来，Flutter 里填上 `https://xxxxx.ngrok-free.app` 一样可以丝滑连通。
