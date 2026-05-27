$ErrorActionPreference = "SilentlyContinue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Ports = @(8000, 3000, 3001, 3002)
$Targets = @{}

function Add-Target {
    param(
        [int]$ProcessId,
        [string]$Reason
    )

    if ($ProcessId -le 0) {
        return
    }

    if ($Targets.ContainsKey($ProcessId)) {
        if ($Targets[$ProcessId] -notlike "*$Reason*") {
            $Targets[$ProcessId] = "$($Targets[$ProcessId]), $Reason"
        }
    } else {
        $Targets[$ProcessId] = $Reason
    }
}

Write-Host ""
Write-Host "Stopping AI Agent services..."
Write-Host ""

foreach ($Port in $Ports) {
    $Connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($Connection in $Connections) {
        Add-Target -ProcessId ([int]$Connection.OwningProcess) -Reason "port $Port"
    }
}

# The backend may have a parent watchdog/reloader process that is not the port owner.
$GatewayProcesses = Get-CimInstance Win32_Process | Where-Object {
    $CommandLine = $_.CommandLine
    $CommandLine -and
        $CommandLine.IndexOf($ScriptDir, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $CommandLine.IndexOf("gateway.server", [System.StringComparison]::OrdinalIgnoreCase) -ge 0
}

foreach ($Process in $GatewayProcesses) {
    Add-Target -ProcessId ([int]$Process.ProcessId) -Reason "gateway.server"
}

if ($Targets.Count -eq 0) {
    Write-Host "[OK] No AI Agent services found on ports $($Ports -join ', ')."
    exit 0
}

foreach ($Entry in $Targets.GetEnumerator()) {
    $ProcessId = [int]$Entry.Key
    $Process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $Process) {
        continue
    }

    Write-Host "Stopping PID $ProcessId ($($Process.Name), $($Entry.Value))..."
    & taskkill.exe /F /T /PID $ProcessId | Out-Null
}

Start-Sleep -Seconds 1

$Remaining = foreach ($Port in $Ports) {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        [PSCustomObject]@{
            Port = $Port
            PID = $_.OwningProcess
        }
    }
}

if ($Remaining) {
    Write-Host ""
    Write-Warning "Some configured ports are still listening:"
    $Remaining | Format-Table -AutoSize
    exit 1
}

Write-Host ""
Write-Host "[OK] AI Agent services stopped."
