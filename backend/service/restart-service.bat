@echo off
REM ===========================================================================
REM restart-service.bat - stop, then start the DROID backend service.
REM After a restart the backend always comes up paper-first (startup safety
REM posture) and the single-instance guard refuses a second instance.
REM
REM sc stop/start need Administrator, so elevate once here rather than letting
REM the two child scripts each raise their own UAC prompt.
REM ===========================================================================
call "%~dp0_common.bat"

"%PS%" -NoProfile -Command "exit [int](-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))" >nul 2>&1
if errorlevel 1 (
    echo Requesting Administrator rights to restart the service...
    "%PS%" -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b %errorlevel%
)

echo [1/2] Stopping service...
call "%~dp0stop-service.bat"
if errorlevel 1 (
    echo [ERROR] Stop failed - aborting restart.
    exit /b 1
)

echo.
echo [2/2] Starting service...
call "%~dp0start-service.bat"
if errorlevel 1 exit /b 1

echo.
echo [OK] Restart complete. Verify readiness: status-service.bat
exit /b 0
