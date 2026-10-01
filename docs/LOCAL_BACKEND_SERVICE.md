> # RETIRED — not the default runtime
>
> **The supported way to start the backend is the CMD launcher:**
> double-click `Start-Backend.cmd` in the repo root (it spawns
> `start-backend-local.ps1`, waits for `/health/subsystems`, then opens the
> trading desk). That is the default and the only path you need.
>
> This document describes an abandoned experiment that ran the backend as a
> WinSW Windows service. **Do not install `DROIDBackend`**: the install script
> registers it with delayed auto-start, so it would grab port 8000 on every
> boot and block the launcher. If it is still installed on a machine, remove it with
> `backend\service\uninstall-service.bat` (Administrator) or at minimum run
> `sc config DROIDBackend start= demand`.
>
> The parts of that work that are still useful and still active are the
> startup single-instance port guard (`backend\app\core\startup_safety.py`)
> and the rotating `logs\application.log` file log — both now belong to the
> normal CMD runtime.

# Local Backend as a Windows Service (WinSW) — archived notes

Run the DROID FastAPI backend as a native Windows service so it starts with
your PC, restarts itself after a crash, and never needs a terminal window.
No Docker Desktop, no WSL, no VM — just the existing Python virtual
environment supervised by a 10 MB service wrapper.

```
Windows
   │
   └── WinSW (droid-backend.exe, a Windows service)
        │
        └── Python (.venv) — FastAPI / Uvicorn on 127.0.0.1:8000
             │
             ├─ Central market-data feed (FYERS)
             ├─ Signal engine & paper book
             ├─ Telegram stack
             └─ Supabase persistence
```

Frontend unaffected: `https://fo-droid.web.app` keeps calling
`http://127.0.0.1:8000` exactly as before (this is `NEXT_PUBLIC_API_URL` in
`frontend/.env.local` and `DEFAULT_BACKEND_BASE` in
`frontend/src/lib/settingsConstants.ts`). Nothing to change there.

---

## 1. Prerequisites

- Windows 10/11 (x64)
- Python ≥ 3.12 available on PATH (only for initial setup)
- The DROID repository (this folder)
- Internet once, to download the WinSW wrapper (see step 4)

## 2. Virtual-environment setup (skip if `backend\.venv` already exists)

```bat
cd /d E:\Droid\backend
python -m venv .venv
```

## 3. Dependency installation (skip if already installed)

```bat
cd /d E:\Droid\backend
.venv\Scripts\python.exe -m pip install -e .
```

## 4. WinSW setup (one-time)

The wrapper binary is not committed. Fetch it once:

```bat
cd /d E:\Droid\backend\service
download-winsw.bat
```

This downloads **WinSW v2.12.0 (x64)** from the official GitHub releases and
names it `droid-backend.exe`. Verify `backend\service\droid-backend.exe`
exists (status-service.bat warns if it does not).

Manual alternative: download
https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe in a
browser, save it as `backend\service\droid-backend.exe`.

## 5. Service installation (Administrator, one-time)

Double-click `backend\service\install-service.bat` (or run it from a
terminal — it relaunches itself elevated via UAC). It checks the wrapper,
the venv and `backend\.env`, then registers the service:

```
Name:    DROIDBackend
Display: DROID Backend (FastAPI)
Startup: Automatic (delayed) — starts after boot once network is up
```

## 6. Starting the service

```bat
backend\service\start-service.bat
```

No admin rights needed. Waits up to 30 s for `RUNNING`, then prints the
health URL. The first start after boot can take ~1 minute to become
*ready* (FYERS connect, DB restore) — the process is alive immediately.

## 7. Stopping the service

```bat
backend\service\stop-service.bat
```

Sends the graceful-stop signal; uvicorn runs the full shutdown path
(signal worker → morning briefing → auto-sync → Telegram →
FYERS stream → central feed → snapshot → write pipeline). Waits up to 30 s.

## 8. Restarting the service

```bat
backend\service\restart-service.bat
```

Restart always lands **paper-first** (see "Trading safety" below).

Prove that supervision works end to end with section 16
(`backend\service\verify-service.bat`).

## 9. Checking status

```bat
backend\service\status-service.bat
```

Prints prerequisite checks, the service state, and probes
`http://127.0.0.1:8000/health`. Exit codes: `0` running, `3` installed but
stopped, `1` not installed. No elevation.

## 10. Viewing logs

All logs live in the repo-root `logs\` folder:

| File | Content |
|---|---|
| `logs\droid-backend.out.log` | Wrapper capture of application stdout (rolled at 10 MB, 8 kept) |
| `logs\droid-backend.err.log` | Wrapper capture of stderr (same rolling) |
| `logs\application.log` | Rotating app log (10 MB × 10) — structured events incl. uvicorn startup/access, JSON in production mode, console-style in development |

```bat
:: live view (Ctrl+C to stop)
powershell Get-Content E:\Droid\logs\application.log -Wait -Tail 50

:: latest errors
powershell Get-Content E:\Droid\logs\droid-backend.err.log -Tail 100
```

Old rolls (`*.1.out.log`, …, `application.log.1`, …) are removed
automatically. Secrets (FYERS/Supabase/Telegram/OpenRouter keys, tokens,
passwords) are read from `backend\.env` and are never written to logs.

## 11. Uninstalling the service

```bat
backend\service\uninstall-service.bat   (Administrator)
```

Stops and de-registers the service. Code, `.venv`, `.env` and logs are
untouched.

---

## 12. Troubleshooting: port 8000 already in use

The backend refuses to start a second instance on the same address —
uvicorn's own bind would otherwise silently succeed twice on Windows
(SO_REUSEADDR) and split the tick feed between two processes. On conflict
the service start fails with:

```
Cannot start: 127.0.0.1:8000 is already in use (WinError 10048).
Stop the other backend instance first (service\status-service.bat or the
manual launcher window).
```

Find and stop the other instance:

```bat
:: which PID listens on 8000?
netstat -ano | findstr :8000 | findstr LISTENING

:: what is that PID?
tasklist /FI "PID eq <pid>"

:: is it the service?
backend\service\status-service.bat
```

- **Service running** → you are done; use it, or `stop-service.bat` before
  developing.
- **Manual window open** (title `DROID backend :8000`) → close that window
  (Start-Backend.cmd) — do not run both at once.
- **Zombie python.exe** → `taskkill /PID <pid> /F`, then
  `start-service.bat`.

## 13. Troubleshooting: service fails to start

1. `logs\droid-backend.err.log` — the wrapper logs the Python traceback
   here; `logs\application.log` has the structured story.
2. Common causes:
   - **Port conflict** → section 12 above.
   - **`backend\.env` missing/invalid** → the app logs
     `startup_config_error` and exits; fix `.env` (section 14).
   - **FYERS unreachable / token expired** → the app *stays up* by design
     (degraded, retries in background); check `/ready` instead of the
     service state.
   - **venv moved** → `droid-backend.xml` points at
     `%BASE%\..\.venv\Scripts\python.exe`; recreate the venv or edit the
     `<executable>` line.
3. After fixing, `restart-service.bat`.
4. WinSW restarts the process automatically ~10 s after an unexpected exit
   (`onfailure` in the XML; SCM recovery mirrors it).

## 14. Troubleshooting: environment variables

- The service runs `python.exe -m uvicorn` with working directory
  `backend\`, so the app loads `backend\.env` exactly like development.
  Secrets stay there — never in `droid-backend.xml`.
- Only non-secret runtime knobs live in the XML (`PYTHONPATH`,
  `PYTHONUNBUFFERED`, scheduler flags) plus the bind arguments
  (`--host 127.0.0.1 --port 8000`).
- To change host/port: edit the `<arguments>` line in
  `backend\service\droid-backend.xml` **and** `BACKEND_HOST`/`BACKEND_PORT`
  in `backend\.env` (they are mirrored), then `restart-service.bat`.
  Keep 127.0.0.1: the API is loopback-only by design and a non-loopback
  bind with `AUTH_REQUIRED=false` is refused at startup.
- A wrong `DATABASE_URL` does not prevent boot — the DB degrades, readiness
  reports `database: unavailable`.

## 15. Development vs service mode

| | Development | Stable runtime |
|---|---|---|
| Start | `Start-Backend.cmd` or `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` (from `backend\`) | `start-service.bat` (or boot) |
| Supervision | none | WinSW + SCM recovery |
| Port | 8000 | 8000 |
| Code reload | relaunch after edits | none (restart service after code changes) |

Both modes are mutually exclusive — the startup guard fails the second
instance with a clear message (section 12). After editing backend code:
`restart-service.bat`.

## 16. Verifying crash recovery (scripted)

The service is only useful if it really does restart the backend. Prove it
on this machine, from an **elevated** terminal (killing the service's own
child process needs Administrator):

```bat
cd /d E:\Droid\backend\service
verify-service.bat
```

(or right-click `verify-service.bat` → *Run as administrator*)

It runs `verify-service-crash-recovery.ps1` and checks, in order:

| # | Check | Passes when |
|---|---|---|
| 1 | service installed + RUNNING | SCM state is `Running` (starts it if stopped) |
| 2 | one wrapper process | exactly one `droid-backend.exe` |
| 3 | one python child | exactly one `python.exe` owned by that wrapper |
| 4 | API answers | `GET /health` → 200, then `GET /ready` → 200 |
| 5 | one listener | exactly one PID listening on 127.0.0.1:8000 |
| 6 | signal worker | `/health/subsystems` → `signal_worker: true` |
| 7 | **crash is detected** | a forced kill of the python child leaves the service RUNNING |
| 8 | **automatic restart** | a NEW python child appears (~10 s) and `/ready` returns 200 |
| 9 | no duplicates | still one wrapper, one child, one listener |
| 10 | one boot in the log | exactly one `startup_single_instance_guard_ok` since the kill |
| 11 | posture logged | `startup_trading_safety_posture` present for the restart |
| 12 | no duplicated worker | worker-start log lines consistent with one boot |

Exit code `0` = all checks passed, `1` = at least one failed. The full
transcript is written to `logs\verify-service-report.log`, so a failing run
can be read after the console closes.

Add `-StopAfter` to also stop the service at the end and assert that no
orphan `python.exe` survives (the graceful lifespan shutdown logs
`SHUTDOWN COMPLETE` in `logs\application.log`):

```bat
verify-service.bat -StopAfter
```

### Manual equivalent

If you would rather watch it by hand:

```bat
:: 1. install once, then start
backend\service\install-service.bat
backend\service\start-service.bat

:: 2. baseline: which wrapper owns which python?
powershell "Get-CimInstance Win32_Process -Filter \"Name='droid-backend.exe'\" | Select-Object ProcessId"
powershell "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Select-Object ProcessId,ParentProcessId"

:: 3. confirm the API and the single worker
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/health/subsystems

:: 4. simulate a crash: kill the child (from an ELEVATED prompt), NOT the wrapper
taskkill /PID <python-child-pid> /F

:: 5. within ~10 s a new python.exe appears under the same wrapper;
::    re-check /ready and the two process lists above

:: 6. what the service saw
powershell Get-Content E:\Droid\logs\droid-backend.out.log -Tail 40
powershell Get-Content E:\Droid\logs\application.log -Tail 60
```

Expected outcome: the wrapper PID is unchanged, the python PID is new, the
SCM state never leaves `Running`, `/ready` returns to 200 on its own, and
`logs\application.log` shows a second `startup_single_instance_guard_ok`
plus a fresh `automated_signal_worker_started` — one backend, one signal
worker, no split feed.

**Kill the wrapper instead of the child and you are testing the SCM, not
WinSW:** the SCM recovery action (`sc failure … restart/10000`) restarts
the service ~10 s later. Both layers are configured; the script tests the
inner one because that is the failure users actually hit.

## Health & readiness endpoints

| Endpoint | Meaning |
|---|---|
| `GET /health` (= `/health/live`, `/live`) | Process alive. Cheap, always 200 while serving. |
| `GET /ready` (= `/health/ready`) | Aggregate readiness. `checks`: `central_feed` (hard gate — 503 when down), `database`, `signal_worker`, `broker_token`, `trading_posture`. A DB or FYERS outage degrades the report, never the process. |
| `GET /health/subsystems` | Full element-level diagnostics. |

## Crash recovery & trading safety

- **Crash recovery:** any unexpected process exit is restarted by WinSW
  after ~10 s; the SCM failure action mirrors this (reset after 1 day).
- **Degrade, don't die:** FYERS outages retry with backoff and surface via
  `/ready`; Supabase hiccups are retried inside the app. Only genuinely
  unrecoverable startup errors exit the process (and get restarted).
- **Single instance:** enforced in-process at startup (section 12).
- **No duplicated workers:** every engine starts once per process inside
  the lifespan and is torn down on service stop; there is exactly one
  market-data loop and one signal loop.
- **Trading safety on restart:** the backend is paper-first by
  construction — automated signals execute to the paper book; live orders
  go only through an explicit, fail-closed live-adapter path. Every boot
  logs an explicit `startup_trading_safety_posture` record (and warns if
  `INSTITUTIONAL_LIVE_MODE=true` is persisted). A restart cannot arm live
  trading by itself.
