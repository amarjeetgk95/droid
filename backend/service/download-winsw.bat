@echo off
REM ===========================================================================
REM download-winsw.bat - fetch WinSW v2.12.0 (x64) and name it droid-backend.exe.
REM Run ONCE before install-service.bat. Requires internet; no admin rights.
REM WinSW v2 is a self-contained ~10 MB executable (no .NET install needed on
REM Win10/11). Pinned version = reproducible installs.
REM ===========================================================================
call "%~dp0_common.bat"

if exist "%WINSW_EXE%" (
    echo WinSW wrapper already present: %WINSW_EXE%
    exit /b 0
)

echo Downloading WinSW v2.12.0 x64 ...
echo   %WINSW_URL%
"%PS%" -NoProfile -ExecutionPolicy Bypass -Command ^
  "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -UseBasicParsing -Uri '%WINSW_URL%' -OutFile 'droid-backend.exe' -TimeoutSec 180 } catch { Write-Host ('Download failed: ' + $_.Exception.Message) -ForegroundColor Red; exit 1 }"
if errorlevel 1 (
    echo.
    echo [ERROR] Download failed. Fetch it manually in a browser:
    echo         %WINSW_URL%
    echo         Save the file into backend\service\ and rename it to droid-backend.exe.
    exit /b 1
)

for %%F in ("%WINSW_EXE%") do echo [OK] Saved %%~nxF ^(%%~zF bytes^).
echo.
echo Next: install-service.bat  ^(as Administrator^)
exit /b 0
