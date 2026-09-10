@echo off
setlocal
REM DROID frontend deploy: builds the static export and pushes it to
REM Firebase Hosting (https://fo-droid.web.app). Double-click to run.
REM Run this again every time you change frontend code.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy-frontend-firebase.ps1"
pause
