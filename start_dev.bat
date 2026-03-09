@echo off
chcp 65001 >nul
echo ============================================
echo   厨房助手 - 一键启动脚本
echo ============================================
echo.

:: 激活虚拟环境
call venv\Scripts\activate.bat

:: 启动后端（后台运行）
echo [1/2] 正在启动后端服务器 (端口 8001)...
start "后端服务器" cmd /k "cd /d %~dp0 && venv\Scripts\activate.bat && uvicorn backend.api.server:app --host 127.0.0.1 --port 8001"

:: 等2秒让后端先启动
timeout /t 2 /nobreak >nul

:: 启动 ngrok（前台运行，方便看到公网地址）
echo [2/2] 正在启动 ngrok 内网穿透...
echo.
echo ============================================
echo   启动成功！请注意：
echo   1. 复制下方 Forwarding 行中的 https://xxx.ngrok-free.dev 地址
echo   2. 粘贴到 wxapp/utils/config.js 中的 ngrok 配置里
echo   3. 把 config.js 中的 ENV 改为 'ngrok' (真机) 或 'local' (模拟器)
echo ============================================
echo.
.\ngrok.exe http 8001
