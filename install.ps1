<#
.SYNOPSIS
    AI Agent Platform — Windows Fresh-System Install Script

.DESCRIPTION
    Installs Python 3.11+, Node.js LTS, optionally Redis, creates a Python virtual
    environment, installs Python and frontend dependencies, builds the frontend,
    and prepares data directories.

    Run this script in PowerShell (as Administrator recommended):
        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
        .\install.ps1

.PARAMETER NoFrontend
    Skip frontend dependencies and build.

.PARAMETER NoSandbox
    Skip sandbox (Docker) optional dependencies.

.PARAMETER SkipRedis
    Skip Redis installation (Redis is optional, only needed for chat/memory).

.EXAMPLE
    .\install.ps1
    .\install.ps1 -NoFrontend
    .\install.ps1 -NoSandbox
    .\install.ps1 -SkipRedis
#>

param(
    [switch]$NoFrontend,
    [switch]$NoSandbox,
    [switch]$SkipRedis
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
$Host.UI.RawUI.ForegroundColor = "White"
function Write-Info   { Write-Host "  * $args" -ForegroundColor Green }
function Write-Warn   { Write-Host "  ! $args" -ForegroundColor Yellow }
function Write-Error  { Write-Host "  X $args" -ForegroundColor Red }
function Fatal        { Write-Error $args; exit 1 }

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $RootDir ".venv\Scripts\python.exe"
$PipExe = Join-Path $RootDir ".venv\Scripts\pip.exe"

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  AI Agent Platform — Windows Install"       -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# Check Administrator rights
# ---------------------------------------------------------------------------
$IsAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
    Write-Warn "Not running as Administrator."
    Write-Warn "Redis installation and some operations may require admin rights."
    Write-Warn "Consider re-running this script as Administrator."
    Write-Host ""
}
else {
    Write-Info "Running with Administrator privileges."
}

# ---------------------------------------------------------------------------
# Phase 1: Check package managers
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "  Phase 1/6: Checking package managers..." -ForegroundColor Cyan
Write-Host "  -----------------------------------------" -ForegroundColor Cyan

$WingetAvailable = $false
$ChocoAvailable = $false

if (Get-Command winget -ErrorAction SilentlyContinue) {
    $WingetAvailable = $true
    Write-Info "winget detected."
}
else {
    Write-Warn "winget not found. Will use alternative methods."
}

if (Get-Command choco -ErrorAction SilentlyContinue) {
    $ChocoAvailable = $true
    Write-Info "Chocolatey detected."
}
else {
    Write-Warn "Chocolatey not found. Redis auto-install unavailable."
}

# ---------------------------------------------------------------------------
# Phase 2: Install Python 3.11
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "  Phase 2/6: Installing Python 3.11..." -ForegroundColor Cyan
Write-Host "  --------------------------------------" -ForegroundColor Cyan

$PythonFound = $false
try {
    $pyVer = & python --version 2>&1
    if ($pyVer -match "3\.1[1-9]|3\.[2-9]\d") {
        $PythonFound = $true
        Write-Info "Python 3.11+ already installed: $pyVer"
    }
}
catch { }

if (-not $PythonFound) {
    if ($WingetAvailable) {
        Write-Info "Installing Python 3.13 via winget..."
        winget install Python.Python.3.13 --accept-source-agreements --accept-package-agreements
        Write-Info "Python 3.13 installed via winget."
    }
    else {
        Write-Warn "winget not available. Please install Python 3.11+ manually from:"
        Write-Warn "  https://www.python.org/downloads/"
        Write-Warn "Make sure to check 'Add Python to PATH' during installation."
        Fatal "Python 3.11+ is required. Install it and re-run this script."
    }
}

# ---------------------------------------------------------------------------
# Phase 3: Install Node.js LTS
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "  Phase 3/6: Installing Node.js LTS..." -ForegroundColor Cyan
Write-Host "  -------------------------------------" -ForegroundColor Cyan

$NodeFound = $false
try {
    $nodeVer = & node --version 2>&1
    if ($nodeVer) {
        $NodeFound = $true
        Write-Info "Node.js already installed: $nodeVer"
    }
}
catch { }

if (-not $NodeFound) {
    if ($WingetAvailable) {
        Write-Info "Installing Node.js LTS via winget..."
        winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
        Write-Info "Node.js LTS installed via winget."
    }
    else {
        Write-Warn "winget not available. Please install Node.js LTS manually from:"
        Write-Warn "  https://nodejs.org/"
        Fatal "Node.js is required. Install it and re-run this script."
    }
}

# ---------------------------------------------------------------------------
# Phase 4: Install Redis (optional, only needed for chat/memory)
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "  Phase 4/6: Installing Redis (optional)..." -ForegroundColor Cyan
Write-Host "  -------------------------------------------" -ForegroundColor Cyan

if (-not $SkipRedis) {
    $RedisFound = $false
    try {
        $redisPing = & redis-cli ping 2>&1
        if ($redisPing -eq "PONG") {
            $RedisFound = $true
            Write-Info "Redis is already running."
        }
    }
    catch { }

    if (-not $RedisFound) {
        # Check if redis-server exists on PATH
        try {
            $null = Get-Command redis-server -ErrorAction Stop
            $RedisFound = $true
            Write-Info "Redis is installed (redis-server found on PATH)."
        }
        catch { }
    }

    if (-not $RedisFound) {
        if ($ChocoAvailable) {
            Write-Info "Installing Redis via Chocolatey..."
            choco install redis-64 -y
            Write-Info "Redis installed via Chocolatey."
            Write-Info "Starting Redis..."
            try {
                & redis-server --service-install 2>$null
                & redis-server --service-start 2>$null
            }
            catch {
                Write-Warn "Could not install Redis as a service. Start it manually: redis-server"
            }
        }
        else {
            Write-Warn "Chocolatey not available — skipping Redis install."
            Write-Warn "Redis is optional (only needed for chat/memory features)."
            Write-Warn "To install manually later, see: https://www.memurai.com/"
        }
    }
}
else {
    Write-Info "Skipping Redis installation (-SkipRedis)."
}

# ---------------------------------------------------------------------------
# Refresh PATH
# ---------------------------------------------------------------------------
Write-Host ""
Write-Info "Refreshing PATH environment variable..."
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path
# Also reload from registry via a simple trick
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

# ---------------------------------------------------------------------------
# Phase 5: Python virtual environment + dependencies
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "  Phase 5/6: Python virtual environment..." -ForegroundColor Cyan
Write-Host "  -----------------------------------------" -ForegroundColor Cyan

if (Test-Path (Join-Path $RootDir ".venv")) {
    Write-Warn ".venv already exists. Skipping creation."
}
else {
    Write-Info "Creating Python virtual environment..."
    & python -m venv (Join-Path $RootDir ".venv")
    if (-not $?) { Fatal "Failed to create virtual environment." }
    Write-Info "Virtual environment created at .venv"
}

Write-Info "Upgrading pip..."
& $PipExe install --upgrade pip -q
if (-not $?) { Fatal "Failed to upgrade pip." }

if ($NoSandbox) {
    $InstallSpec = ".[dev,prod]"
    Write-Info "Installing base + dev + prod dependencies (skipping sandbox)..."
}
else {
    $InstallSpec = ".[dev,prod,sandbox]"
    Write-Info "Installing base + dev + prod + sandbox dependencies..."
}

& $PipExe install -e "$RootDir[$InstallSpec]" -q
if (-not $?) { Fatal "Failed to install Python dependencies." }
Write-Info "Python dependencies installed."

# ---------------------------------------------------------------------------
# Phase 6: Frontend
# ---------------------------------------------------------------------------
if (-not $NoFrontend) {
    Write-Host ""
    Write-Host "  Phase 6/6: Building frontend..." -ForegroundColor Cyan
    Write-Host "  --------------------------------" -ForegroundColor Cyan

    $WebDir = Join-Path $RootDir "web"
    if (-not (Test-Path $WebDir)) {
        Write-Warn "web/ directory not found. Skipping frontend build."
    }
    else {
        Write-Info "Installing frontend npm dependencies..."
        Push-Location $WebDir
        try {
            & npm ci
            if (-not $?) { throw "npm ci failed" }
            Write-Info "Building frontend..."
            & npm run build
            if (-not $?) { throw "npm run build failed" }

            $DistHtml = Join-Path $WebDir "dist\index.html"
            if (Test-Path $DistHtml) {
                Write-Info "Frontend build successful — web\dist\index.html"
            }
            else {
                Write-Warn "Frontend build completed but dist\index.html not found."
            }
        }
        finally {
            Pop-Location
        }
    }
}
else {
    Write-Host ""
    Write-Info "Frontend build skipped (-NoFrontend)."
}

# ---------------------------------------------------------------------------
# Data directories & configuration
# ---------------------------------------------------------------------------
Write-Host ""
Write-Info "Creating data directories..."
$null = New-Item -ItemType Directory -Force -Path (Join-Path $RootDir "data\workspace")
$null = New-Item -ItemType Directory -Force -Path (Join-Path $RootDir "data\logs")
$null = New-Item -ItemType Directory -Force -Path (Join-Path $RootDir "data\sessions")
Write-Info "Data directories created under data\"

$EnvFile = Join-Path $RootDir ".env"
$EnvExample = Join-Path $RootDir ".env.example"
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Info "Copied .env.example -> .env"
        Write-Warn "Please edit .env with your API keys and settings."
    }
    else {
        Write-Warn ".env.example not found. Create .env manually."
    }
}
else {
    Write-Info ".env already exists. Skipping copy."
}

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Installation complete!"                     -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:"
Write-Host "    1. Edit .env with your API keys:"
Write-Host "       notepad .env"
Write-Host ""
Write-Host "    2. (Optional) Start Redis if you need chat/memory features:"
Write-Host "       redis-server"
Write-Host ""
Write-Host "    3. Run the platform:"
Write-Host "       run.bat"
Write-Host ""
Write-Host "  Other commands:"
Write-Host "       build.bat           (rebuild frontend)"
Write-Host ""

if ($NoFrontend) {
    Write-Host "  Note: Frontend was not built. Run 'build.bat' when ready." -ForegroundColor Yellow
    Write-Host ""
}
