@echo off
REM quant-poc Dashboard 启动脚本

if not exist .venv\Scripts\activate.bat (
    echo [ERROR] 请先双击 install_windows.bat 安装依赖
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo ===========================================================
echo   启动 Streamlit Dashboard
echo   浏览器打开: http://localhost:8501
echo ===========================================================
streamlit run dashboard.py

pause
