# AI Agent Platform — Windows Uninstall Script
#
# Usage:
#   powershell -File uninstall.ps1
#   powershell -File uninstall.ps1 -All         # Also remove data/ directory
#   powershell -File uninstall.ps1 -Full        # Above + prompt to uninstall system packages
#
param(
    [switch]$All,
    [switch]$Full,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Write-Info    { Write-Host "[INFO]  $args" -ForegroundColor Cyan }
function Write-Success { Write-Host "[OK]    $args" -ForegroundColor Green }
function Write-Warn    { Write-Host "[WARN]  $args" -ForegroundColor Yellow }
function Write-Error   { Write-Host "[ERROR] $args" -ForegroundColor Red }

if ($Help) {
    Write-Host @"
Usage: powershell -File uninstall.ps1 [-All] [-Full] [-Help]

  (no flag)  Remove Python venv, node_modules, and frontend build
  -All       Also remove data/ directory (workspace, logs, sessions)
  -Full      Above + prompt to uninstall system packages (Python, Node, Redis)
  -Help      Show this help
"@
    exit 0
}

# Summary
Write-Host ""
Write-Info "============================================"
Write-Info "  AI Agent Platform — Uninstall (Windows)"
Write-Info "============================================"
Write-Host ""
if ($Full) {
    Write-Warn "Mode: FULL (project files + data + system packages)"
} elseif ($All) {
    Write-Warn "Mode: ALL (project files + data directory)"
} else {
    Write-Info "Mode: standard (project files only, data/ preserved)"
}
Write-Host ""

# Confirmation
if ($Full) {
    $response = Read-Host "Proceed with full uninstall? [y/N]"
} else {
    $response = Read-Host "Proceed with uninstall? [y/N]"
}
if ($response -notmatch '^[yY]$') {
    Write-Info "Aborted."
    exit 0
}

$Removed = @()

# --- Remove Python virtual environment ---
if (Test-Path ".venv") {
    Remove-Item -Recurse -Force ".venv"
    $Removed += ".venv\"
    Write-Success "Removed .venv\"
} else {
    Write-Info "No .venv\ found, skipping"
}

# --- Remove frontend build artifacts ---
if (Test-Path "web\dist") {
    Remove-Item -Recurse -Force "web\dist"
    $Removed += "web\dist\"
    Write-Success "Removed web\dist\"
} else {
    Write-Info "No web\dist\ found, skipping"
}

# --- Remove node_modules ---
if (Test-Path "web\node_modules") {
    Remove-Item -Recurse -Force "web\node_modules"
    $Removed += "web\node_modules\"
    Write-Success "Removed web\node_modules\"
} else {
    Write-Info "No web\node_modules\ found, skipping"
}

# --- Remove Python caches ---
Get-ChildItem -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Directory -Filter "*.egg-info" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Info "Cleaned __pycache__ and *.egg-info"

# --- Remove dist\ (python wheel) ---
if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
    $Removed += "dist\"
    Write-Success "Removed dist\"
}

# --- Remove data directory (-All or -Full) ---
if ($All -or $Full) {
    if (Test-Path "data") {
        Write-Warn "==========================================="
        Write-Warn "  About to remove data\ directory"
        Write-Warn "  This includes:"
        Write-Warn "    - User workspaces"
        Write-Warn "    - Session history"
        Write-Warn "    - Application logs"
        Write-Warn "==========================================="
        $dataConfirm = Read-Host "Type 'DELETE' to confirm removal of data\"
        if ($dataConfirm -eq "DELETE") {
            Remove-Item -Recurse -Force "data"
            $Removed += "data\"
            Write-Success "Removed data\ (workspace, logs, sessions)"
        } else {
            Write-Info "data\ preserved (confirmation did not match)"
        }
    } else {
        Write-Info "No data\ found, skipping"
    }
}

# --- Remove system packages (-Full only) ---
if ($Full) {
    Write-Host ""
    Write-Warn "System package removal uses winget. Each package requires separate confirmation."
    Write-Host ""

    # Python
    $response = Read-Host "Remove Python 3.11? [y/N]"
    if ($response -match '^[yY]$') {
        winget uninstall Python.Python.3.11 2>$null
        Write-Success "Python 3.11 uninstall initiated"
    } else {
        Write-Info "Python preserved"
    }

    # Node.js
    $response = Read-Host "Remove Node.js? [y/N]"
    if ($response -match '^[yY]$') {
        winget uninstall OpenJS.NodeJS.LTS 2>$null
        Write-Success "Node.js uninstall initiated"
    } else {
        Write-Info "Node.js preserved"
    }

    # Redis
    $response = Read-Host "Remove Redis (via Chocolatey)? [y/N]"
    if ($response -match '^[yY]$') {
        choco uninstall redis-64 -y 2>$null
        Write-Success "Redis uninstall initiated"
    } else {
        Write-Info "Redis preserved"
    }
}

# --- Summary ---
Write-Host ""
Write-Success "============================================"
Write-Success "  Uninstall complete"
Write-Success "============================================"
Write-Host ""
if ($Removed.Count -gt 0) {
    Write-Info "Removed: $($Removed -join ', ')"
} else {
    Write-Info "Nothing was removed."
}
Write-Host ""
Write-Info "The following remain on disk (not managed by this script):"
Write-Info "  - Source code (git repository)"
Write-Info "  - .env file (contains your API keys)"
Write-Info "  - config\ directory"
Write-Host ""
Write-Info "To remove everything, delete the project directory:"
Write-Info "  Remove-Item -Recurse -Force `"$ScriptDir`""
Write-Host ""
