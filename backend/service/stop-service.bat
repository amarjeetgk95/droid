@echo off
REM ===========================================================================
REM stop-service.bat - stop the DROID backend service gracefully.
REM WinSW sends the stop signal; uvicorn then runs the full shutdown path
REM (workers, feeds, Telegram) before exiting. Waits up to ~30 s.
REM No admin rights needed.
REM ===========================================================================
call "%~dp0_common.bat"

REM -- elevation: sc stop requires Administrator for this service (same ACL as
REM    start) - relaunch elevated if needed. ---------------------------------
"%PS%" -NoProfile -Command "exit [int](-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))" >nul 2>&1
if errorlevel 1 (
    echo Requesting Administrator rights to stop the service...
    "%PS%" -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b %errorlevel%
)

"%SC_EXE%" query "%SVC_NAME%" >nul 2>&1
if not %errorlevel%==0 (
    echo Service "%SVC_NAME%" is not installed - nothing to stop.
    exit /b 0
)

"%SC_EXE%" query "%SVC_NAME%" | "%FINDSTR_EXE%" /C:"STOPPED" >nul
if %errorlevel%==0 (
    echo Service is already stopped.
    exit /b 0
)

echo Stopping %SVC_NAME% ...
"%SC_EXE%" stop "%SVC_NAME%" >nul 2>&1
set "RC=%errorlevel%"
if "%RC%"=="1062" (
    echo Service not running.
    exit /b 0
)
if not "%RC%"=="0" if not "%RC%"=="1066" (
    echo [WARN] sc stop returned exit code %RC% - waiting for state anyway.
)

set /a tries=0
:wait_stopped
timeout /t 3 /nobreak >nul
"%SC_EXE%" query "%SVC_NAME%" | "%FINDSTR_EXE%" /C:"STOPPED" >nul
if %errorlevel%==0 goto :is_stopped
set /a tries+=1
if %tries% lss 10 goto :wait_stopped

echo [ERROR] Service did not reach STOPPED state within 30 s.
echo         A graceful shutdown may still be in progress; check
echo         logs\application.log. If it stays stuck, see the docs
echo         (section 12) - do NOT kill the process blindly mid-session.
exit /b 1

:is_stopped
echo [OK] Service stopped cleanly.
exit /b 0
