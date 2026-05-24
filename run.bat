@echo off
chcp 65001 >nul 2>&1
title AI Agent Platform

:: ============================================================================
::  AI Agent Platform — Production Run Script (Windows)
:: ============================================================================
::  Usage: run.bat
:: ============================================================================

setlocal enabledelayedexpansion

set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"

:: Colors via ANSI (works in Win10+ Terminal, PowerShell, VS Code)
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "NC=[0m"

echo.
echo ============================================
echo   AI Agent Platform — Starting...
echo ============================================
echo.

:: ---------------------------------------------------------------------------
:: Check .env
:: ---------------------------------------------------------------------------
if exist "%ROOT_DIR%\.env" (
    echo  %GREEN%*%NC% Loading configuration from .env
    for /f "usebackq delims=" %%a in ("%ROOT_DIR%\.env") do (
        for /f "tokens=1,* delims==" %%b in ("%%a") do (
            if not "%%b"=="" if not "%%b"=="#" (
                set "%%b=%%c"
            )
        )
    )
) else (
    echo  %YELLOW%!%NC% .env file not found.
    echo  %YELLOW%!%NC% Copy .env.example to .env and configure it.
)

:: ---------------------------------------------------------------------------
:: Check Redis
:: ---------------------------------------------------------------------------
echo.
echo  Checking Redis...
echo  -----------------

where redis-cli >nul 2>&1
if %errorlevel% equ 0 (
    redis-cli ping 2>nul | find "PONG" >nul
    if %errorlevel% equ 0 (
        echo  %GREEN%*%NC% Redis is running.
    ) else (
        echo  %YELLOW%!%NC% Redis is not responding.
        echo  %YELLOW%!%NC% The server will start normally. Chat and memory features
        echo  %YELLOW%!%NC% require Redis to be running.
    )
) else (
    echo  %YELLOW%!%NC% redis-cli not found on PATH. Skipping check.
    echo  %YELLOW%!%NC% Redis is optional — needed only for chat/memory features.
)

:: ---------------------------------------------------------------------------
:: Check frontend build
:: ---------------------------------------------------------------------------
if not exist "%ROOT_DIR%\web\dist\index.html" (
    echo.
    echo  %RED%X%NC% Frontend build not found at web\dist\index.html
    echo  %RED%X%NC% Run build.bat to build the frontend.
    echo.
    pause
    exit /b 1
)
echo  %GREEN%*%NC% Frontend build found at web\dist\

:: ---------------------------------------------------------------------------
:: Check virtual environment
:: ---------------------------------------------------------------------------
if not exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
    echo.
    echo  %RED%X%NC% Virtual environment not found.
    echo  %RED%X%NC% Run install.ps1 to set up the environment.
    echo.
    pause
    exit /b 1
)
echo  %GREEN%*%NC% Virtual environment found at .venv\

:: ---------------------------------------------------------------------------
:: Set production mode
:: ---------------------------------------------------------------------------
set "AI_AGENT_SERVE_STATIC=true"

:: ---------------------------------------------------------------------------
:: Start backend
:: ---------------------------------------------------------------------------
echo.
echo ============================================
echo   Starting Backend...
echo ============================================
echo.

set "HOST=%AI_AGENT_GATEWAY_HOST%"
if "%HOST%"=="" set "HOST=0.0.0.0"
set "PORT=%AI_AGENT_GATEWAY_PORT%"
if "%PORT%"=="" set "PORT=8000"
set "WORKERS=%AI_AGENT_GATEWAY_WORKERS%"
if "%WORKERS%"=="" set "WORKERS=4"

:: Check if gunicorn is available (via venv Scripts)
if exist "%ROOT_DIR%\.venv\Scripts\gunicorn.exe" (
    echo  Using gunicorn with %WORKERS% workers...
    start "AI-Agent-Platform" "%ROOT_DIR%\.venv\Scripts\gunicorn" ^
        gateway.server:app ^
        --worker-class uvicorn.workers.UvicornWorker ^
        --bind %HOST%:%PORT% ^
        --workers %WORKERS% ^
        --timeout 120 ^
        --access-logfile - ^
        --error-logfile - ^
        --log-level %AI_AGENT_LOG_LEVEL%
) else (
    echo  Using uvicorn directly...
    start "AI-Agent-Platform" "%ROOT_DIR%\.venv\Scripts\python" -m gateway.server
)

:: Wait for the server to start
echo  Waiting for the server to be ready...
set "WAITED=0"
:wait_loop
timeout /t 2 /nobreak >nul
set /a "WAITED=WAITED+2"
:: Try to reach the health endpoint
for /f "tokens=*" %%a in ('powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri http://localhost:%PORT%/health -UseBasicParsing -TimeoutSec 2).StatusCode } catch { 0 }" 2^>nul') do (
    if "%%a"=="200" goto ready
)
if %WAITED% lss 30 goto wait_loop

:: If we got here, the server didn't respond in time
echo  %YELLOW%!%NC% Server may still be starting. Check the window titled "AI-Agent-Platform".
goto print_urls

:ready
echo  %GREEN%*%NC% Server is ready!

:print_urls
echo.
echo ============================================
echo   AI Agent Platform is running!
echo ============================================
echo.
echo   URL:        http://localhost:%PORT%
echo   Health:     http://localhost:%PORT%/health
echo   API Docs:   http://localhost:%PORT%/docs
echo.
echo   Close the "AI-Agent-Platform" window to stop.
echo.
pause
