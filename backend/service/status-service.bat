@echo off
REM ===========================================================================
REM status-service.bat - report service + API status. Read-only, no elevation.
REM Exit codes: 0 = service RUNNING, 3 = service present but not RUNNING,
REM             1 = not installed.
REM ===========================================================================
call "%~dp0_common.bat"

echo ============================================================
echo  DROID Backend Service - Status
echo ============================================================

if not exist "%WINSW_EXE%" (
    echo [WARN] %WINSW_EXE% not found ^(download-winsw.bat not run yet^).
) else (
    echo [OK]   Wrapper binary present: droid-backend.exe
)
if not exist "%VENV_PYTHON%" (
    echo [WARN] Virtual environment missing: %VENV_PYTHON%
) else (
    echo [OK]   Virtual environment present.
)

echo.
"%SC_EXE%" query "%SVC_NAME%" >nul 2>&1
if not %errorlevel%==0 (
    echo [INFO] Service "%SVC_NAME%" is NOT installed.
    echo        Run install-service.bat as Administrator.
    set "SVC_RC=1"
    goto :api_probe
)

"%SC_EXE%" query "%SVC_NAME%" | findstr /C:"STATE"
"%SC_EXE%" query "%SVC_NAME%" | "%FINDSTR_EXE%" /C:"RUNNING" >nul
if %errorlevel%==0 (
    set "SVC_RC=0"
) else (
    echo [INFO] Service is installed but not RUNNING.
    set "SVC_RC=3"
)

:api_probe
echo.
echo Probing API: http://127.0.0.1:8000/health
curl -s -o nul -w "HTTP %%{http_code}" --max-time 5 http://127.0.0.1:8000/health 2>nul
echo.
echo.
echo Logs: %LOGS_DIR%\droid-backend.out.log ^(+ .err.log^)
echo       %LOGS_DIR%\application.log
exit /b %SVC_RC%
