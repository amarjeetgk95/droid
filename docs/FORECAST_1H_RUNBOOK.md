# 1H Forecast v2.3 — Monitoring & Rollback Runbook (P3-2)

Companion: `docs/FORECAST_1H_V23_IMPLEMENTATION_PLAN.md` §P3-2.
Code: `backend/app/research/monitoring.py`, `backend/app/api/monitoring.py`
(router NOT registered in `backend/app/main.py` — enable with
`app.include_router(monitoring.router)`), gates in
`backend/app/research/trend_forecast.py` (`forecast()` P0-2 section).

Live signals:

- `GET /api/v1/monitoring/forecast-health?limit=200` →
  `{status: healthy|degraded|unknown, degraded, reasons[], metrics, thresholds}`.
  Fail-open: DB trouble returns `status=unknown` (HTTP 200), never 500.
- `GET /api/v1/monitoring/forecast-config` → current release bundle
  (code flags, model/calibrator artifacts, feature schema, target spec).

Rolling metrics (last 200 settleable, unsettleable/unsettled rows excluded, never
guessed): `n, hit_rate, brier, ece, freshness{candle/fno age max+median},
missing_tf_rate, ml_availability` (+ `resampled_tf_rate`,
`artifact_mismatch_count/rate`).

Degrade triggers (`check_degrade`, reasons non-empty IFF degraded):

| Trigger | Default | Source |
|---|---|---|
| `ECE > 0.12` | `ece_max: 0.12` | P2-4 gate on rolling 200 |
| Brier worse than baseline `+ 0.02` | `brier_slack: 0.02` | vs shadow/v1 baseline (offline report) |
| Hit-rate drop vs baseline | `hit_drop: 0.05` | vs shadow/v1 baseline (offline report) |
| Stale provider | candle `>300s`, F&O `>600s` | freshness max age |
| Artifact/spec mismatch | any row | `artifact-mismatch*` limitation / spec drift |
| Missing-TF rate high | `>0.20` | rows with `missing_timeframes` |
| ML availability low | `<0.80` | rows with `ml_available=false` |

---

## 1. Chaos matrix → expected badge / cap

Per-forecast gates live in `trend_forecast.py::forecast` (P0-2). Confidence only
ever caps DOWN; degraded styling must never equal healthy high-conviction.

| # | Chaos (how to inject) | Expected `status` / `data_quality` | Expected cap + `limitations[]` | Monitoring signal |
|---|---|---|---|---|
| C1 | Stale F&O: `ResearchOptionsContext.get_context` → `available=False` (or `data_quality=DEGRADED/STALE`) | `DEGRADED` (from `RESEARCH`), DQ `DEGRADED` | no cap; `options-unavailable-degraded` / `options-degraded:<DQ>` | rolling `ml_availability` unaffected; per-forecast DQ visible in snapshot `v2` block |
| C2 | Missing TFs: ≥2 timeframes return `[]`, no 1m to resample from | `DEGRADED`, DQ `DEGRADED` (`ABSTAIN` stays `ABSTAIN`) | no cap; `missing-timeframes:[...]` | `missing_tf_rate` rises → degrade past `0.20` |
| C3 | Resampled primary: only `1m` present, `1h` rebuilt locally | `DEGRADED` | no cap; `resampled-1h-from-1m` | `resampled_tf_rate` rises → degrade past `0.20` |
| C4 | Artifact/spec mismatch: ensemble claims `model_source=xgboost_lightgbm_ensemble` with no matching h60 triple (or `meta.horizon_minutes/target_spec/feature-width` drift) | ML layer dropped → confidence path as C6 | `artifact-mismatch-h60:*` + `ml-unavailable-confidence-capped-0.55`, conf ≤ 0.55 | `artifact_mismatch_count > 0` → immediate `degraded` |
| C5 | Late-session / unsettleable: frozen clock post-~14:30 IST, holiday/special (`classify_window` unsettleable) | weak `\|score\|<35` → `ABSTAIN` + forced `NEUTRAL` (targets nulled); else `DEGRADED`; DQ `UNSETTLEABLE` | cap 0.45; `crosses-session-close — excluded from accuracy (<reason>)` (+ `late-session-forced-neutral` when abstained) | these rows are excluded from accuracy (`settleable=false` filtered out of the rolling window) |
| C6 | ML unavailable (`get_ml_forecast → None`) or `FORECAST_ALLOW_HEURISTIC=false` with heuristic source | unchanged status, `model_source=unavailable` | cap 0.55; `ml-unavailable-confidence-capped-0.55` / `heuristic-disabled-by-FORECAST_ALLOW_HEURISTIC` | `ml_availability` falls → degrade below `0.80` |
| C7 | Snapshot write fails | `DEGRADED`, NO prediction persisted (`prediction_id=None`) | `snapshot-unavailable` | `forecast-health` shows thinning `n` → `unknown` if nothing settleable |
| C8 | Rolling-200 `ECE > 0.12`, or Brier/hit regression vs shadow baseline | monitoring `degraded=true` (`ece-*-above-0.12`, `brier-*-worse-than-baseline*`, `hit-rate-*-below-baseline*`) | operator action: confidence handling per §2 + promotion lock; persistent → §3 rollback | `forecast-health.reasons[]` |

Accept: every chaos above was demonstrated (mocked `MarketService` + F&O +
`classify_window`, cf. `backend/tests/test_forecast_v2_contract.py`) and the
monitoring unit matrix passes (`backend/tests/test_monitoring.py`).

---

## 2. On-call response (auto-degrade)

1. `forecast-health` → `degraded=true`: read `reasons[]`.
   - `ece-*` / `brier-*` / `hit-rate-*` → calibration/performance regression:
     keep serving (per-forecast caps already apply), open incident, freeze
     promotion (see §4), compare against the shadow report before any change.
   - `stale-candle-*` / `stale-fno-*` → provider incident: re-auth broker
     (FYERS daily token), check F&O feed; forecasts already self-downgrade
     (C1); no manual cap needed.
   - `artifact-spec-mismatch-count-*` → artifact incident: do NOT force-serve
     ML (P0-4 refuses silent fallback); verify artifact triple + spec (§3).
   - `missing-tf-rate-*` / `resampled-tf-rate-*` / `ml-availability-*` →
     data-quality incident: check history API / ML service; per-forecast
     gates (C2/C3/C6) already cap and label.
2. `status=unknown` → health probe itself failed (DB down) or zero settled
   rows (`warming-up-no-settled-rows` note): check database connectivity
   (`/api/v1/health/database`), then the research settler cron/backfill
   (`backend/app/research/settlement.py`).
3. Persistent degrade (multiple rolling windows, or any `CONTRADICTORY`
   shadow cell) → §3 rollback. Rollback drill must already have passed in
   staging.

---

## 3. Rollback steps (plan-only helper)

`resolve_release_bundle()` snapshots the §26 bundle
(code `FORECAST_WEIGHTS_VERSION`/`FORECAST_V2_MODEL` + model artifact meta +
calibrator version + feature schema `f12-v1` + target spec
`v2-atr-em-session`); `rollback_to(bundle)` returns the application plan —
it never mutates live env and never writes files:

1. Promotion stays LOCKED (plan sets `promotion_locked=true`; unlock needs a
   green rolling-200 + signed decision — §4).
2. Redeploy the prior code bundle: `FORECAST_WEIGHTS_VERSION=<raw>`
   (`forecast-<raw>`), `FORECAST_V2_MODEL=<v1|logistic-v2>` — rollback is
   flip-env + redeploy.
3. Restore the prior artifact triple (`xgb/lgb/meta _h60` paths in
   `artifacts_to_restore`) + persisted calibrator; verify
   `meta.horizon_minutes==60`, `meta.target_spec_version`, and
   `len(meta.feature_names)==caller width` — never silently remap h15.
4. Verify feature schema (`f12-v1`) and target spec (`v2-atr-em-session`);
   on mismatch the P0-4 guard serves `ml_forecast=None` + capped confidence.
5. Heuristic kill-switch without artifact redeploy:
   `FORECAST_ALLOW_HEURISTIC=false` (heuristic-free capped output).
6. Staging rollback drill → green rolling-200 (`ECE<=0.12`, no Brier/hit
   regression) → signed promotion/reject decision → unlock.

---

## 4. Promotion lock note

Any monitoring `degraded=true`, any `CONTRADICTORY` shadow cell, or any open
rollback plan LOCKS MVIG promotion. Unlock requires ALL of: green rolling-200
window, shadow win rules met (pre-registered MDE from the P1 power analysis),
and a signed promotion packet (experiment record: date/id, versions/hashes,
samples, Brier/ECE, hit-CI, returns, costs, decision). Two failed OOS cycles →
kill escalation, remain on `forecast-v1` (implementation plan §7).
