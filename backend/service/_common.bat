@echo off
REM ===========================================================================
REM _common.bat - shared paths/constants for DROID service scripts.
REM Sourced with:  call "%~dp0_common.bat"
REM DO NOT run directly.
REM
REM NOTE: deliberately NO setlocal here. A setlocal inside a called batch file
REM is unwound when that file ends, so every variable set below would vanish
REM before the calling script uses it. Variables are set in the caller's
REM environment instead (each script runs in its own transient cmd.exe).
REM ===========================================================================
cd /d "%~dp0"

REM WinSW wrapper + config (must sit next to these scripts)
set "WINSW_EXE=%~dp0droid-backend.exe"
set "WINSW_XML=%~dp0droid-backend.xml"

REM Windows service identity (must match <id> in droid-backend.xml)
set "SVC_NAME=DROIDBackend"
set "SVC_DISPLAY=DROID Backend (FastAPI)"

REM Project layout: %~dp0 = backend\service\ (trailing backslash included),
REM so ONE ..\ = backend, TWO ..\ = repo root. (Verified by resolving:
REM E:\Droid\backend\service\..\ = E:\Droid\backend.)
set "BACKEND_DIR=%~dp0.."
set "REPO_ROOT=%~dp0..\.."
set "VENV_PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "LOGS_DIR=%REPO_ROOT%\logs"
REM Normalize away the ..\..\.. segments so echoed paths stay readable.
for %%I in ("%BACKEND_DIR%")  do set "BACKEND_DIR=%%~fI"
for %%I in ("%REPO_ROOT%")   do set "REPO_ROOT=%%~fI"
for %%I in ("%VENV_PYTHON%") do set "VENV_PYTHON=%%~fI"
for %%I in ("%LOGS_DIR%")    do set "LOGS_DIR=%%~fI"

REM Official WinSW v2.12.0 x64 binary (github.com/winsw/winsw)
set "WINSW_URL=https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"

set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not defined SC_EXE set "SC_EXE=%SystemRoot%\System32\sc.exe"
REM Fully qualified on purpose: a bare `find` resolves to GNU find when these
REM scripts are called from a Git-Bash/MSYS shell (PATH shadowing), which
REM silently breaks service-state detection. findstr returns 0 on match, 1 on
REM no match - same contract as find.exe.
if not defined FINDSTR_EXE set "FINDSTR_EXE=%SystemRoot%\System32\findstr.exe"

exit /b 0
