@echo off
chcp 65001 >nul
echo ============================================
echo   厨房助手 - 一键启动脚本
echo ============================================
echo.

:: 激活虚拟环境
call venv\Scripts\activate.bat

:: 启动后端（后台运行）
echo [1/2] 正在启动后端服务器 (端口 8000)...
start "后端服务器" cmd /k "cd /d %~dp0 && venv\Scripts\activate.bat && uvicorn backend.api.server:app --host 127.0.0.1 --port 8000 --reload"

:: 等2秒让后端先启动
timeout /t 2 /nobreak >nul

:: 启动 ngrok（前台运行，方便看到公网地址）
echo [2/2] 正在启动 ngrok 内网穿透...
echo.
echo ============================================
echo   启动成功！请注意：
echo   1. 复制下方 Forwarding 行中的 https://xxx.ngrok-free.dev 地址
echo   2. 使用该地址启动 Flutter：
echo      flutter run --dart-define=API_BASE_URL=https://xxx.ngrok-free.dev --dart-define=WS_BASE_URL=wss://xxx.ngrok-free.dev/ws/voice
echo ============================================
echo.
.\ngrok.exe http 8000
