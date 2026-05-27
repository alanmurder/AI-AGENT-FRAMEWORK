@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"

echo.
echo ============================================
echo   AI Agent Platform — Starting...
echo ============================================
echo.

rem Check .env exists
if not exist "%ROOT_DIR%\.env" (
    echo [WARN] .env not found — copying from .env.example
    copy "%ROOT_DIR%\.env.example" "%ROOT_DIR%\.env" >nul
    echo [WARN] Edit .env with your API keys if needed.
)
echo [*] Configuration: .env

rem Check virtual environment
if not exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
    echo [X] Virtual environment not found. Run install.ps1 first.
    pause
    exit /b 1
)
echo [*] Python virtual environment: .venv\

rem Check frontend build
if not exist "%ROOT_DIR%\web\dist\index.html" (
    echo [X] Frontend build not found. Run build.bat first.
    pause
    exit /b 1
)
echo [*] Frontend build: web\dist\

rem Optional: check Redis
where redis-cli >nul 2>&1
if %errorlevel% equ 0 (
    redis-cli ping 2>nul | find "PONG" >nul
    if %errorlevel% equ 0 (
        echo [*] Redis: running
    ) else (
        echo [WARN] Redis not running — chat/memory features unavailable
    )
) else (
    echo [WARN] redis-cli not found — Redis is optional
)

rem Set production mode
set "AI_AGENT_SERVE_STATIC=true"

echo.
echo Starting backend on http://localhost:8000 ...
echo.

rem Start in a new window so it stays running
start "AI-Agent-Platform" "%ROOT_DIR%\.venv\Scripts\python" -m gateway.server

rem Wait for backend to be ready
set "TRIES=0"
:wait
timeout /t 2 /nobreak >nul 2>&1
set /a "TRIES=TRIES+1"
powershell -NoProfile -Command "try { $r = Invoke-WebRequest 'http://localhost:8000/health' -UseBasicParsing -TimeoutSec 2; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 goto ready
if %TRIES% lss 15 goto wait

echo [WARN] Server may still be starting — check the AI-Agent-Platform window.
goto done

:ready
echo [*] Server is ready!

:done
echo.
echo ============================================
echo   http://localhost:8000       — Frontend
echo   http://localhost:8000/health — Health
echo   http://localhost:8000/docs   — API Docs
echo ============================================
echo.
echo Close the "AI-Agent-Platform" window to stop the server.
echo If port 8000 is still occupied, run stop.bat.
echo.
pause
