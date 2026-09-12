# 1H Forecast — Promotion Packet (DRAFT, pre-Cycle-1)

Status: `DRAFT — engineering complete, empirical evidence pending` · Date: 2026-09-11
Baseline: `forecast-v1` · Candidate: `forecast-v2 / MVIG track` · Target spec: `v2-atr-em-session`

## 1. Decision

**Do NOT promote.** Engineering gates PASS; empirical gates BLOCKED (no live history/DB). System stays `RESEARCH`, never labeled Institutional Grade. Fallback remains `forecast-v1`.

Blocked on:
- FYERS re-auth (`FYERS_ACCESS_TOKEN` empty in `backend/.env`; provider `OFFLINE/Awaiting authentication`). NSE candles return 0; correctly refused synthesis.
- Supabase DB reachable after `load_dotenv` fix, but `research_*` tables empty (0 due rows) — no live forecasts recorded yet.
- Calendar-bound shadow: 2 weeks OR 250 settleable (requires live run after unblock).

Unblocked this round (2026-09-11):
- Scripts now `load_dotenv(BACKEND_ROOT/.env)` (`backfill`, `validate`, `shadow_compare`) — DB connects.
- Fixed `research/settlement.py` `AmbiguousParameterError` (`CAST(:since AS timestamptz)`); backfill `--dry-run --limit 5` now returns `would_settle: 0, errors: 0` live against Supabase.
- Crypto plumbing smoke (NON-PROMOTION, NOT NSE evidence): 400 live BTCUSDT 1h klines via public Binance → `WalkForwardGate` pooled_n=30, hit 53.33, Brier 0.6133, purge_ok, unsettleable=0. Artifact: `backend/artifacts/walkforward_BTCUSDT_smoke.json`. Proves fetch→features→settlement→metrics loop real-data end to end; NSE evidence still requires FYERS.

## 2. Engineering evidence (PASS)

| Gate | Evidence |
|---|---|
| PIT/leakage | `PITStore.as_of_join` + `leakage_gate` enforced in training paths; v2 features carry `available_time`; leakage-injection CI tests pass |
| Contract | `validate_forecast_v2` (simplex, versions, snapshot-required); `test_forecast_v2_contract` 16 pass |
| Targets/settlement | `targets_v2`, `research/settlement` + backfill dry-run (refuses without DB); 16 tests pass |
| Walk-forward harness | `WalkForwardGate` (5 folds, purge+embargo, session-aware, Brier/ECE/costs); 5 tests pass |
| Power/calib/costs | `required_n(0.38,0.05)=749`; Brier/log-loss/ECE pure; `ref-v1` costs; 11 tests pass |
| Features/models | `f12-v1` 15 feats (basis dropped, documented); logistic + strict h60 loader + registry; 21+16 tests pass (1 sklearn skip) |
| Calibrator/risk | Temperature `cal-v1` (OOS-gated), EM targets, abstention 0.55/0.60; 19 tests pass |
| Shadow/monitor/SLO | Dual-run + compare CLI, rolling-200 monitor + degrade, runbook, TTL caches + idempotency; 11+13+10 tests pass |
| Frontend | RESEARCH/MVIG/DEGRADED/ABSTAIN badges, prob bars, calibration chip, settleability, limitations; `tsc` clean, 10 vitest pass |
| Regression | 138 passed / 1 skip across P0–P3 suites; monitoring router wired (`/api/v1/monitoring/forecast-health|config`) |

## 3. Empirical evidence (TODO — Cycle-1)

Per `docs/FORECAST_1H_CYCLE1_BUDGET.md` (1 target × 2 models × 1 global calib × 2 thresholds):

- [ ] 30m diagnostic walk-forward report (pipeline/labels/calib sanity)
- [ ] 60m production walk-forward (pooled + per-fold/instrument/regime/session, power vs 749, Brier/ECE vs baseline, costs base/1.5x/2x)
- [ ] Calibration reliability table + bucket hit-rates
- [ ] Ablation (drop-one-layer ΔBrier)
- [ ] Shadow 2w/250 + compare report
- [ ] MVIG decision per §19 (excess>0, Brier≤base, ECE ok, net ref ≥~0, no catastrophic fold, PIT clean)

## 4. Release bundle (to pin at promotion)

- Code: `FORECAST_WEIGHTS_VERSION`, `FORECAST_V2_MODEL`, `FORECAST_ABSTAIN_T`, `FORECAST_CACHE`, `FORECAST_ALLOW_HEURISTIC` (record live values)
- Artifacts: `model_h60_logistic.json` + meta (dataset_hash, f12-v1, v2-atr-em-session, git_sha) — NOT YET TRAINED (no history)
- Calibrator: `calibrator_h60_*.json cal-v1` — NOT YET FIT (needs OOS preds)
- Registry: `artifacts/registry.jsonl` entry — TODO at training
- Snapshots: every persisted forecast has `snapshot_id` (P0-3 wired; verify in prod DB)

## 5. Next actions

1. Re-auth FYERS, confirm 1h (≥300 bars) + 1m (≥90d) history for NIFTY/BANKNIFTY/SENSEX.
2. Run migrations incl. `014_research_snapshot_forecast_v2_index` (DB reachable; tables exist via 011).
3. Set `FORECAST_SCHEDULER_ENABLED=on` after re-auth — hourly shadow + settlement then accumulate automatically (market-closed ticks no-op; default off so dev/CI never writes). Manual alternative: `backfill --commit`, cron `shadow_scheduler.run_hourly_shadow_sync`.
4. Run `validate_forecast_1h.py` 30m then 60m; fill Cycle-1 budget tables.
5. Train logistic-v2 + challenger on same-session rows; fit global calibrator OOS; record registry.
6. Monitor via `/api/v1/monitoring/forecast-health`; decide per §19 or invoke 2-cycle kill (stay on v1).

## 6. Follow-up wiring (2026-09-12, uncommitted)

- `app/research/scheduler.py`: hourly loop (next :05 IST, `FORECAST_SCHEDULER_ENABLED` default off), `run_once` = shadow + settlement, never raises. Wired into `main.py` lifespan start/stop (guarded). Tests: `tests/test_forecast_scheduler.py` (5 pass).
- Full P0–P3 + scheduler regression: 143 passed / 1 skip.
