# 真机联调与内网穿透排障指南

## 1. 适用场景

本文档用于排查以下问题：

1. 后端和 Flutter 都已启动，但手机端无法登录
2. 手机端提示“操作失败，请检查网络或用户名”
3. 后端控制台没有任何请求日志
4. 已开启 ngrok，但真机仍然无法联调

## 2. 本次问题结论

本次联调失败的根因是：

1. 手机端访问到了失效的 ngrok 公网地址
2. Flutter 真机包没有使用最新的 `--dart-define` 重新安装

出现 `ERR_NGROK_3200` 时，说明当前访问的 ngrok endpoint 已离线，而不是后端业务代码本身报错。

## 3. 现象判断

如果同时出现以下现象，优先怀疑是穿透地址或 App 构建参数问题：

1. 手机登录时报网络错误
2. 后端 `uvicorn` 控制台没有任何访问日志
3. ngrok 地址曾经变化过
4. 手机浏览器访问同一公网地址也失败

这通常表示请求根本没有打到 FastAPI。

## 4. 正确联调流程

### 4.1 启动后端

```bash
uvicorn backend.api.server:app --host 127.0.0.1 --port 8000 --reload
```

如果后续怀疑本地监听问题，也可以改为：

```bash
uvicorn backend.api.server:app --host 0.0.0.0 --port 8000 --reload
```

### 4.2 启动 ngrok

```bash
ngrok http 8000
```

记录当前 `Forwarding` 中的最新地址，例如：

```text
https://xxxx.ngrok-free.dev
```

注意：Free 版 ngrok 重启后，公网域名经常变化。

### 4.3 先用手机浏览器验证

在手机浏览器中访问：

```text
https://xxxx.ngrok-free.dev/docs
https://xxxx.ngrok-free.dev/api/tts_probe
```

判断方式：

1. 如果这两个地址都打不开，问题在 ngrok 或后端，不在 Flutter。
2. 如果浏览器能打开，而 App 不能访问，问题通常在 Flutter 构建参数或旧包未更新。

### 4.4 重新安装 Flutter 真机包

必须使用最新 ngrok 地址重新执行：

```bash
flutter run --dart-define=API_BASE_URL=https://xxxx.ngrok-free.dev --dart-define=WS_BASE_URL=wss://xxxx.ngrok-free.dev/ws/voice
```

注意：

1. 这一步必须是重新 `run`
2. 不能只靠热重载或热重启
3. 更稳妥的做法是先卸载手机上的旧 App，再重新安装

原因是：

`API_BASE_URL` 和 `WS_BASE_URL` 在项目中通过 `String.fromEnvironment(...)` 读取，属于编译期常量。  
如果 ngrok 地址变了，但 App 没有重新安装，手机端仍会访问旧地址。

## 5. 常见错误与含义

### 5.1 `ERR_NGROK_3200`

含义：

```text
The endpoint is offline.
```

表示当前访问的 ngrok endpoint 不在线，常见原因：

1. ngrok 进程已退出
2. ngrok 已重启，公网地址变了
3. App 中保存的是旧地址

官方参考：

https://ngrok.com/docs/errors/err_ngrok_3200

### 5.2 后端没有日志

如果后端控制台完全没有日志，通常说明：

1. 请求没到 FastAPI
2. 地址错误
3. 手机包仍指向旧地址
4. ngrok endpoint 已失效

这时不应先怀疑登录逻辑或数据库。

## 6. 本项目里的关键实现点

### 6.1 Flutter 地址配置

配置文件：

[constants.dart](C:/Users/34222/Desktop/bishe/app-flutter/lib/core/utils/constants.dart)

项目使用：

```dart
String.fromEnvironment('API_BASE_URL')
String.fromEnvironment('WS_BASE_URL')
```

这意味着地址不是运行时动态修改，而是安装包构建时注入。

### 6.2 登录错误显示

为了排查这类问题，项目已经增强了登录错误透出能力：

1. [api_service.dart](C:/Users/34222/Desktop/bishe/app-flutter/lib/core/services/api_service.dart)
2. [app_state_provider.dart](C:/Users/34222/Desktop/bishe/app-flutter/lib/core/providers/app_state_provider.dart)
3. [login_page.dart](C:/Users/34222/Desktop/bishe/app-flutter/lib/ui/screens/login_page.dart)

现在登录失败会显示更具体的 Dio 异常信息，便于区分：

1. 域名失效
2. 网络超时
3. SSL/证书问题
4. HTTP 状态码错误
5. 用户名密码错误

## 7. 推荐排障顺序

以后真机联调出问题时，建议固定按下面顺序排查：

1. 确认 `uvicorn` 正在运行
2. 确认 `ngrok http 8000` 正在运行
3. 复制当前最新 `Forwarding` 地址
4. 手机浏览器先访问 `/docs`
5. 手机浏览器再访问 `/api/tts_probe`
6. 卸载旧 App
7. 用最新 `--dart-define` 重新 `flutter run`
8. 再看 App 内部错误提示

## 8. 推荐启动命令模板

### 后端

```bash
uvicorn backend.api.server:app --host 127.0.0.1 --port 8000 --reload
```

### ngrok

```bash
ngrok http 8000
```

### Flutter 真机

```bash
flutter run --dart-define=API_BASE_URL=https://xxxx.ngrok-free.dev --dart-define=WS_BASE_URL=wss://xxxx.ngrok-free.dev/ws/voice
```

## 9. 结论

本项目真机联调时，最容易踩坑的点不是后端接口本身，而是：

1. ngrok 地址会变化
2. Flutter 使用的是编译期注入地址
3. 地址一变就必须重新安装 App

只要先用手机浏览器验证公网地址，再用最新地址重新安装 Flutter 包，绝大多数“手机报网络错误、后端没日志”的问题都能快速定位。
