# Forecast 1H v2.3 — Cycle-1 Experiment Budget (pre-registered)

Status: `pre-registered` · Costs: `ref-v1` · Power defaults: `BASELINE_RATE=0.38, MDE_ABSOLUTE=0.05, ALPHA=0.05, POWER=0.8`
Plan refs: P1-3 (`power.py`), P1-4 (`calibration_metrics.py`), P1-5 (`costs.py`), promotion §19.

> Rule: sweeps outside this family are exploratory only and cannot promote.
> Do not tune MDE / thresholds / family post-hoc. Failures invoke the
> two-cycle kill rule (stay on `forecast-v1`).

## 1. Pre-registered family (8 cells max)

| Dim | Values | Count |
|---|---|---|
| Target | `v2-atr-em-session` (0.25×ATR14_1h, EM risk-only) | 1 |
| Models | `logistic` (primary) vs `XGB/LGB challenger` | 2 |
| Calibrator | single global (temperature primary, isotonic challenger diagnostic) | 1 |
| Thresholds | `maxP ≥ 0.55` (base) / `maxP ≥ 0.60` (conservative) | 2 |

Total: 1 × 2 × 1 × 2 = 4 candidate configs (+ v1 shadow benchmark, not counted).

## 2. Hypothesis

H1: pooled 60m hit-rate of the v2 candidate exceeds the identical-settlement
naive baseline by ≥ +0.05 absolute after `ref-v1` costs, with
`Brier ≤ v1-softmax baseline`, `ECE < 0.08`, and no catastrophic fold.
H0: no such excess (promotion blocked, see §5).

## 3. Window / data

- Walk-forward: `folds ≥ 5` chronological, `stride=1`, `purge=60m (1×1h bar + 1m buffer)`, `embargo=1 trading day` (configurable, logged).
- Settlement: same-session only via `classify_window` + 1m-close forward spot; overnight never bridged.
- Universe: NSE index futures proxy per §15 mapping (spot signal → next futures mid after T, exit mid T+60m).

## 4. MDE / power

- `required_n(baseline 0.38, MDE +0.05, α=0.05 two-sided, power=0.8) = 749 pooled settleable`
  (one-sample proportion z-test, normal approx; see `power.py` docstring).
- Report shows `required_n vs actual pooled n`; per-cell `n + Wilson95 +
  SUFFICIENT / INSUFFICIENT / CONTRADICTORY` (cells never block unless
  contradictory/unsafe).

## 5. Promotion rule (reference, not restated)

Pooled excess > 0 AND Brier ≤ baseline AND ECE acceptable AND net ref ≥ ~0
AND no catastrophic fold, on fresh OOS (not tuning folds), with power cited
explicitly. Full gate list: plan §19 + §31-MVIG rows. BH-FDR/DSR deferred to FULL.

## 6. Cost assumptions (`costs_version=ref-v1`)

`spread_bps=2.0/side, slippage_bps=1.0/side, statutory_pct=0.001/side (blended
assumption), brokerage_flat=0`. Sensitivity `{base, 1.5x, 2x}` in every report.
Mapping: §15 v2.3. No broker calls.

## 7. Results (P2 fills — TODO)

### 7.1 Model × threshold pooled (TODO)

| Model | Thr | n / req_n | Hit-rate + Wilson95 | Baseline | Excess | p | Brier | Log-loss | ECE | Gross | Net(base/1.5x/2x) | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| logistic | 0.55 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |
| logistic | 0.60 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |
| xgb/lgb | 0.55 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |
| xgb/lgb | 0.60 | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO | TODO |

### 7.2 Calibration baseline v1-softmax (P1 report fills — TODO)

| Split | n | Brier | Log-loss | ECE(10) | Slope (bull/neut/bear) | Note |
|---|---|---|---|---|---|---|
| pooled | TODO | TODO | TODO | TODO | TODO | expected overconfident RANGING/CLOSING |
| per-fold | TODO | TODO | TODO | TODO | TODO | — |

### 7.3 Decision (TODO)

- Decision: TODO (PROMOTE / REJECT / EXTEND-SHADOW)
- Evidence packet: TODO (report id, dataset hash, git sha, artifact hashes)
- Sign-off: TODO

## 8. P2-1/P2-2 decision record — basis choice + frozen v2 feature list

Date: 2026-09-11 · Schema: `FEATURE_SCHEMA_V2="f12-v1"` (`backend/app/ml/feature_extractor_v2.py`)

### 8.1 Basis decision (P2-1): DROP `futures_basis`, replace with `max_pain_distance`

- Decision: **DROP** (plan option b). Do not ship a constant-zero feature.
- Reason: no PIT-safe market futures basis exists in-repo —
  `backend/app/api/futures.py` returns `curve_state="UNAVAILABLE"` with
  `contracts=[]` / `basis_pts=None` (refuses to fabricate); `fno/context.py`
  hardcodes `near_basis=0` with **no timestamp** (PIT unprovable);
  `options_service.futures_price` is a synthetic cost-of-carry estimate
  (`spot*exp(r*t)`), not a market quote; `ml/predictor.py:50-66` passes
  `term_structure=None` so v1 `futures_basis_pct` is constant-zero on every call.
- Re-entry rule: only via `check_basis_availability()` returning `(True, reason)`
  for a timestamped market-quoted basis with `available_time <= T`, plus a schema
  bump (`f12-v2`) and OOS ΔBrier evidence from the P1 harness.
- The v1 10-feature path (`feature_extractor.py` / `predictor.py`) is untouched
  (legacy heuristic fallback, labeled as such).

### 8.2 Frozen v2 feature list (15 columns, 12–15 allowed)

Supertrend enters as three per-TF ±1 votes; cross-TF agreement stays a derived
helper (`supertrend_agreement()`, deterministic function of the three votes —
not stored to avoid redundancy/collinearity; available for P2-5 abstention).
Scaling is fixed fit-free min-max/neutral-centered (P2-3 logistic fits its
z-scaler on train folds, persisted in artifact meta). Missing → `None` +
missing-mask flag; `model_vector` uses the documented neutral only where
`imputed[name]` is true (never silent).

| # | Feature | Source | PIT note | Scale / clip | Missing → |
|---|---|---|---|---|---|
| 1 | `rsi_1h` | primary 1h `quant.rsi_14` | candles ≤ T | `(rsi-50)/50`, [-1,1] | None → 0.0 + flag |
| 2 | `adx_1h` | primary 1h `quant.adx` | candles ≤ T | `adx/50`, [0,1] | None → 0.0 + flag |
| 3 | `supertrend_1h` | 1h `supertrend_dir` @ last close | close ≤ T | ±1 | None → 0.0 + flag |
| 4 | `supertrend_15m` | 15m `supertrend_dir` @ last close | close ≤ T | ±1 | None → 0.0 + flag |
| 5 | `supertrend_4h` | 4h `supertrend_dir` @ last close | close ≤ T | ±1 | None → 0.0 + flag |
| 6 | `bb_pct_b_1h` | primary 1h `quant.bb_pct_b` | candles ≤ T | passthrough, [-0.5,1.5] | None → 0.5 + flag |
| 7 | `atr_pct_1h` | 1h `atr_14` / last close | both ≤ T | percent, [0,5] | None → 0.5 + flag |
| 8 | `ret_5` | 1h closes last vs 5 back | both ≤ T | percent, [-5,5] | None → 0.0 + flag |
| 9 | `ret_15` | 1h closes last vs 15 back | both ≤ T | percent, [-5,5] | None → 0.0 + flag |
| 10 | `relative_volume` | 1h current/avg20 volume | bars ≤ T | ratio, [0,5] | None → 1.0 + flag |
| 11 | `vwap_distance` | last close vs session VWAP | bars ≤ T | percent, [-5,5] | None → 0.0 + flag |
| 12 | `pcr_oi` | options snapshot `pcr_oi` | `available_time` ≤ T; stale → null | `(pcr-1)/0.5`, [-1,1] | None → 0.0 + flag |
| 13 | `max_pain_distance` | options snapshot `max_pain` (**basis replacement**) | snapshot ≤ T | percent, [-5,5] | None → 0.0 + flag |
| 14 | `vix` | VIX quote | `available_time` ≤ T; stale → null | level, [5,50] | None → 15.0 + flag |
| 15 | `minutes_to_close` | decision clock → 15:30 IST | not market data, no lookahead | `/375`, [0,1] | None → 0.5 + flag |

Schema hash: `feature_schema_hash_v2()` (sha256 over `f12-v1` + ordered names);
any list/tag change alters the hash and fails `test_features_v2.py`.
New `research/features.py` helpers (additive only): `minutes_to_close_ist`,
`atr_pct_1h`, `period_return_pct` / `ret_5_pct` / `ret_15_pct`,
`relative_volume`, `vwap_distance_pct`.
