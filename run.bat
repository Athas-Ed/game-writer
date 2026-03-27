@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Ensure console uses UTF-8 code page for display.
chcp 65001 >nul

rem Use PowerShell for Chinese output and startup logic.
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); & '%~dp0run.ps1'"

echo.
pause
endlocal
