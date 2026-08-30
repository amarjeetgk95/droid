# Database Documentation — Supabase PostgreSQL Architecture

## Overview

The Droid platform uses **PostgreSQL** (via **Supabase**) as its unified, persistent data layer. The database stores:
- User Profiles & Preferences (`profiles`, `user_settings`)
- User Watchlists & Items (`watchlists`, `watchlist_items`)
- Market Metadata (`instruments`, `expiries`)
- Quantitative Alert Rules & History (`alert_rules`, `alert_history`)
- Virtual Paper Trading Engine (`paper_portfolios`, `paper_orders`, `paper_positions`)
- ML Predictions & Feature Vectors (`ml_predictions`)
- AI Market Intelligence Reports (`ai_reports`)

**Important:** High-frequency raw tick feeds and real-time streaming buffers are processed in memory and micro-batched.

## Architecture

```
User Next.js Frontend (Supabase Auth / SSR)
        │ (Bearer JWT)
        ▼
   FastAPI Backend
        │ (Async SQLAlchemy ORM / asyncpg)
   Service Layer (Alert, Paper, ML, AI, Watchlist)
        │
   Repository Layer (app.repositories.*)
        │
        ▼
   Supabase PostgreSQL (Row-Level Security)
```

## Public Tables Summary

| Table | Purpose | Row-Level Security (RLS) |
|---|---|---|
| `profiles` | User identity & display names | Users read/update own profile |
| `user_settings` | Per-user application preferences & theme | Users CRUD own settings |
| `watchlists` | User-created watchlists | Users CRUD own watchlists |
| `watchlist_items` | Instruments saved within watchlists | Access restricted by parent watchlist ownership |
| `instruments` | Exchange instruments reference metadata | Public read-only |
| `expiries` | F&O contract expiry schedules | Public read-only |
| `alert_rules` | User-configured quantitative alerts | Users CRUD own alert rules |
| `alert_history` | Audit log of triggered alert events | Users read own alert history |
| `paper_portfolios` | Virtual trading capital and margin usage | Users CRUD own portfolio |
| `paper_orders` | Virtual order execution book | Users CRUD own orders |
| `paper_positions` | Active and closed virtual positions | Users CRUD own positions |
| `ml_predictions` | Probabilistic ensemble prediction history | Public read-only / Service writes |
| `ai_reports` | Structured LLM market intelligence reports | Public read-only / Service writes |

## Migrations

Migrations are stored in `database/migrations/` and executed sequentially:
1. `001_initial_schema.sql`: Core profiles, settings, watchlists, instruments, and expiries.
2. `002_seed_instruments_expiries.sql`: Demo NSE/BSE index instruments and expiries.
3. `003_alerts_paper_ml_ai_schema.sql`: Alert rules, alert history, paper trading portfolios/orders/positions, ML predictions, and AI reports.

### Applying Migrations

To apply all migrations to Supabase:
```powershell
cd backend
python run_migrations.py
```
