@echo off
REM ===========================================================================
REM verify-service.bat - prove the DROID backend service actually self-heals.
REM
REM Runs verify-service-crash-recovery.ps1: checks install/health/single-worker,
REM kills the Python child, then confirms WinSW brought the backend back with
REM exactly one worker and left no orphans.
REM
REM Administrator rights are required (killing the service's own child
REM process needs them), so run this from an ELEVATED terminal:
REM
REM     right-click Start -> "Terminal (Admin)" / "Windows PowerShell (Admin)"
REM     cd /d E:\Droid\backend\service
REM     verify-service.bat
REM
REM or right-click this file -> Run as administrator.
REM
REM Extra switches are passed through, e.g.:
REM     verify-service.bat -StopAfter
REM
REM A full transcript is written to %LOGS_DIR%\verify-service-report.log.
REM ===========================================================================
call "%~dp0_common.bat"

"%PS%" -NoProfile -Command "exit [int](-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Not running as Administrator.
    echo         Killing the service's Python child requires elevation, so this
    echo         check cannot run from a normal prompt.
    echo.
    echo         Open an elevated terminal and re-run:
    echo             cd /d %~dp0
    echo             verify-service.bat
    echo.
    echo         ^(or right-click verify-service.bat -^> Run as administrator^)
    exit /b 1
)

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify-service-crash-recovery.ps1" -ServiceName "%SVC_NAME%" -BaseUrl "http://127.0.0.1:8000" %*
set "RC=%errorlevel%"

echo.
if "%RC%"=="0" (
    echo [OK] Verification passed - the service supervises and restarts the backend.
) else (
    echo [FAIL] Verification reported problems ^(exit code %RC%^).
)
echo      Full transcript: %LOGS_DIR%\verify-service-report.log
echo      Wrapper logs:    %LOGS_DIR%\droid-backend.out.log / .err.log
exit /b %RC%
