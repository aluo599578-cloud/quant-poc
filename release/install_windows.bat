@echo off
REM quant-poc 一键安装脚本（Windows CMD）

echo ===========================================================
echo   quant-poc 一键安装
echo ===========================================================

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 未安装或不在 PATH 中
    echo 请先安装 Python 3.10+ : https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] 创建虚拟环境...
if not exist .venv (
    python -m venv .venv
)

echo [2/4] 激活虚拟环境...
call .venv\Scripts\activate.bat

echo [3/4] 升级 pip...
python -m pip install --upgrade pip

echo [4/4] 安装依赖（这可能需要 1-3 分钟）...
pip install -r requirements.txt

echo.
echo ===========================================================
echo   安装完成！
echo ===========================================================
echo.
echo 接下来：
echo   1. 设置环境变量 TUSHARE_TOKEN（去 https://tushare.pro 注册）
echo   2. 双击 run_backtest.bat 跑回测
echo   3. 双击 run_dashboard.bat 看可视化 Dashboard
echo.
pause
