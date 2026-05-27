@echo off
chcp 65001 >nul 2>&1

REM --- Kill any existing instances on our ports ---
for %%p in (8000 3000 3001 3002) do (
    for /f "tokens=*" %%a in ('powershell -NoProfile -Command "try { (Get-NetTCPConnection -LocalPort %%p -State Listen -ErrorAction Stop).OwningProcess } catch { }" 2^>nul') do (
        echo Killing PID %%a on port %%p...
        taskkill /F /PID %%a >nul 2>&1
    )
)
timeout /t 2 /nobreak >nul

echo Starting Backend...
start "AI-Agent-Backend" cmd /k "cd /d %~dp0 && .venv\Scripts\python -m gateway.server"

timeout /t 3 /nobreak >nul

echo Starting Frontend...
start "AI-Agent-Frontend" cmd /k "cd /d %~dp0web && npm run dev"

echo.
echo ========================================
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:3000
echo   Health:   http://localhost:8000/health
echo   API Docs: http://localhost:8000/docs
echo ========================================
echo.
echo Close the two cmd windows to stop services.
echo If a port is still occupied, run stop.bat.
echo.
pause
