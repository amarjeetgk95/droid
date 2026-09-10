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

try {
    $probe = New-Object Net.Sockets.TcpClient
    $probe.Connect("127.0.0.1", 8000)
    $probe.Close()
    Write-Host "Port 8000 is already in use - another backend is running." -ForegroundColor Yellow
    Write-Host "Close the old window (or run: Get-Process python | Stop-Process) and retry."
    exit 1
} catch { }

& $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
