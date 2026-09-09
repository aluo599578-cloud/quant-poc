@echo off
REM quant-poc 回测脚本

if not exist .venv\Scripts\activate.bat (
    echo [ERROR] 请先双击 install_windows.bat 安装依赖
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo ===========================================================
echo   002180 纳思达 双均线回测
echo ===========================================================
python backtest_3stocks.py

echo.
echo ===========================================================
echo   30 次策略扫描
echo ===========================================================
python backtest_scan.py

pause
