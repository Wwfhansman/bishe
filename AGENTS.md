# Repository Guidelines

## 项目结构与模块分工
本仓库是一个“后端服务 + Flutter 客户端 + 本地模型/数据脚本”的组合项目。`backend/` 是核心服务端代码：`api/server.py` 负责 FastAPI 与 WebSocket 入口，`config.py` 集中管理环境变量与默认配置，`database.py` 处理 SQLite 相关逻辑，`llm/` 封装大模型调用，`rag/` 处理知识检索，`voice/` 维护 STT/TTS 协议、工厂与 provider 注册。`backend/tests/` 存放后端测试。`app-flutter/lib/` 是 Flutter 主代码目录，`ui/screens/` 放页面，`core/services/` 与 `core/providers/` 放状态和服务封装。`frontend/` 是静态 Web 页面，`data/raw/` 存原始知识库文本，`scripts/` 放模型下载和性能测试脚本，`docs/` 放架构与接口文档。

## 开发、构建与调试命令
首次进入项目先创建并激活虚拟环境，再安装后端依赖：

```bash
pip install -r backend/requirements.txt
```

本地启动后端：

```bash
uvicorn backend.api.server:app --reload
```

Windows 下如需连同 ngrok 一起启动，可直接运行：

```bash
start_dev.bat
```

模型下载与基准测试命令：

```bash
python scripts/download_models.py
python scripts/bench_stt.py path/to/sample.wav
python scripts/bench_tts.py
```

Flutter 端在 `app-flutter/` 目录下执行：

```bash
flutter pub get
flutter analyze
flutter test
flutter run
```

## 编码规范与命名约定
不要在本仓库里混用风格。Python 代码统一使用 4 空格缩进，文件名、函数名采用 `snake_case`，类名采用 `PascalCase`。新增 provider 时优先复用 `backend/voice/` 现有抽象，并同步更新 `backend/voice/registry.json`；如果改动了 provider 初始化参数，也要检查 `factory.py`、配置项和测试是否需要一起调整。FastAPI、Pydantic、服务工厂相关代码应保持“入口清晰、依赖显式、配置集中”，不要把环境变量读取散落到各模块中。

Flutter/Dart 代码使用 2 空格缩进，类名和 Widget 名使用 `UpperCamelCase`，变量与方法使用 `lowerCamelCase`。页面逻辑尽量放在 `ui/screens/`，可复用的网络、录音、播放、状态处理逻辑放回 `core/`，避免在页面里直接堆积业务细节。提交前至少跑一次 `flutter analyze`，遵守 `app-flutter/analysis_options.yaml` 中启用的 `flutter_lints` 规则。

## 测试要求
后端测试放在 `backend/tests/`，文件命名使用 `test_<feature>.py`。优先覆盖注册表解析、服务装配、RAG 检索、接口协议等稳定逻辑；依赖本地模型的能力测试应与纯单元测试分开，避免让基础测试过重。新增接口时，至少补一条能覆盖成功路径或关键失败路径的测试。Flutter 测试放在 `app-flutter/test/`，命名为 `*_test.dart`。提交前至少执行 `pytest backend/tests/` 与 `flutter test`，如果有无法在本地跑通的模型相关测试，需要在 PR 说明原因、前置条件和替代验证方式。

## 提交与合并请求规范
现有提交历史同时存在 `chore:`、`refactor:` 这类前缀式写法，以及简短中文摘要；继续沿用即可，但一条提交只解决一个问题，标题要直接说明改动目的，不要写成流水账。不要把“代码重构 + 配置调整 + 文档修补”混在同一个提交里，除非它们确实不可拆分。Pull Request 需说明变更背景、影响模块、运行方式、测试结果；涉及界面、音频链路、WebSocket 通信或启动流程调整时，附截图、关键日志或复现步骤。

## 配置与安全注意事项
`.env`、本地模型文件、SQLite 数据库、`ngrok` 地址及其他密钥不得提交。新增环境变量时，同时更新 `README.md` 或 `docs/` 中的说明，至少写明用途、是否必填、默认值和示例。`models/` 默认视为本地资源目录，修改下载逻辑或模型路径时，必须保证脚本和文档一致，避免他人按文档无法复现环境。若改动会影响端口、跨域、静态资源挂载路径或数据库文件位置，也要同步检查 `start_dev.bat`、前端连接地址和部署文档。
