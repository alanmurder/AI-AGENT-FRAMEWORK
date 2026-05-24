@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM deploy.bat — AI Agent Platform Windows Docker deployment script
REM
REM Usage:
REM   deploy.bat              Build (cached) and start
REM   deploy.bat --build      Force rebuild with --no-cache
REM   deploy.bat --pg         Include PostgreSQL profile
REM   deploy.bat --prod       Load .env for production
REM   deploy.bat --build --pg --prod   All flags
REM   deploy.bat --down       Stop and remove containers (keep data)
REM   deploy.bat --down-clean Stop containers AND remove all data volumes

set BUILD=false
set PG=false
set PROD=false
set DOWN=false
set DOWN_CLEAN=false

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--build"      set BUILD=true&      goto next_arg
if /i "%~1"=="--pg"         set PG=true&         goto next_arg
if /i "%~1"=="--prod"       set PROD=true&       goto next_arg
if /i "%~1"=="--down"       set DOWN=true&       goto next_arg
if /i "%~1"=="--down-clean" set DOWN_CLEAN=true& goto next_arg
echo [ERROR] Unknown argument: %~1
echo Usage: %~nx0 [--build] [--pg] [--prod] [--down ^| --down-clean]
exit /b 1
:next_arg
shift
goto parse_args
:args_done

REM -----------------------------------------------------------------------
REM Handle --down / --down-clean (stop and optionally remove data)
REM -----------------------------------------------------------------------
if /i "%DOWN%"=="true" goto do_down
if /i "%DOWN_CLEAN%"=="true" goto do_down_clean
goto skip_down

:do_down_clean
echo [WARN]  ===========================================
echo [WARN]    DESTRUCTIVE ACTION: --down-clean
echo [WARN]    This will DELETE all data volumes:
echo [WARN]      - Redis data
echo [WARN]      - Application data (workspace, logs, sessions^)
echo [WARN]      - PostgreSQL data (if profile pg was used^)
echo [WARN]  ===========================================
echo.
set /p CONFIRM="Type 'DELETE' to confirm: "
if /i not "!CONFIRM!"=="DELETE" (
    echo [INFO]  Aborted. No data was removed.
    pause
    exit /b 0
)
echo [INFO]  Stopping containers and removing volumes ...
docker compose down -v
echo [OK]    All containers stopped and data volumes removed.
pause
exit /b 0

:do_down
echo [INFO]  Stopping containers (data volumes preserved) ...
docker compose down
echo [OK]    All containers stopped. Data volumes are preserved.
pause
exit /b 0

:skip_down

echo [INFO]  AI Agent Platform Deploy Script
echo [INFO]  Working directory: %CD%
echo.

REM -----------------------------------------------------------------------
REM Check Docker is running
REM -----------------------------------------------------------------------
docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Docker is not running or not installed.
    echo         Make sure Docker Desktop is running and try again.
    pause
    exit /b 1
)
echo [INFO]  Docker is available.

REM -----------------------------------------------------------------------
REM Load environment variables (production mode)
REM -----------------------------------------------------------------------
if /i "%PROD%"=="true" (
    if not exist ".env" (
        echo [ERROR] .env file not found at %CD%\.env
        echo         Copy .env.example to .env and fill in required values before deploying with --prod.
        pause
        exit /b 1
    )
    echo [INFO]  Loading .env file for production ...

    REM Read .env and set each variable (skip blanks and comments)
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        set "line=%%a"
        if not "!line!"=="" (
            set "first=!line:~0,1!"
            if not "!first!"=="#" (
                set "%%a=%%b"
            )
        )
    )
    echo [OK]    Environment variables loaded from .env
) else (
    echo [INFO]  Development mode: using default environment (no .env loaded)
)

REM -----------------------------------------------------------------------
REM Validate critical environment variables
REM -----------------------------------------------------------------------
set VALIDATION_FAILED=false

if not defined AI_AGENT_DEEPSEEK_API_KEY (
    echo [WARN]  AI_AGENT_DEEPSEEK_API_KEY is not set. This may cause runtime failures.
    set VALIDATION_FAILED=true
)
if not defined AI_AGENT_JWT_SECRET (
    echo [WARN]  AI_AGENT_JWT_SECRET is not set. This may cause runtime failures.
    set VALIDATION_FAILED=true
) else if "!AI_AGENT_JWT_SECRET!"=="change-this-in-production" (
    echo [WARN]  AI_AGENT_JWT_SECRET is still set to the default value 'change-this-in-production'. Update it for production.
    set VALIDATION_FAILED=true
)

if "!VALIDATION_FAILED!"=="true" (
    echo [WARN]  One or more environment variables need attention. Check the warnings above.
    if /i "!PROD!"=="true" (
        echo [WARN]  Proceeding anyway in 5 seconds ... (press Ctrl+C to abort)
        choice /c CN /t 5 /d C /n >nul 2>&1
    )
)

REM -----------------------------------------------------------------------
REM Build images
REM -----------------------------------------------------------------------
if /i "%BUILD%"=="true" (
    echo [WARN]  Forcing full rebuild with --no-cache (this may take a while)...
    echo [INFO]  Building Docker images ...
    docker compose build --no-cache
) else (
    echo [INFO]  Building Docker images (cached) ...
    docker compose build
)

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Docker build failed. Check the build output above.
    pause
    exit /b 1
)
echo [OK]    Docker images built successfully.

REM -----------------------------------------------------------------------
REM Start services
REM -----------------------------------------------------------------------
if /i "%PG%"=="true" (
    echo [INFO]  Starting services with PostgreSQL profile ...
    docker compose --profile pg up -d
) else (
    echo [INFO]  Starting services (without PostgreSQL) ...
    docker compose up -d
)

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to start Docker services. Check 'docker compose logs' for details.
    pause
    exit /b 1
)
echo [OK]    All services started.

REM -----------------------------------------------------------------------
REM Display running containers
REM -----------------------------------------------------------------------
echo.
echo [INFO]  Running containers:
echo ----------------------------------------
docker compose ps
echo ----------------------------------------
echo.

REM -----------------------------------------------------------------------
REM Wait for health endpoint
REM -----------------------------------------------------------------------
set HEALTH_URL=http://localhost:8000/health
set TIMEOUT=60
set ELAPSED=0

echo [INFO]  Waiting for health endpoint at %HEALTH_URL% (timeout: %TIMEOUT%s) ...

:health_loop
if %ELAPSED% geq %TIMEOUT% (
    echo [ERROR] Health check did not pass within %TIMEOUT%s.
    echo          Possible issues:
    echo            - The application failed to start. Check: docker compose logs app
    echo            - The port mapping is different. Run: docker compose ps
    echo            - Redis is unavailable. Check: docker compose logs redis
    pause
    exit /b 1
)

REM Use PowerShell to make the HTTP request
powershell -Command ^
    "try { $r = Invoke-RestMethod -Uri '%HEALTH_URL%' -ErrorAction Stop; exit 0 } catch { exit 1 }" >nul 2>&1

if %ERRORLEVEL% equ 0 (
    echo [OK]    Health check passed!
    goto health_done
)

REM Wait before retrying
if %ELAPSED% neq 0 (
    set /a mod=ELAPSED %% 10
    if !mod! equ 0 (
        echo [INFO]  Still waiting ... !ELAPSED!s elapsed
    )
)
timeout /t 2 /nobreak >nul
set /a ELAPSED+=2
goto health_loop

:health_done

REM -----------------------------------------------------------------------
REM Print success summary
REM -----------------------------------------------------------------------
echo.
echo [OK]    ============================================
echo [OK]      AI Agent Platform is now running!
echo [OK]    ============================================
echo.
echo   Frontend:  http://localhost:8000
echo   Health:    http://localhost:8000/health
echo   API Docs:  http://localhost:8000/docs
echo.
echo Useful commands:
echo   docker compose logs -f    Follow all logs
echo   docker compose ps         List services
echo   docker compose down       Stop all services
echo.

REM Show health response
echo [INFO]  Health endpoint response:
powershell -Command ^
    "try { Invoke-RestMethod -Uri 'http://localhost:8000/health' -ErrorAction Stop | ConvertTo-Json } catch { echo 'Health check unavailable' }"
echo.

pause
