# DROID — AI-Powered Indian F&O Market Analysis Platform

DROID is a personal trading-intelligence terminal for Indian index futures & options (NIFTY, BANKNIFTY, SENSEX). It combines a local FastAPI engine (real-time FYERS market data, signal scanning, paper trading, ML/forecast research) with a static Next.js frontend deployed to Firebase Hosting.

```
┌──────────────────────────────┐        ┌───────────────────────────────────────────────┐
│  Frontend (Next.js static)   │        │  Backend (FastAPI, 127.0.0.1:8000)            │
│  https://fo-droid.web.app    │◄──────►│  Central feed · Signal worker · Swing worker  │
│  Firebase Hosting            │  HTTP  │  Telegram stack · Forecast/Flow schedulers    │
└──────────────────────────────┘        │  Paper engine · AI copilot · ML research      │
                                        └───────────┬───────────────────────┬───────────┘
                                                    │                       │
                                          ┌─────────▼─────────┐   ┌─────────▼─────────┐
                                          │ FYERS API v3 +    │   │ Supabase          │
                                          │ HSM v1-5 socket   │   │ Auth + PostgreSQL │
                                          └───────────────────┘   └───────────────────┘
```

## Core Principles

- **Truth of Wall (no fabrication):** a gating CI scan (`backend/tests/test_no_fabrication_signatures.py`) rejects fabricated-data signatures — hardcoded spots, synthetic fallback prices, ungated mock AI, hardcoded IV maps. A corrupted feed degrades or rejects ticks; it never invents data or trades.
- **FYERS-only market data:** `MARKET_DATA_PROVIDER=fyers` is enforced at startup; legacy demo values are normalized, anything else fails loud.
- **Local-first backend:** the API binds to loopback. The browser talks to the deployed frontend, which calls `http://127.0.0.1:8000` on the same machine. Closing a browser never stops backend services.
- **Auth posture:** Supabase JWT auth. When `AUTH_REQUIRED=false`, an anonymous dev-admin bypass applies **only to loopback Host requests** — never through the Cloudflare tunnel or in production.

## Repository Layout

```
Droid/
├── backend/                  FastAPI engine (Python ≥3.12)
│   ├── app/
│   │   ├── api/              REST + WebSocket routers (markets, options, signals, algo, …)
│   │   ├── ai/               AI providers (OpenRouter, OpenAI, Gemini, NVIDIA, Ollama) + validators
│   │   ├── algo/             Algo trading: risk, execution, position sizing, reconciliation
│   │   ├── core/             Settings, logging, DB, service lifecycle, broker runtime
│   │   ├── event_engine/     Economic/market event intelligence and scheduling
│   │   ├── fno/              F&O universe and instrument logic
│   │   ├── institutional/    Institutional flow ingest and drift detection
│   │   ├── instruments/      Instrument master / symbol resolution
│   │   ├── market_data/      Central feed, tick handling, staleness and sanity guards
│   │   ├── ml/               ML models, features, calibration, training, registry
│   │   ├── models/           Pydantic domain models (market, signals, …)
│   │   ├── multi_timeframe/  Multi-timeframe analysis
│   │   ├── providers/        Broker providers (FYERS REST + HSM WebSocket)
│   │   ├── quant/            Pricing, Greeks, quant primitives
│   │   ├── repositories/     Persistence layer
│   │   ├── research/         Forecast research: predictions, settlement, shadow, scheduler
│   │   ├── services/         Central feed, write pipeline, snapshots, SLO, paper, OpenRouter catalog
│   │   ├── signals/          Signal engine: scanner, FSM, risk, paper, outcomes, audit, SSE/Telegram
│   │   ├── swing/            Swing trading EOD scan + intraday monitor
│   │   └── technical_analysis/ Indicators and TA primitives
│   ├── scripts/              Training, validation, backfill, promotion scripts
│   ├── tests/                Pytest suite (including the no-fabrication gate)
│   ├── Dockerfile            Container image for Cloud Run deployment
│   ├── run_migrations.py     Applies database/migrations/*.sql to Supabase
│   └── .env.example          Backend environment template
├── frontend/                 Next.js 16 static export (React 19, Tailwind 4, Radix UI)
│   ├── src/app/              Routes: /, /signals, /swing, /options, /trade, /intel,
│   │                         /lab, /copilot, /ops, /settings, /login
│   ├── src/components/       Module UI (dashboard, signals, swing, options, trade, intel,
│   │                         lab, copilot, ops, settings, shell, ui)
│   ├── src/hooks/            Data hooks (market stream, desks, execution guard, …)
│   ├── src/context/          App stream / instrument / market session contexts
│   ├── src/lib/              API clients, settings, symbols, chart + desk helpers
│   ├── scripts/              check-design-rules.mjs (design gate)
│   └── apphosting.yaml       Firebase App Hosting config
├── database/migrations/      Versioned SQL schema (15 migrations)
├── .github/workflows/        CI + Supabase keep-alive
├── Start-Backend.cmd         One-click backend launcher
├── Deploy-Frontend.cmd       Build + deploy static export to Firebase
├── Start-Mobile-Tunnel.cmd   Cloudflare quick tunnel + rebuild/redeploy for phone access
└── firebase.json             Hosting config (project: fo-droid)
```

## Frontend Modules

| Route        | Desk                       | Purpose                                                                 |
|--------------|----------------------------|-------------------------------------------------------------------------|
| `/`          | Dashboard / Command Centre| System health, feed circuits, regime, ML bias, forecast and signal ribbon |
| `/signals`   | Signals & Ledger           | Scanner grid, signal lifecycle, execution ledger, outcomes             |
| `/swing`     | Swing Desk                 | EOD swing scans and intraday swing positions                           |
| `/options`   | Options & Strategy         | Option chain analytics, strategy builder, options intelligence          |
| `/trade`     | Trade Ops                  | Paper/live trade operations, health panel, risk controls                |
| `/intel`     | Intel                      | FII/DII flows, institutional overlays, event intelligence               |
| `/lab`       | Research Lab               | ML models, forecasts, walk-forward validation, experiments              |
| `/copilot`   | AI Copilot                 | AI chat/analysis over live market context                               |
| `/ops`       | Ops Console                | Observability, SLO metrics, subsystem health                            |
| `/settings`  | Settings                   | Broker/AI/Telegram configuration (stored in Supabase + local storage)   |
| `/login`     | Auth                       | Supabase authentication                                                 |

The UI is a design-gated system: `scripts/check-design-rules.mjs` fails the build if raw Tailwind palette classes, hex colors, `dark:` variants, or inline color styles are reintroduced.

## Prerequisites

- Windows (launcher scripts are PowerShell), Python **3.12+**, Node.js (pinned **20.18.0** via `.node-version`; CI uses 22)
- A **FYERS** trading account with API app credentials (App ID `XXXXX-100`, secret, redirect URI)
- A **Supabase** project (Auth + PostgreSQL) — used for auth and persistence
- **Firebase CLI** (`npm i -g firebase-tools`) logged in to the `fo-droid` project
- Optional: **cloudflared** for mobile access, **Ollama** for local AI models

## Setup

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,ml]"     # the ml extra is required: app/quant + app/ml import
                               # numpy, polars, scipy and scikit-learn. `.[dev]` alone
                               # cannot import those packages at all.

Copy-Item .env.example .env     # then fill in the values
python run_migrations.py        # apply database/migrations/*.sql to Supabase
```

Key variables in `backend/.env`:

| Variable | Purpose |
|----------|---------|
| `APP_MODE`, `APP_ENV` | `development` / `production` |
| `AUTH_REQUIRED` | Set `true` in production; dev bypass is loopback-only |
| `SUPABASE_URL` | Supabase project URL (required for ES256/JWKS token verification) |
| `SUPABASE_JWT_SECRET` | Legacy HS256 secret (only for old projects) |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/postgres` |
| `MARKET_DATA_PROVIDER`, `API_TYPE` | Fixed to `fyers` / `indian` |
| `FYERS_APP_ID`, `FYERS_SECRET_KEY`, `FYERS_REDIRECT_URI`, `FYERS_ACCESS_TOKEN` | FYERS OAuth credentials |
| `FYERS_WS_ENABLED`, `FYERS_WS_URL` | HSM v1-5 tick socket (REST poller is the fallback) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_WEBHOOK_SECRET`, `BACKEND_PUBLIC_URL` | Telegram alerts (webhook requires an HTTPS tunnel) |
| `OPENROUTER_API_KEY`, `OPENROUTER_FREE_ONLY`, `OPENROUTER_DEFAULT_MODEL` | OpenRouter AI (or configure via Settings UI); direct provider keys and Ollama settings also supported |
| `REDIS_URL` | Optional cache; in-memory used when empty |

### 2. Frontend

```powershell
cd frontend
npm ci
```

Create `frontend/.env.local`:

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_URL` | Backend base URL (default dev: `http://127.0.0.1:8000`) |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL (auth) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key (auth) |
| `NEXT_PUBLIC_MINIMAL_UI` | `1` for the consolidated shell |

## Running

| Action | Command |
|--------|---------|
| Start everything (1-click) | Double-click `Start-Backend.cmd` — starts uvicorn, waits for `/health/subsystems`, then opens https://fo-droid.web.app |
| Start backend manually | `backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` (from `backend/`) |
| API docs | http://127.0.0.1:8000/docs |
| Frontend local dev | `npm run dev` in `frontend/` (optional; production is the static Firebase site) |
| Deploy frontend | Double-click `Deploy-Frontend.cmd` — builds static export with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` and runs `firebase deploy --only hosting --project fo-droid` |
| Mobile access | Double-click `Start-Mobile-Tunnel.cmd` — exposes the backend via a Cloudflare quick tunnel, rebuilds the export with that URL, redeploys. Quick-tunnel URLs change on restart, so re-run after reboot. Broker OAuth still callbacks to `127.0.0.1`, so do FYERS login on the PC. |

Backend startup brings up (once per process): central market feed, FYERS stream with retry, Telegram stack, morning briefing (08:50 IST), automated signal worker (3s risk / 10s scalp / 30s intraday), swing worker, forecast + institutional-flow schedulers, event engine, and signal/paper persistence hydration. Graceful shutdown runs on process teardown only.

## Testing & CI

```powershell
# Backend (from backend/, with the ml extra installed — see Setup above)
python -m pytest tests -q                                     # 1613 passed
python -m pytest tests/test_no_fabrication_signatures.py -q   # gating truth-of-wall scan

# Frontend (from frontend/)
npm run check        # typecheck && design gate && vitest
npm run lint         # eslint
```

CI (`.github/workflows/ci.yml`):

- **Frontend [gating]:** `npm run check` (typecheck + design gate + tests)
- **Backend [gating]:** `pip install -e ".[dev,ml]"` then `pytest tests -q` (1613 passed)
- **No-fabrication gate [gating]:** stdlib-only scan for fabricated-data signatures

`supabase-keepalive.yml` pings Supabase every 3 days to prevent free-tier pause.

## Database

Versioned SQL migrations live in `database/migrations/` (initial schema, instruments/expiries, alerts/paper/ML/AI, paper hardening, user settings, pattern outcomes, algo trading, HPI historical intelligence, warehouse, event engine phases 1–2, research laboratory, ML horizons/ATR settle, snapshot forecast indexes, institutional flow). Apply with:

```powershell
cd backend
python run_migrations.py
```

## ML & Research Tooling

`backend/scripts/` includes:

- **Training:** `train_direction.py`, `train_regime.py`, `train_breakout.py`, `train_trade_outcome.py`
- **Validation:** `validate_forecast_1h.py`, `validate_institutional_1h.py`, `shadow_compare.py`, `promote_challenger.py`
- **Data:** `build_ml_dataset.py`, `backfill_research_settlement.py`, `backfill_flow_daily.py`, `ingest_fii_dii_history.py`, `daily_ml_settlement.py`
- **Auth:** `verify_auth_token.py`

The research layer (`backend/app/research/`) runs hourly 1H-forecast evidence collection (shadow + settlement) behind `FORECAST_SCHEDULER_ENABLED=on`; institutional flow ingest runs behind `FLOW_SCHEDULER_ENABLED=on`.

## Risk Configuration

`backend/config/risk_envelopes.json` defines per-instrument risk envelopes (`1m_scalp`, `5m_intraday`) with min/max risk points, T1/T2 ceilings, ATR multipliers, minimum R:R, trigger TTL, and time stops for NIFTY / BANKNIFTY / SENSEX, plus lot sizes and options scaling. `backend/config/event_scoring.json` and `backend/config/event_sources.json` configure the event intelligence engine, and `backend/config/scoring_weights.json` pins the ARMED threshold.

`backend/config/` is the single source of truth and is shipped into the container by `backend/Dockerfile`. Do not add a second copy at the repo root: the loader searches `<backend>/config` first, so a duplicate would silently change the effective limits in exactly one of the two run modes.

## Deployment

- **Frontend:** static export (`output: "export"`) served by Firebase Hosting (`fo-droid`), SPA rewrite to `index.html`, no-cache HTML with immutable `_next/static` assets.
- **Backend (optional):** `backend/Dockerfile` (Python 3.12-slim, `.[ml]` deps, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`) for Cloud Run-style hosting.

## Troubleshooting

- **Port 8000 busy:** `start-backend-local.ps1` auto-recycles the process holding the port.
- **FYERS auth expired:** the backend refuses to synthesize candles and logs `AUTH_EXPIRED` — re-authenticate via the app (OAuth callback must reach `http://127.0.0.1:8000/api/v1/tokens/fyers/callback`).
- **No database:** persistence-dependent features (research backfill, shadow compare, signals restore) degrade gracefully or abort with a clear "DATABASE_URL missing" message.
- **Mobile shows offline data:** re-run `Start-Mobile-Tunnel.cmd` after any reboot or tunnel restart.
- **Telegram webhook silent:** `BACKEND_PUBLIC_URL` must be a public HTTPS URL (localhost alone cannot receive webhooks).

## Security Notes

- Never commit `backend/.env`, `frontend/.env.local`, tokens (`*.fyers_token`), or runtime state (`*_state.json`) — they are git-ignored by design.
- Set `AUTH_REQUIRED=true` before exposing the API beyond loopback; the dev bypass only serves loopback hosts, and production always enforces auth.
- CORS is restricted to exact Firebase origins plus fixed dev-server ports — no wildcard loopback ports or prefix-matched Firebase domains.
