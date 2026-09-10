# Local Hosting — DROID (Windows)

Backend runs on your laptop, frontend lives on Firebase Hosting. No cloud
backend, no bandwidth limit.

## What runs where

- Backend (FastAPI, your laptop): `http://127.0.0.1:8000` — docs at `/docs`, health at `/health/live`
- Frontend (Firebase Hosting): `https://fo-droid.web.app` — calls the local backend over loopback (works because the site runs in YOUR browser on THIS machine)
- Database: optional. Backend works without `DATABASE_URL` (signals run in-memory, `/health/db` shows error — normal).

## 1. First time only

```powershell
# Backend deps (already done once — skip if backend\.venv exists)
cd E:\Droid\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install ".[ml]"

# Frontend deps (already done once — skip if frontend\node_modules exists)
cd E:\Droid\frontend
npm install

# Firebase login (already done once — skip if `firebase projects:list` works)
firebase login
```

Node: project wants Node 20 (`frontend\.node-version`). You have Node 24 — build still works. If you get weird errors, install Node 20 via `nvm`/`volta` and retry.

## 2. Daily use — start backend (one click)

Double-click **`E:\Droid\Start-Backend.cmd`**. It opens the server in its own
window, waits until healthy, then opens `https://fo-droid.web.app` for you.
Close the "DROID backend" window to stop the server.

That is the only thing you run day-to-day. The frontend is already live on
Firebase — no localhost frontend server needed.

## 3. After changing frontend code — redeploy (one click)

Double-click **`E:\Droid\Deploy-Frontend.cmd`**. It rebuilds the static export
(with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` baked in) and pushes it to
Firebase Hosting. No need to run this unless frontend code changed.

## 4. Stop

Close the "DROID backend" window (or `Ctrl+C` in it).

## Notes / limits

- Backend must be running for the Firebase site to show live data. If the site shows connection errors, the backend window is closed — double-click `Start-Backend.cmd` again.
- Broker login (Fyers OAuth): broker portals only accept public `https` redirect URIs, so `http://127.0.0.1:8000` callbacks will be rejected. For local testing either paste tokens manually via Settings UI / `FYERS_ACCESS_TOKEN` env, or expose backend with `ngrok http 8000` / `cloudflared tunnel` and register that HTTPS URL in the broker portal.
- Telegram: fully works on localhost. The backend auto-uses getUpdates long-polling (no public webhook needed) — Settings → Telegram → Connect Telegram Account → open the bot → Start → chat links, test alerts and signal notifications flow. Status endpoint reports `"inbound_mode": "polling"`. If you later put the backend on public HTTPS, it switches back to webhook mode automatically. Set `TELEGRAM_POLLING_ENABLED=false` to force webhook mode.
- Market data after hours: `FyersProvider` reports `Market closed — serving last-known snapshot`. Normal at night/weekends.
- Port busy (`Port 8000 is already in use`): another backend still running — close old window or `Get-Process python | Stop-Process`.
- Scripts are plain ASCII on purpose: Windows PowerShell 5.1 misreads BOM-less `.ps1` files containing Unicode (e.g. em-dashes) and fails to parse. Do not add non-ASCII characters to `*.ps1`/`*.cmd` files.
