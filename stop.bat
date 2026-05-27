@echo off
chcp 65001 >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
if errorlevel 1 (
    echo.
    echo Some services may still be running. Check the messages above.
)

echo.
pause
