@echo off
setlocal
chcp 65001 >nul
title SmartRoute AI Gateway

echo [INFO] 正在检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 未检测到 Python。请先安装 Python 3.10+ 并添加到系统路径。
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

cd /d "%~dp0"

if not exist frontend\dist (
    echo [WARNING] 未检测到前端构建文件 frontend/dist 。
    echo [WARNING] 管理面板可能无法正常访问。
    echo [WARNING] 请确保在复制前已运行 'npm run build'，或在此目录下手动构建。
    echo.
)

if not exist venv (
    echo [INFO] 正在创建虚拟环境...
    python -m venv venv
)

echo [INFO] 激活虚拟环境...
call venv\Scripts\activate

echo [INFO] 检查依赖更新...
pip install -r backend/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo.
echo [INFO] SmartRoute AI Gateway 启动中...
echo [INFO] 管理面板: http://localhost:6688
echo [INFO] API 地址: http://localhost:6688/v1
echo.

cd backend
python main.py

pause
