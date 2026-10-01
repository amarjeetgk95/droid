@echo off
REM ===========================================================================
REM uninstall-service.bat - stop and de-register the DROID backend service.
REM Leaves code, .venv, .env and all logs untouched.
REM Relaunches itself elevated (UAC) when not run as Administrator.
REM ===========================================================================
call "%~dp0_common.bat"

REM -- elevation ----------------------------------------------------------------
"%PS%" -NoProfile -Command "exit [int](-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))" >nul 2>&1
if errorlevel 1 (
    echo Requesting Administrator rights to uninstall the service...
    "%PS%" -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b %errorlevel%
)

"%SC_EXE%" query "%SVC_NAME%" >nul 2>&1
if not %errorlevel%==0 (
    echo Service "%SVC_NAME%" is not installed - nothing to do.
    exit /b 0
)

echo Stopping service (if running)...
"%SC_EXE%" stop "%SVC_NAME%" >nul 2>&1
set /a tries=0
:wait_stopped
"%SC_EXE%" query "%SVC_NAME%" | "%FINDSTR_EXE%" /C:"STOPPED" >nul
if %errorlevel%==0 goto :stopped
timeout /t 2 /nobreak >nul
set /a tries+=1
if %tries% lss 15 goto :wait_stopped
echo [WARN] Service did not report STOPPED within 30 s - deleting anyway.

:stopped
echo Removing service registration...
"%SC_EXE%" delete "%SVC_NAME%"
if errorlevel 1 (
    echo [ERROR] sc delete failed ^(exit code %errorlevel%^).
    exit /b 1
)

echo.
echo [OK] Service "%SVC_NAME%" uninstalled.
echo      Untouched: backend\app, backend\.venv, backend\.env, logs\,
echo                 backend\service\droid-backend.exe and .xml
echo      (Delete backend\service\droid-backend.exe manually if you also want
echo       to remove the wrapper binary.)
exit /b 0
