# Cycle-1 Smoke Notes — 1H Forecast v2.3 (dry-run only)

Date (UTC): 2026-09-11 · Repo: E:\Droid · Tree: dirty (no reset performed)
Rules observed: no --commit, no DB writes, --dry-run only, 120s max per script, no synthetic training data, no invented candles. No commit made.

## 1. Backfill dry-run
Command: `python backend/scripts/backfill_research_settlement.py --dry-run --limit 20`
Exit: 1
Tail:
```
backfill failed: Database is not configured (DATABASE_URL missing) — aborting backfill.
```
Verdict: expected-offline. DB unavailable, nothing planned/written. No fabrication.

## 2. Validate 1H (smoke)
Requested command: `python backend/scripts/validate_forecast_1h.py --instrument "NIFTY 50" --folds 2 --warmup 20 --stride 5 --out backend/artifacts/cycle1_smoke.md+json`
Exit: 1
Tail:
```
--folds must be >= 5
```
Note: folds=2 rejected by design (budget requires folds ≥ 5; script enforces). Never reached MarketService. No report written.

Compliant probe (read-only, still dry): same but `--folds 5`
Exit: 2
Tail:
```
validate_forecast_1h failed: Insufficient 1h candle data for 'NIFTY 50': broker history returned 0 candles (available: none). Re-auth FYERS if the daily token expired, then retry. No synthetic data was generated.
+ provider logs: fyers AUTH_EXPIRED ('Token expired and no refresh callback registered')
```
Path executed: live MarketService path attempted → broker/creds failure (0 candles, FYERS token expired). Script correctly refused to synthesize. No `cycle1_smoke.md/json` written.

Synthetic-free unit fallback (no candles, no DB, pure math):
Command: `python -m pytest backend/tests/test_p1_power_calib_costs.py backend/tests/test_shadow.py -q`
Exit: 0 — 22 passed in 0.12s
Extra check: `required_n(0.38, 0.05) = 749` via `app.research.validation.power` — matches `FORECAST_1H_CYCLE1_BUDGET.md §4`.

## 3. Shadow compare
Command: `python backend/scripts/shadow_compare.py --help`
Exit: 0 (usage shown; min-settleable default 250, max-days default 14, OR-gate documented)
Dry attempt: `python backend/scripts/shadow_compare.py --min-settleable 5`
Exit: 2
Tail:
```
shadow_compare failed: Database is not configured (DATABASE_URL missing) — refusing to synthesize shadow data. Run inside the backend env with Postgres.
```
Gate behavior: `--min-settleable 5` lowers the n-bar, but gate warning (`INSUFFICIENT EVIDENCE ... EXTEND SHADOW`) only renders when DB is present and `n_pair < min AND days < max`. With no DB, CLI exits before gate — expected-offline, no empty-DB gate demo possible.

## Artifacts written
- `backend/artifacts/cycle1_smoke_notes.md` (this file) — only new artifact.
- `backend/artifacts/cycle1_smoke.md/json` — NOT written (validate never reached report stage).
- No DB writes; backfill/shadow aborted on missing DATABASE_URL.

## Data-availability verdict: BLOCKED for live Cycle-1
- History/creds: BLOCKED — FYERS AUTH_EXPIRED, 0× 1h candles for "NIFTY 50". Need re-auth + history window (warmup+folds+1 bars min), then rerun with `--folds ≥ 5 --stride 1` per budget.
- Research DB: BLOCKED — DATABASE_URL missing. Need Postgres with `research_predictions` + `research_prediction_outcomes` (+ snapshots) before backfill/shadow can show settleable counts or gate SUFFICIENT/INSUFFICIENT.
- Harness logic: PASS offline — 22 pure unit tests green; power MDE 749 confirmed.
- Can Cycle-1 proceed live? NO — blocked on history/creds + DB. Next: re-auth FYERS, configure DATABASE_URL in backend env, ingest 90d research preds, then rerun dry-runs.
