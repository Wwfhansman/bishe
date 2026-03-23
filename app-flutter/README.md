# app_flutter

Flutter 客户端是当前项目的主前端，实现了登录、历史会话和实时语音对话。

## 运行

先安装依赖：

```bash
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

真机 + ngrok：

```bash
flutter run --dart-define=API_BASE_URL=https://你的地址.ngrok-free.dev --dart-define=WS_BASE_URL=wss://你的地址.ngrok-free.dev/ws/voice
```

## 开发命令

```bash
flutter analyze
flutter test
```

## 目录说明

- `lib/core/services/`：API、WebSocket、录音、播放、音频会话
- `lib/core/providers/`：全局状态管理
- `lib/ui/screens/`：登录页、主页、历史页、个人页
