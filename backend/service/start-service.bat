@echo off
REM ===========================================================================
REM start-service.bat - start the DROID backend service.
REM Waits up to ~30 s for the service to report RUNNING.
REM
REM sc start requires Administrator for a LocalSystem service with the default
REM ACL (unelevated: exit code 5), so this script relaunches itself elevated.
REM ===========================================================================
call "%~dp0_common.bat"

REM -- elevation: relaunch self as Administrator if needed ---------------------
"%PS%" -NoProfile -Command "exit [int](-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))" >nul 2>&1
if errorlevel 1 (
    echo Requesting Administrator rights to start the service...
    "%PS%" -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b %errorlevel%
)

if not exist "%WINSW_EXE%" (
    echo [ERROR] %WINSW_EXE% not found.
    echo         Run backend\service\install-service.bat after download-winsw.bat.
    exit /b 1
)
if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment not found:
    echo         %VENV_PYTHON%
    echo         Create it first - see docs\LOCAL_BACKEND_SERVICE.md, section 2.
    exit /b 1
)

"%SC_EXE%" query "%SVC_NAME%" >nul 2>&1
if not %errorlevel%==0 (
    echo [ERROR] Service "%SVC_NAME%" is not installed.
    echo         Run backend\service\install-service.bat first ^(as Administrator^).
    exit /b 1
)

"%SC_EXE%" query "%SVC_NAME%" | "%FINDSTR_EXE%" /C:"RUNNING" >nul
if %errorlevel%==0 (
    echo Service is already running.
    exit /b 0
)

echo Starting %SVC_NAME% ...
"%SC_EXE%" start "%SVC_NAME%" >nul 2>&1
set "RC=%errorlevel%"
if "%RC%"=="1056" (
    echo Service instance already running.
    exit /b 0
)
if "%RC%"=="5" (
    echo [ERROR] Access denied ^(exit code 5^): starting a service needs an
    echo         elevated prompt. Right-click start-service.bat -^> Run as administrator.
    exit /b 1
)
if not "%RC%"=="0" (
    echo [ERROR] sc start failed ^(exit code %RC%^).
    echo         Check the wrapper log: logs\droid-backend.err.log
    exit /b 1
)

REM -- wait for RUNNING (10 x ~3 s) ---------------------------------------------
set /a tries=0
:wait_running
timeout /t 3 /nobreak >nul
"%SC_EXE%" query "%SVC_NAME%" | "%FINDSTR_EXE%" /C:"RUNNING" >nul
if %errorlevel%==0 goto :is_running
set /a tries+=1
if %tries% lss 10 goto :wait_running

echo [ERROR] Service did not reach RUNNING state within 30 s.
echo         Check logs\droid-backend.err.log and logs\application.log
echo         (a port-8000 conflict refuses the start - see section 12 of the docs).
exit /b 1

:is_running
echo [OK] Service is RUNNING.
echo      API:     http://127.0.0.1:8000/health
echo      Logs:    logs\droid-backend.out.log + logs\application.log
exit /b 0
