@echo off
setlocal
REM =========================================================================
REM DROID Backend & Subsystems 1-Click Unified Launcher
REM Double-click this file:
REM   1. Spawns backend in dedicated window with auto-port recycling
REM   2. Initializes all elements (Feed, Workers, Telegram, Schedulers)
REM   3. Verifies health via /health/subsystems HUD
REM   4. Launches https://fo-droid.web.app
REM =========================================================================
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

echo =========================================================================
echo                    DROID ENGINE - 1-CLICK LAUNCHER
echo =========================================================================
echo [1/3] Starting backend engine with all elements...

start "DROID backend :8000" "%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-backend-local.ps1"

echo [2/3] Waiting for all elements to initialize and verify...
"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "& { $deadline=(Get-Date).AddSeconds(60); while ((Get-Date) -lt $deadline) { try { $sub = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health/subsystems' -TimeoutSec 2; if ($sub.status -eq 'ok') { Write-Host ''; Write-Host '  [OK] FastAPI Server Running        -> http://127.0.0.1:8000' -ForegroundColor Green; Write-Host '  [OK] Central Market Feed Ingestion -> LIVE' -ForegroundColor Green; Write-Host '  [OK] Automated Signal Worker Loop  -> ACTIVE (Risk 3s | Scalp 10s | Intraday 30s)' -ForegroundColor Green; Write-Host '  [OK] 1H Forecast & Flow Schedulers -> RUNNING' -ForegroundColor Green; Write-Host '  [OK] Telegram Integration Stack    -> ACTIVE' -ForegroundColor Green; Write-Host ''; Write-Host '[3/3] All elements verified! Opening DROID Trading Desk...' -ForegroundColor Cyan; Start-Process 'https://fo-droid.web.app'; exit 0 } } catch { try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health/live' -TimeoutSec 2; if ($r.StatusCode -eq 200) { Write-Host ''; Write-Host '  [OK] Backend Server Ready -> http://127.0.0.1:8000' -ForegroundColor Green; Write-Host '[3/3] Opening DROID Trading Desk...' -ForegroundColor Cyan; Start-Process 'https://fo-droid.web.app'; exit 0 } } catch {} }; Start-Sleep -Seconds 2 }; Write-Host 'Backend taking longer than expected. Check the DROID backend window for details.' -ForegroundColor Yellow; Start-Process 'https://fo-droid.web.app'; exit 0 }"

exit /b 0

