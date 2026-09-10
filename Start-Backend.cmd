@echo off
setlocal
REM DROID backend one-click launcher.
REM Double-click this file: opens the server in its own window, waits until
REM healthy, then opens the Firebase frontend. Close the "DROID backend"
REM window to stop the server.
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
start "DROID backend :8000" "%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-backend-local.ps1"
"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "& { $deadline=(Get-Date).AddSeconds(90); while ((Get-Date) -lt $deadline) { try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health/live' -TimeoutSec 3; if ($r.StatusCode -eq 200) { Write-Host ''; Write-Host '  DROID backend READY  ->  http://127.0.0.1:8000  (docs: /docs)' -ForegroundColor Green; Write-Host '  Opening Firebase frontend...'; Start-Process 'https://fo-droid.web.app'; exit 0 } } catch {}; Start-Sleep -Seconds 2 }; Write-Host '  Backend did not become healthy in 90s. Check the DROID backend window for errors.' -ForegroundColor Red; exit 1 }"
pause
