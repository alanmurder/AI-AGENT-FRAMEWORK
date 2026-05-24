@echo off
chcp 65001 >nul 2>&1
title AI Agent Platform — Build

:: ============================================================================
::  AI Agent Platform — Build Script (Windows)
:: ============================================================================
::  Usage: build.bat
:: ============================================================================

setlocal enabledelayedexpansion

set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"

set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "NC=[0m"

echo.
echo ============================================
echo   AI Agent Platform — Build
echo ============================================
echo.
echo  Step 1/2: Building frontend...
echo  ------------------------------

if not exist "%ROOT_DIR%\web" (
    echo  %RED%X%NC% web/ directory not found.
    pause
    exit /b 1
)

echo  %GREEN%*%NC% Installing frontend dependencies...
pushd "%ROOT_DIR%\web"
call npm ci
if %errorlevel% neq 0 (
    echo  %YELLOW%!%NC% npm ci failed, falling back to npm install...
    call npm install
)
if %errorlevel% neq 0 (
    echo  %RED%X%NC% npm install failed.
    popd
    pause
    exit /b 1
)

echo  %GREEN%*%NC% Building frontend...
call npm run build
if %errorlevel% neq 0 (
    popd
    echo  %RED%X%NC% Frontend build failed.
    pause
    exit /b 1
)
popd

echo.
echo  Verifying output...
echo  -------------------

if exist "%ROOT_DIR%\web\dist\index.html" (
    echo  %GREEN%*%NC% Frontend build: OK
    echo  %GREEN%*%NC% Output: web\dist\
) else (
    echo  %RED%X%NC% web\dist\index.html not found — build may have failed.
    pause
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: Done
:: ---------------------------------------------------------------------------
echo.
echo ============================================
echo   Build complete!
echo ============================================
echo.
echo   Frontend output:  %ROOT_DIR%\web\dist\
echo   Frontend entry:   %ROOT_DIR%\web\dist\index.html
echo.
echo   Run run.bat to start the platform.
echo.
pause
