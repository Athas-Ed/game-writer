@echo off
chcp 936 >nul
setlocal EnableExtensions
cd /d "%~dp0"

rem 让运行脚本时也能稳定 import `src.*`
if defined PYTHONPATH (
    set "PYTHONPATH=%~dp0;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%~dp0"
)

rem 一键启动游戏编剧工作台，无需手动 activate。
rem 可选：在系统或用户环境变量中设置 APP_MODE=work 或 APP_MODE=dev。

set "PYEXE="
if exist "venv\Scripts\python.exe" set "PYEXE=%~dp0venv\Scripts\python.exe"
if not defined PYEXE if exist "venv_skills\Scripts\python.exe" set "PYEXE=%~dp0venv_skills\Scripts\python.exe"

if not defined PYEXE (
    echo [错误] 未找到虚拟环境 venv 或 venv_skills。
    echo 请在本目录执行: python -m venv venv
    echo 然后执行:
    echo   venv\Scripts\python -m pip install -r requirements.txt
    echo   venv\Scripts\python -m pip install -e .
    goto :end
)

"%PYEXE%" -c "import streamlit" 1^>nul 2^>nul
if errorlevel 1 (
    echo [错误] 当前环境未安装 streamlit。
    echo 请执行: "%PYEXE%" -m pip install -r requirements.txt
    echo （可选）"%PYEXE%" -m pip install -e .
    goto :end
)

echo.
echo ========================================
echo   游戏编剧工作台
echo   浏览器打开: http://localhost:8501
echo   停止服务请在本窗口按 Ctrl+C
echo ========================================
echo.

"%PYEXE%" -m streamlit run "src\ui\streamlit_app.py" --server.address=localhost --browser.gatherUsageStats=false
echo.
echo [已退出] Streamlit 已结束，退出代码: %ERRORLEVEL%

:end
echo.
pause
endlocal
