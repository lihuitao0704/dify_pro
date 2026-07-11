@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ============================================
echo   企业智能助手 v2.0
echo ============================================
echo.
echo   [1] 启动后端 (FastAPI :8001)
echo   [2] 启动前端 (Streamlit :8501)
echo   [3] 测试套件
echo   [4] 初始化测试数据
echo   [5] 同步账户
echo.
echo ============================================
echo.

set /p choice="请选择 (1-5): "

if "%choice%"=="1" (
    python -m uvicorn enterprise_agent.main:app --host 0.0.0.0 --port 8001 --reload
) else if "%choice%"=="2" (
    streamlit run enterprise_agent/frontend/app.py --server.port 8501
) else if "%choice%"=="3" (
    python -m enterprise_agent.test_api
    pause
) else if "%choice%"=="4" (
    python -m enterprise_agent.seed_data
    pause
) else if "%choice%"=="5" (
    python -m enterprise_agent.sync_accounts
    pause
) else (
    echo 无效选择
    pause
)
