# 1H Forecast v2.3 — Detailed Implementation Plan (MVIG-first)

Status: `approved for build` · Baseline: `forecast-v1` in `backend/app/research/trend_forecast.py` · Target: `forecast-v2 / MVIG`
Companion specs: v2.2 (full standard), v2.3 lean spec (this plan implements v2.3), `docs/FORECAST_1H_FRAMEWORK_AND_ROADMAP.md`.

Principle: `TRUTH > MEASUREMENT > SIMPLICITY > ROBUSTNESS > COMPLEXITY`. Ship smallest system that proves 60m edge. FULL-tier items are explicitly deferred.

---

## 0. Scope lock

### 0.1 In scope (MVIG ship blockers)

PIT + leakage, snapshot/audit, data-quality + settleability + late-session gates, single primary target `v2-atr-em-session (0.25xATR14_1h)`, 12–15 feature logistic + XGB/LGB challenger, single global calibrator, walk-forward + purge/embargo + power + reference cost model, abstention, target/risk v2, shadow 250, monitoring-minimal, rollback, API `1h-v2` + frontend honesty.

### 0.2 Out of scope until FULL

BH-FDR/DSR formal promotion, crypto-holdout governance, full event-calendar automation, options friction replay, advanced PSI matrix, 35–45 feature expansion, complex stacking, per-cell calibrators.

### 0.3 Product invariants (do not change in this plan)

- Product horizon stays `60m`. `30m` is diagnostic only (`HORIZON_CONFIG` in `trend_forecast.py:49` unchanged in meaning).
- `forecast-v1` weights `0.30/0.30/0.25/0.10/0.05` (`trend_forecast.py:38`) retained as baseline comparator + fallback + shadow benchmark. New code paths use `forecast_version: 1h-v2`, `weights_version`, `target_spec_version`, `model_version`, `calibrator_version`.
- No autonomous trading / position sizing.

---

## 1. Baseline inventory (what exists today)

| Layer | File | Current behavior | v2.3 action |
|---|---|---|---|
| Orchestrator | `backend/app/research/trend_forecast.py:113-573` | 7-TF concurrent fetch (12s TF timeout), 1m-resample fallback, 5 indicators on 1h, ML 60m, heuristic options score, fixed weights, ±20 direction, 1.8/1.1 ATR targets, `record_prediction` | Add gates + prob contract + snapshot + EM targets alongside v1 path (flag) |
| Features | `backend/app/research/features.py:27-323` | `classify_session_ist`, VWAP, `determine_market_regime`, per-TF quant/momentum/volume + MTF vote | Add `minutes_to_close`, expose v2 feature extractor; no logic break |
| Indicators | `backend/app/research/indicators/*.py`, `registry.py`, `models.py:62` | `IndicatorOutput(score±100, confidence0-1)` | Unchanged; add OOS attribution only |
| ML inference | `backend/app/ml/predictor.py:26` | 10-feat vector, XGB/LGB or heuristic fallback, `calibrated` flag | Add v2 12–15 feat path + logistic + artifact validation; keep v1 fallback labeled |
| ML features | `backend/app/ml/feature_extractor.py:19` | 10 normalized features; `term_structure=None` so `futures_basis_pct=0` | Fix basis plumbing or drop feature (decision §3.1); add v2 extractor |
| Targets | `backend/app/ml/targets.py:24-72` | `v1-atr-band`, 0.25 ATR, horizons 5–120 | Freeze new `v2-atr-em-session` module; keep v1 for compat |
| Settlement | `backend/app/ml/sessions.py:40`, `settlement.py:58` | `classify_window` same-session rule, `plan_row`, `settle_due` for `ml_predictions` | Reuse for research preds; add cron + backfill script |
| Calibration | `backend/app/ml/calibration.py:15` | `settle_prediction` + hit-rate summary | Add Brier/log-loss/ECE + single global isotonic/temperature fitter |
| Persistence | `backend/app/research/predictions.py:30`, `models.py:88-126` | Immutable `research_predictions`, append-only outcomes, in-mem fallback; `ResearchSnapshot` model exists but not written on forecast path | Write snapshot every persist; add `limitations[]`, version fields |
| API | `backend/app/api/research.py:182` | `GET /forecast/{horizon}?instrument&record`, 503 on data gap | Add v2 response fields (probabilities, settleable, versions, limitations); contract validation |
| Frontend | `frontend/src/components/research/ForecastCard.tsx`, `app/(app)/page.tsx` | Score/confidence/targets/layers/WhyPanel, 60s poll | Add prob bars, MVIG/DEGRADED/ABSTAIN states, settleability + reason |
| Validation | `backend/app/research/validation/*`, `outcome_measurer.py` | Cheap gate, Wilson CI, naive baseline | Add walk-forward + purge/embargo + power + cost + calibration report runner |

---

## 2. P0 — Honesty & auditability (3–5 eng days; realistic 5–8 with review)

Goal: every persisted forecast is truthful about quality and reconstructable. No model change.

### P0-1. Probability + version contract (backend)

Files: `backend/app/research/trend_forecast.py:440-474,538-563`, `backend/app/signals/explain.py` (forecast explain), `backend/app/api/research.py:182-206`.

Tasks:
1. Define `ForecastV2Meta` dict keys (no breaking change to v1 keys): `forecast_version="1h-v2"`, `status: RESEARCH|MVIG|DEGRADED|ABSTAIN`, `probabilities{bullish,neutral,bearish}`, `confidence=max(P)`, `raw_confidence` (pre-calibration, v1 path maps score→softmax or holds raw until P1 calibrator lands; label `uncalibrated`), `regime`, `session`, `settleable: bool`, `settle_reason: str|null`, `data_quality: HEALTHY|DEGRADED|HEURISTIC|UNSETTLEABLE`, `model_source`, `calibrated: bool`, `model_version`, `calibrator_version` (`none-v0` in P0), `weights_version="forecast-v1"`, `target_spec_version` (still `v1-atr-band` in P0; `v2-atr-em-session` lands in P1), `prediction_id`, `snapshot_id`, `limitations: str[]`.
2. Map v1 `score±100` to interim `probabilities` via documented placeholder (e.g. temperature softmax with `T=40`, clearly flagged `calibrated=false`) so frontend contract is stable before real calibrator.
3. Contract validator `validate_forecast_v2(d)` raises on `sum(P)!=1±1e-6`, `P∉[0,1]`, missing snapshot when `record=true`, version mismatch.

Tests: unit `test_forecast_v2_contract.py` (valid, bad-prob, missing-snapshot cases).
Accept: `GET /forecast/1h` returns new keys; old keys intact; invalid payload never emitted.

### P0-2. Data-quality + settleability + late-session gates

Files: `trend_forecast.py:120-177,476-502`, `research/options_context.py:28-58`, `ml/sessions.py:40`, `research/features.py:27`.

Tasks:
1. Compute in `forecast()`: `missing_tfs` (TF fetch returned `[]`), `resampled_tfs` (already logged), `ml_available` (`ml_forecast is not None`), `options_state` (`available`, `data_quality`), `session` (from primary 1h last-candle ts via `classify_session_ist`), `settle = classify_window(symbol, now_utc, 60)`.
2. Apply CORE gate table (§17 v2.3): missing-1h → BLOCK (existing 503); `missing≥2` or `resampled 1h` → `DEGRADED`; `ml None` → confidence cap 0.55 + limitation; stale F&O (`available=False` or `DEGRADED`) → `DEGRADED`; `settleable=false` (covers ~post-14:30 + holidays + specials) → downgrade: cap confidence 0.45, force `NEUTRAL/ABSTAIN` if raw direction was weak (`|score|<35`), add limitation `crosses-session-close — excluded from accuracy`.
3. Propagate to `explain.data_health` + `limitations[]` + log fields.

Tests: mocked `MarketService` (healthy / missing-1h / missing-2TF / resampled), mocked F&O degraded, frozen clock at 10:30 vs 15:00 IST (settleable true/false).
Accept: QA matrix shows correct badges; unsettleable never shows "High conviction".

### P0-3. Snapshot on every persist

Files: `research/models.py:88`, `research/predictions.py:30`, `api/research.py` snapshots section, `trend_forecast.py:538`.

Tasks:
1. Build `ResearchSnapshot{snapshot_id, instrument, timeframe=1h, timestamp, price, regime, session, features: mtf_features (trimmed), options_context, data_quality, created_at}` inside `forecast()` and persist via existing snapshot path (DB + memory); set `prediction.snapshot_id`; include `snapshot_id` in response.
2. If snapshot write fails → `record=false` behavior + `status=DEGRADED` + limitation `snapshot-unavailable`; never persist prediction without snapshot (INVALID per §7).
3. Migration (if needed): ensure `research_snapshots` table + index `(instrument, timestamp)`; `research_predictions.snapshot_id` nullable FK.

Tests: round-trip `record → get_prediction → get_snapshot`; failure-injection test.
Accept: 100% of new `trend_forecast_1h*` rows have non-null `snapshot_id`.

### P0-4. Artifact/spec validation + rollback flag

Files: `ml/trainer.py` (`load_ensemble`, `artifact_paths`), `ml/targets.py`, `trend_forecast.py:275-300`.

Tasks:
1. On `get_ml_forecast`: verify `meta.horizon_minutes==60`, `meta.target_spec_version==expected`, `feature_names` length matches caller; else `ml_forecast=None` + `calibrated=false` + limitation `artifact-mismatch-h60`.
2. Add env flag `FORECAST_WEIGHTS_VERSION=v1` (only v1 in P0) + `FORECAST_ALLOW_HEURISTIC=true` surfaced as `model_source=heuristic_ensemble` in UI. Rollback = flip flag + redeploy; document bundle (code + artifact hashes).
3. Frontend P0: render `status` badge (`RESEARCH` until MVIG), `DATA` (HEALTHY/DEGRADED), `SETTLEMENT YES/NO + reason`, `Model MVIG? No — Research`, `limitations[]` list. No prob-bar redesign yet (P3).

Accept: artifact mismatch demo shows capped DEGRADED, not silent heuristic.

P0 exit: §31 MVIG rows PIT/leakage/data-quality/settleability/snapshot/artifact/late-session/rollback = PASS by code + tests (empirical rows pending P1).

---

## 3. P1 — Measurement (1–2 weeks)

Goal: credible OOS evidence pipeline. No production model switch.

### P1-1. Freeze `v2-atr-em-session` target + session settlement reuse

Files: new `backend/app/ml/targets_v2.py` (or extend `targets.py` with `TARGET_SPEC_VERSION_V2="v2-atr-em-session"`), `ml/sessions.py`, `ml/settlement.py`, `research/outcome_measurer.py`.

Tasks:
1. Implement `label_forward_return_v2(spot_t, spot_th, atr14_1h_t)`: identical math to v1 primary (`0.25×ATR14_1h`, §4) but version string `v2-atr-em-session` + `describe_target` noting EM is risk-only (not label). Keep ATR14_1h source = primary 1h `quant.atr_14`; raise on non-positive (INSUFFICIENT_DATA).
2. Reuse `classify_window` + `resolve_forward_spot` (1m closes) for both ML and research settlement. Document late cutoff derived from calendar (not hardcoded clock).
3. Research auto-settler: new `backend/app/research/settlement.py` mirroring `ml/settlement.settle_due` but reading `research_predictions` (filter `indicator_id like trend_forecast_%`, `outcome missing`), resolving via 1m candles, labeling with v2 spec, appending to `research_prediction_outcomes`. Injectable fetchers + calendar for unit tests.
4. Backfill script `backend/scripts/backfill_research_settlement.py --indicator trend_forecast_1h --since 90d --limit N` (dry-run + commit modes).

Tests: boundary labels (±band, zero/NaN ATR), cross-close skip, holiday skip, forward-spot picker.
Accept: backfill settles only same-session windows; overnight never bridged.

### P1-2. Walk-forward + purge/embargo harness

Files: extend `backend/app/research/validation/backtest_engine.py:37`, new `backend/scripts/validate_forecast_1h.py`, `research/validation/statistical_evaluator.py`.

Tasks:
1. Runner inputs: 1h candles (≥ `warmup 100` + folds), 1m candles for settlement, options snapshots if available (else `available=False` path), instrument list. Params: `stride=1`, `folds≥5 chronological`, `purge=H (60m of 1h bars = 1 bar + 1m buffer)`, `embargo=1 trading day` between train/test (configurable, logged).
2. Per-fold + pooled + per-instrument/regime/session/direction outputs: `n, hit-rate + Wilson95, baseline (naive momentum + buy/hold), excess, Brier, log-loss, ECE(10 bins) + reliability table + confidence-bucket hit-rate, MFE/MAE, target/stop-hit, time-to-target, turnover`.
3. Baselines share identical settlement + costs (no peeking).
4. CI: `pytest backend/tests/test_walkforward_1h.py` with synthetic fixtures asserting no-shuffle, purge respected, session filter applied.

Accept: one-command report `validate_forecast_1h.py --instrument "NIFTY 50" --folds 5` emits markdown + JSON with all tables.

### P1-3. Power analysis (pooled)

Files: new `backend/app/research/validation/power.py`, wired into report.

Tasks:
1. `required_n(baseline_rate, mde, alpha=0.05, power=0.8)` two-sided proportion test. Pre-register MDE for MVIG cycle 1: e.g. `baseline 0.38 → MDE +0.05 absolute after costs` (record exact numbers in experiment record; do not tune post-hoc).
2. Report shows `required_n vs actual pooled n`; per-cell `n + Wilson CI + SUFFICIENT/INSUFFICIENT/CONTRADICTORY` (cells never block unless contradictory/unsafe).

Accept: promotion decision cites power result explicitly.

### P1-4. Calibration metrics (pre-model)

Files: extend `ml/calibration.py:29`, new `ml/calibration_metrics.py`.

Tasks:
1. `brier_score, log_loss_3class, ece_equal_width(Pmax, y, bins=10), reliability_table, calibration_slope_intercept` (1-vs-rest logistic). All pure + unit-tested.
2. Run on v1 interim probabilities (P0 softmax) to establish baseline ECE/Brier — expected: overconfident in RANGING/CLOSING. This justifies P2 calibrator.

Accept: baseline calibration table in P1 report.

### P1-5. Reference cost model + experiment budget

Files: new `backend/app/research/validation/costs.py`, `docs` experiment record template.

Tasks:
1. Implement `REFERENCE_COSTS_V1 = {spread_bps: 2.0 (per side? document), brokerage_flat, statutory_pct, slippage_bps configurable}` + sensitivity `{base, 1.5x, 2x}`. Mapping: §15 v2.3 (spot signal → futures mid entry at next available mid after T, exit mid at T+60m). Version assumptions (`costs_version` in report + snapshot).
2. Pre-register Cycle-1 family (§14): `1 target × 2 models (logistic, XGB/LGB challenger) × 1 calib (global) × 2 thresholds`. Log `experiment_id, hypothesis, window` before running. Sweeps outside budget = exploratory only.

Accept: P1 report includes gross/net/turnover (+Sharpe/DD/profit-factor only if n sufficient) under all 3 cost assumptions.

P1 exit: credible OOS evidence exists (or fails → invoke kill criterion, stay on v1).

---

## 4. P2 — Model (1–2 weeks)

Goal: smallest candidate that can beat v1 OOS with calibration.

### P2-1. Basis plumbing decision (30 min, blocks feature list)

File: `ml/predictor.py:50-66`, `ml/feature_extractor.py:51`, `services/options_service.py`, `fno/context.py`.

Options: (a) plumb `term_structure` through (preferred if available same-session with timestamps), or (b) drop `futures_basis` from v2 set and document. Do not ship a constant-zero "feature".
Accept: decision logged; feature schema reflects it.

### P2-2. v2 feature set (12–15) + schema versioning

Files: new `backend/app/ml/feature_extractor_v2.py` (`FEATURE_SCHEMA_V2="f12-v1"`), `research/features.py` (expose `minutes_to_close`, `atr_pct_1h`, `ret_5/15`, `rel_volume`, `vwap_distance`).

Candidate list (§8 v2.3): `rsi_1h, adx_1h, supertrend_1h/15m/4h (as ±1 + agreement count), bb_pct_b_1h, atr_pct_1h, ret_5, ret_15, relative_volume, vwap_distance, pcr_oi, futures_basis (or replacement), vix, minutes_to_close`. Exact list frozen in `FEATURE_SCHEMA_V2` + `feature_names` in artifact meta. Each addition needs OOS ΔBrier evidence (P1 harness) — no drive-by features.

PIT rules: all inputs timestamped `available_time<=T`; VIX/F&O staleness → feature null + `data_quality` downgrade (impute neutral + flag, never forward-fill silently).
Tests: PIT unit (future VIX rejected), missing-data, schema-hash.

### P2-3. Models: logistic primary, XGB/LGB challenger

Files: new `backend/app/ml/model_v2.py`, `trainer` extension for h60, `artifacts/*h60*`.

Tasks:
1. `L2 multinomial logistic` on standardized v2 features (class_weight balanced if needed). Save `model_h60_logistic.json + meta {model_version, dataset_hash, feature_schema, target_spec, training_time, n, git_sha}`.
2. Challenger `XGB + LGB` on same rows/splits (reuse `trainer.train_ensemble` pattern, horizon 60). No stacking in MVIG.
3. Strict no-fallback: missing `h60` artifact → `model_source=unavailable`, confidence cap (P0-2), never silent remap to h15/h30. `load_ensemble` fallback path must be bypassed for v2 (explicit flag).
4. Model registry entry (minimal for MVIG): `model_version, dataset_hash, feature_schema, target_spec, calibrator_version, git_sha, validation_report_id, decision`. FULL registry hardening later.

Accept: both candidates reproducible from `{dataset_hash, schema, spec, sha}`.

### P2-4. Single global calibrator

Files: new `backend/app/ml/calibrators.py` (`CalibratorV1: temperature scaling primary, isotonic challenger`), `ml/predictor.py` integration.

Tasks:
1. Fit **only on OOS preds** (walk-forward out-of-fold). One calibrator per `(instrument, H=60)` where support allows; no regime×session split in MVIG.
2. Persist `calibrator_h60_{instrument}.json {method, params, fit_n, fit_window, ECE_before/after, version}`. Inference: `P_cal = calibrate(P_raw)`; `confidence=max(P_cal)`; expose both `confidence` + `raw_confidence`.
3. Gate: `ECE<0.08` target; `>0.12` on rolling 200 → degrade (P3 wiring).

Tests: probability simplex, monotone-ish sanity, ECE improvement on held fold.
Accept: reliability curve + bucket table in report.

### P2-5. Abstention + target/risk v2

Files: `trend_forecast.py:415-438` (branch `forecast_version`), new `research/risk_v2.py`.

Tasks:
1. Thresholds (pre-registered, 2 candidates max, e.g. `maxP≥0.55` base / `0.60` conservative; higher in VOLATILE/CLOSING/event-advisory). Else `NEUTRAL/ABSTAIN` with reason. Threshold is part of experiment budget, not tuned post-hoc.
2. Targets: `tgt_dist=min(1.8·ATR14_1h, 0.70·EM)`, `inv_dist=max(1.1·ATR14_1h, 0.35·EM, barrier)`; `EM = atm_iv/100·spot·sqrt(dte_years)` with guards (DTE≤0/clamp, IV missing → ATR-only + limitation `target_basis=ATR-only`); closing scaling `×(time_to_close/H)`; NEUTRAL returns `expected_range{lower,mid,upper}` (EM-based) not nulls.
3. Keep v1 `1.8/1.1 ATR` path behind flag for A/B + shadow.

Tests: EM edge cases (expiry-day, missing IV), abstention matrix, range sanity.
Accept: all directional outputs have EM-aware or explicitly ATR-only targets.

P2 exit: candidate shows `pooled excess>0 AND Brier≤baseline AND ECE acceptable AND net ref ≥ ~0 AND no catastrophic fold` (§19) on fresh OOS (not tuning folds).

---

## 5. P3 — Shadow, monitoring, SLO, frontend (1 week eng + calendar-bound shadow)

### P3-1. Shadow deployment

Files: `api/research.py`, scheduler/worker, `ForecastOutcomes` data source.

Tasks:
1. Dual-run `v1` + `v2-candidate` on same triggers (`record=true`, distinct `indicator_id`: `trend_forecast_1h` vs `trend_forecast_1h_v2`). Minimum `2 weeks OR 250 settleable` (whichever stronger evidence).
2. Compare: hit-rate, Brier, ECE, log-loss, reliability, DQ failure rate, latency. Economics diagnostic only.
3. Promotion requires pre-registered win rules (from P1 MDE + §18).

Accept: shadow report + signed promotion/reject decision.

### P3-2. Minimal monitoring + auto-degrade + rollback

Files: new `backend/app/research/monitoring.py`, cron, `api/research.py` health, runbook in docs.

Metrics (rolling 200 settleable): `hit-rate, Brier, ECE, freshness (candle/F&O age), missing-TF rate, ml availability`. Triggers: `ECE>0.12`, material Brier/hit deterioration vs shadow baseline, stale provider, artifact/spec mismatch → `status=DEGRADED` + confidence cap + alert + promotion lock; persistent → rollback to last approved bundle (code + model + calibrator + schema + spec + weights). Rollback drill in staging.
Accept: chaos tests (stale F&O, missing TF, mismatch) all degrade correctly.

### P3-3. SLO + caching + idempotency

Target `p95<8s, hard 12s` (existing TF timeout). Add caches: `MTF 30s / options 60s / ML 15s` per instrument (key includes minute bucket); idempotency `instrument+H+minute_bucket` (replay returns same `prediction_id` within bucket). Load test: 10 users × poll 60s + manual refresh burst.
Accept: p95 measured + logged; timeout paths return 503, never synthetic.

### P3-4. Frontend honesty (v2 contract)

Files: `ForecastCard.tsx:17-39,63-69,127-293`, `WhyPanel`, `ForecastOutcomes.tsx`, `lib/api/intelligence.ts` (add `getForecast` v2 typing).

Tasks:
1. Type `HourForecastV2` with probabilities, `status`, `settleable+reason`, `data_quality`, versions, `expected_range`, `limitations[]`.
2. UI: prob bars `BULL/NEUT/BEAR%`, `Confidence` (=max P) + `Calibration` chip (`LIVE ECE x.xx n=NNN` or `UNCALIBRATED`), `MODEL: RESEARCH/MVIG`, `DATA: HEALTHY/DEGRADED`, `SETTLEMENT: YES/NO + reason`, target/invalidation + expected-range for NEUTRAL, `ABSTAIN — INSUFFICIENT EVIDENCE` and `DEGRADED — reason` states visually distinct from healthy high-confidence. Never equate degraded/high-confidence styling.
3. `ForecastOutcomes` filter: settleable-only toggle + costs note.

Accept: UX review with 6 states (healthy directional, abstain, degraded, unsettleable late-session, ML-missing, snapshot-fail).

---

## 6. Test strategy (per phase)

- Unit: target boundaries, session/holiday/special rules, forward-spot picker, resample invariants, prob simplex, calibrator math, cost math, PIT joins, leakage injections (future candle/options/regime/norm/universe must fail CI).
- Integration: healthy/degraded/missing-TF/resampled/stale-options/missing-ML/late-session/expiry/artifact-mismatch matrix via mocked `MarketService` + F&O.
- Offline: `validate_forecast_1h.py` + power + calibration + cost sensitivity (base/1.5x/2x).
- Shadow + rollback drill + SLO load test.

---

## 7. Work breakdown (checklist order)

P0: [ ] contract types + validator [ ] gates (quality/settle/late) [ ] snapshot write + migration [ ] artifact validation + flags [ ] frontend status badges [ ] QA matrix + merge.
P1: [ ] targets_v2 + research settler + backfill [ ] walk-forward runner [ ] power module [ ] calibration metrics [ ] costs + budget registration [ ] P1 report (30m diagnostic + 60m baseline).
P2: [ ] basis decision [ ] extractor_v2 + schema [ ] logistic + challenger h60 [ ] global calibrator [ ] abstention + risk v2 [ ] Cycle-1 OOS report.
P3: [ ] shadow harness [ ] monitoring + degrade + rollback [ ] caches/SLO [ ] frontend v2 [ ] promotion packet (experiment record §37 v2.2: date/id/versions/hashes/samples/Brier/ECE/hit-CI/returns/costs/decision).

Two-cycle kill: if Cycle-1 + Cycle-2 (fresh OOS each) fail §19 MVIG rule → stop escalation, remain on `forecast-v1` (or best validated simple candidate). Log decision.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| 60m has no edge after costs | Abstention + kill criterion; 30m diagnostic first; success = honest ABSTAIN system, not forced direction |
| Sample starvation (4/day) | Pooled power, single calibrator, small family, 250-shadow (not 500), multi-month calendar expectation set with stakeholders |
| F&O staleness kills options value | DEGRADED path + options-as-info-layer rule; materiality threshold pre-registered |
| Basis always zero | P2-1 decision gate; blocks feature freeze |
| Scope creep to FULL | Tier labels enforced in code review; FULL items tagged `FULL-deferred` in registry/API/frontend |

---

## 9. Definition of done

MVIG production when §31-MVIG rows PASS with evidence: PIT, leakage, data-quality, settleability, calibrated prob, walk-forward+purge, power, cost model, abstention, snapshot, artifact governance, late-session, rollback — plus shadow + monitoring live. `INSTITUTIONAL GRADE` label stays locked until FULL gates pass.
