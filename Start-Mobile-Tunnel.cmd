@echo off
setlocal
REM DROID mobile access: exposes local backend via Cloudflare tunnel, rebuilds
REM frontend with the public URL, deploys to Firebase. Double-click to run.
REM Keep this window + the backend window open while using your mobile.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-mobile-tunnel.ps1"
pause
