@echo off
REM ===========================================================================
REM install-service.bat - register "DROID Backend (FastAPI)" as a Windows service.
REM
REM Prerequisites (checked below):
REM   backend\service\droid-backend.exe     (run download-winsw.bat once)
REM   backend\.venv\Scripts\python.exe      (project virtual environment)
REM   backend\.env                          (credentials - never committed)
REM
REM Administrator rights are required to write to the SCM; if this script is
REM not elevated it relaunches itself elevated (UAC prompt).
REM ===========================================================================
call "%~dp0_common.bat"

REM -- elevation: relaunch self as Administrator if needed ---------------------
"%PS%" -NoProfile -Command "exit [int](-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))" >nul 2>&1
if errorlevel 1 (
    echo Requesting Administrator rights to install the service...
    "%PS%" -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b %errorlevel%
)

REM -- prerequisite checks ------------------------------------------------------
if not exist "%WINSW_EXE%" (
    echo [ERROR] %WINSW_EXE% not found.
    echo         Fetch it first: run backend\service\download-winsw.bat
    echo         ^(downloads WinSW v2.12.0 from %WINSW_URL%^)
    exit /b 1
)
if not exist "%WINSW_XML%" (
    echo [ERROR] %WINSW_XML% not found - service configuration missing.
    exit /b 1
)
if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment not found:
    echo         %VENV_PYTHON%
    echo         Create it first - see docs\LOCAL_BACKEND_SERVICE.md, section 2.
    exit /b 1
)
if not exist "%BACKEND_DIR%\.env" (
    echo [WARNING] backend\.env not found. The service will boot with defaults;
    echo           copy .env.example to .env and fill in your credentials.
)

REM -- install ------------------------------------------------------------------
"%SC_EXE%" query "%SVC_NAME%" >nul 2>&1
if %errorlevel%==0 (
    echo [ERROR] Service "%SVC_NAME%" is already installed.
    echo         Use restart-service.bat / stop-service.bat / uninstall-service.bat.
    exit /b 1
)

echo Installing service "%SVC_NAME%"...
REM start= delayed-auto : automatic start, delayed until OS/network settle
REM binPath quotes use sc.exe's \" escaping for paths with spaces.
"%SC_EXE%" create "%SVC_NAME%" binPath= "\"%WINSW_EXE%\"" DisplayName= "%SVC_DISPLAY%" start= delayed-auto
if errorlevel 1 goto :create_failed

REM Auto-restart on crash: restart after 10 s, failure counter resets after 1 day.
"%SC_EXE%" failure "%SVC_NAME%" reset= 86400 actions= restart/10000
if errorlevel 1 echo [WARN] Could not set recovery options - the service still runs, but the wrapper's onfailure entries in droid-backend.xml apply at runtime.

"%SC_EXE%" description "%SVC_NAME%" "DROID trading-intelligence backend: FastAPI/Uvicorn on 127.0.0.1:8000. Managed by WinSW - config: backend\service\droid-backend.xml."

echo.
echo [OK] Service installed:
echo      Name:    %SVC_NAME%
echo      Display: %SVC_DISPLAY%
echo      Startup: Automatic (delayed)
echo.
echo Next: start-service.bat  ^(no admin rights needed^)
exit /b 0

:create_failed
echo [ERROR] sc create failed (exit code %errorlevel%).
echo         Are you running elevated? See docs\LOCAL_BACKEND_SERVICE.md, section 12.
exit /b 1
