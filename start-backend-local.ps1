# Worker for Start-Backend.cmd - runs the server in the foreground of its own
# window. Closing that window stops the backend. Do not run hidden: uvicorn
# --reload spawns child processes that would be orphaned by a hidden launch.
$host.ui.RawUI.WindowTitle = "DROID backend :8000"
Set-Location -LiteralPath (Join-Path $PSScriptRoot "backend")

$venvPython = Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "ERROR: backend\.venv not found." -ForegroundColor Red
    Write-Host "Run the first-time setup in docs/LOCAL_HOSTING.md, then retry."
    exit 1
}

$env:PYTHONPATH = (Join-Path $PSScriptRoot "backend")
$env:FORECAST_SCHEDULER_ENABLED = "on"
$env:FLOW_SCHEDULER_ENABLED = "on"

# Auto-free port 8000 if a zombie process is holding it
try {
    $conns = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -ne 0 -and $_.OwningProcess -ne $PID }
    if ($conns) {
        $pidsToKill = $conns | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($procId in $pidsToKill) {
            Write-Host "Port 8000 occupied by PID $procId - auto-recycling for 1-click launch..." -ForegroundColor Yellow
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
    }
} catch {
    try {
        $lines = netstat -ano | Select-String ":8000\s+.*LISTENING\s+(\d+)"
        foreach ($line in $lines) {
            if ($line.Matches[0].Groups[1].Value) {
                $procId = [int]$line.Matches[0].Groups[1].Value
                if ($procId -gt 0 -and $procId -ne $PID) {
                    Write-Host "Port 8000 occupied by PID $procId - auto-recycling..." -ForegroundColor Yellow
                    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                }
            }
        }
        Start-Sleep -Seconds 1
    } catch { }
}

& $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

