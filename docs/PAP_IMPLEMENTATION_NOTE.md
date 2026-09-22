# PAP Implementation Note

**Status:** Phase −1 and Phase 0 implemented; real SENSEX/NIFTY 1m data landed 2026-09-22; Phase 1 not started · **Date:** 2026-09-22 · **Supersedes:** the two external PAP specifications (full-build and staged evidence-first)

**Subject:** Price Action Prediction research programme (Fisher 9 + VWAP + ADX/DMI + Linear Regression Slope + Bollinger Band Width → 3/5/10-minute direction on NIFTY, BANKNIFTY, SENSEX).

---

## 0. Reader summary

The external specs got the *methodology* largely right and the *environment* entirely wrong. They were written for a repository that does not exist. This note replaces their component inventory with the one that does, corrects three material defects, and reduces Phase 1 from a 35-item build to five new files.

Three corrections drive everything below:

| # | Correction | Consequence if ignored |
|---|---|---|
| **C1** | Every research input must pass a **data provenance gate**. The only 1-minute dataset in this repo is a synthetic fixture. | The experiment measures a random-number generator and reports FAIL (or a noise-level PASS) as if it were market truth. |
| **C2** | There is a **canonical component map** for every capability PAP needs. Most of it already exists; four of the candidates are broken or duplicated. | We build a second ML stack, a fifth VWAP, and a fourth purged splitter. |
| **C3** | The **primary pass criterion is economic**, not statistical. Statistics are supporting evidence. | We PASS a system with 89.8% cost drag. This has already happened here once. |

The programme stays shadow-mode-only and offline until Phase 1 returns **PASS**. Nothing in this note authorises execution, sizing, gating, or enrichment changes.

---

## 1. Why this note exists: three findings

### 1.1 Finding 1 — the input data is synthetic (blocking)

`backend/data/raw/sensex/1m.json` is a `DatasetManager` sidecar and states its own provenance:

```json
{ "dataset_id": "ds_sensex_1m_20260919_151352",
  "row_count": 67500,
  "source": "synthetic_fixture",
  "data_quality_score": 100.0,
  "checksum_sha256": "11b8ce16b90ddfb0ecea7645f0969a7ac8ef9c830ccf03030e7eb8ae7949b283" }
```

`backend/data/datasets/SENSEX_1m.parquet` and `backend/data/raw/sensex/1m.parquet` carry identical statistics and match the declared row count. Measured behaviour of both files:

| Signature | Observed | Real 1m index data |
|---|---|---|
| Bars/day | 375 × 180 sessions, **zero gaps** | gaps occur daily |
| `open[t] == close[t-1]` | **99.73%** exact | rare; never to 6 dp |
| `high == max(open, close)` | **0.0000** | common, especially quiet bars |
| `low == min(open, close)` | **0.0000** | common |
| Log-return kurtosis | **0.000** | 5–50 |
| Volume integer-like | 0.13% | ~100% |

Kurtosis of exactly zero across 67,500 bars is a Gaussian generator. On such data the five features *cannot* carry edge — not because they are weak, but because there is no structure to find. The pre-registered test would return FAIL and we would conclude the feature stack is worthless while having learned nothing about the market.

Three aggravating facts:

- `data/quality_score: 100.0`. The existing quality path scores the simulator as perfect.
- `backend/app/quant/research/s6_runner.py:176` loads `data/datasets/{INST}_1m.parquet` and logs `Loaded historical parquet` with **no synthetic check**, while `backend/app/signals/strategies/vortex_snap/backtest/data_loader.py` correctly implements `require_real_data=True` and a DATA-SOURCE CONTRACT docstring. The guard exists in one loader, not the other.
- `backend/scripts/run_session_study.py:45` loads this file directly, so `data/quant_session_study.json` was produced from it.

**The fix is not to write provenance metadata — it already exists and is correct. The fix is to *enforce* it.** See §3.

### 1.2 Finding 2 — duplicate validation frameworks, one of them fail-open

Four purged walk-forward implementations exist:

| Component | Purge | Embargo | Verdict |
|---|---|---|---|
| `app/research/validation/backtest_engine.py:run_walkforward` | yes | yes (`purge_bars + embargo_days*6`) | **canonical** |
| `app/quant/validation/purged_wfo.py:PurgedWalkForwardSplitter` | yes | declared | usable splitter |
| `app/quant/research/s6_wfo.py` | yes | `embargo_days` | S6-local; leave |
| `app/ml/validation/purged_cv.py:PurgedWalkForwardCV` | partial | **never applied** | **broken — do not use** |

In `purged_cv.py`, `embargo_bars` is assigned in `__init__` (line 27) and never referenced again. Worse, when `n_samples < (n_splits+1)*50` (i.e. < 250) it falls through to `split_point = int(n*0.8)` and yields a single split with **no purge and no embargo** — labelled in a comment as "degrade gracefully". That is a silent leakage path with a reassuring comment.

*Correction to earlier review:* my initial statement "the embargo is unused" was true of `purged_cv.py` only. The other three implementations do apply it. The finding that matters is not "embargo is missing repo-wide" but "there are four splitters and the one an ML researcher is most likely to import is the broken one."

### 1.3 Finding 3 — the economics gate is the real gate

`backend/data/experiments/experiment_nifty_report.md`:

> Win Rate **72.9%** · Profit Factor **2.69** · Sharpe **1.70** · Cost Drag **89.8%** · Gross ₹4,270.71 → **Net ₹435.73**

A `Macro-F1 + 0.03` gate passes that system. Any PAP pass criterion that is purely statistical will do the same. Statistical credibility answers "is this real?"; only the cost filter answers "does it matter?". Both are required, and the cost filter is the one that has already bitten this codebase.

### 1.4 Finding 4 — the live-path guard was defeated by file presence

`app/api/vortex.py:58` force-sets `_config.data.require_real_data = True` with the comment:

> the live HUD path must 503 when the 1m parquet is missing instead of silently serving the seed-42 simulation

That guard worked exactly as written, and was defeated anyway. A synthetic series had been persisted to `data/raw/sensex/1m.parquet` — a real-data path — and the loader tested only for *file existence*. So the HUD served generated candles tagged `is_simulated: false` with `note: "Real historical 1m parquet dataset."`, while the guard above it existed precisely to prevent that.

This is the most consequential instance of the fail-open pattern in §2.1, because it is the live path rather than a research path. It is also the strongest argument for enforcing provenance rather than merely recording it: the metadata was correct the whole time and no code read it.

---

## 2. Canonical component map

Rule: **if a row below has an existing component, PAP extends or calls it. It does not create a sibling.** Any deviation requires a written reason in the PR.

| Capability | Canonical component | Action |
|---|---|---|
| ATR / ADX / Bollinger | `app/quant/indicators.py` (`calculate_atr` :53, `calculate_adx` :84, `calculate_bollinger_bands` :158) | reuse |
| Fisher Transform 9 | *none exists* | **add here** |
| Linear Regression Slope | *none exists* | **add here** |
| VWAP (session, causal) | `app/signals/pipeline/data_acquisition.py:calculate_session_vwap` | reuse semantics |
| Labels / targets | `app/ml/targets.py` (`label_forward_return`, `LABEL_MAP`, `NEUTRAL_BAND_ATR`, `SUPPORTED_HORIZONS`) + `app/ml/targets_v2.py` | extend horizons |
| Session / EOD settlement | `app/ml/sessions.py` (`classify_window`, `resolve_forward_spot`) | reuse |
| Purged walk-forward | `app/research/validation/backtest_engine.py:run_walkforward` | reuse |
| Fold splitting | `app/quant/validation/purged_wfo.py:PurgedWalkForwardSplitter` | reuse |
| Sample sufficiency / power | `app/research/validation/power.py` (`required_n`, `cell_status`, `power_report`) | reuse |
| Baselines | `app/research/validation/baseline.py` (`BuyAndHoldBaseline`, `NaiveMomentumBaseline`) | reuse |
| Cost model | `app/research/validation/costs.py` (`apply_costs`, `summarize_costs`, `sensitivity_summary`) | reuse |
| Probability metrics | `app/ml/calibration_metrics.py` (`brier_score_3class`, `log_loss_3class`, `ece_equal_width`) | reuse |
| Calibrators | `app/ml/calibrators.py`, `app/ml/calibration/calibrators.py` | reuse |
| Feature schema / extractor | `app/ml/features/schema.py` (f28-v3), `app/ml/features/feature_extractor_v3.py` | add new version |
| Leakage checks | `app/ml/validation/leakage_checks.py`, `app/ml/leakage_gate.py` | extend |
| Dataset provenance | `app/quant/data/dataset_manager.py` (`DatasetManager`, `DatasetMetadata.source`) | **enforce** |
| Model registry | `app/ml/registry.py` → `artifacts/registry.jsonl` | reuse |
| Drift hooks | `app/ml/monitoring/drift_monitor.py` | reuse (non-blocking) |
| Promotion gates | `app/quant/validation/gate_g1_evaluator.py`, `gate_g2_evaluator.py`, `promotion_gate.py` | leave untouched |
| Reports | `app/research/validation/report.py`, `statistical_evaluator.py` | reuse |

**Explicitly forbidden:** `app/research/features.py:calculate_intraday_vwap`. It returns `candles[-1]["close"]` as VWAP when cumulative volume is zero — silently turning `vwap_distance` into a constant rather than failing. Two VWAPs with different semantics is not a duplicate to dedupe later; it is two different features wearing one name.

### 2.1 The fail-open pattern (root cause)

Findings 1.1, 1.2 and 2 share one shape: **a degraded path that fabricates a plausible value instead of failing.** Unpurged split called "graceful". Last close returned as VWAP. Synthetic session logged as "historical parquet". A 100.0 quality score for a simulator.

Phase 0 therefore adds one invariant, enforced by test:

> **No component on the PAP research path may return a substituted value. Missing, stale, simulated, unsettled or insufficient inputs must raise, or return `None`/`UNAVAILABLE` with a reason code. `NaN` and `0.0` are never acceptable stand-ins.**

---

## 3. Phase −1 — data provenance gate (blocking; do this first)

New file, small: `backend/app/quant/data/provenance_gate.py`

```python
ALLOWED_RESEARCH_SOURCES = {"fyers_api_v3", "nse_bhavcopy", "vendor_export"}
FIXTURE_SOURCES = {"synthetic_fixture", "mock", "test", "seed42"}
```

API: `assert_real_dataset(path) -> DatasetMetadata`, raising `SyntheticDataError` (subclass of `RuntimeError`).

Gate logic, in order:

1. Sidecar `<name>.json` must exist next to the parquet. Absent sidecar → **raise** (`DatasetMetadata` is already written on ingest; absence means the file bypassed ingest).
2. `source ∈ FIXTURE_SOURCES` → raise, quoting the sidecar.
3. `source ∉ ALLOWED_RESEARCH_SOURCES` → raise (unknown provenance is not real provenance).
4. Recompute SHA-256; mismatch against `checksum_sha256` → raise.
5. Row count / min / max timestamp must match the sidecar.
6. Statistical simulation screen — any **two or more** of the following trip:
   - zero missing bars across ≥ 20 consecutive sessions
   - `open[t] == close[t-1]` in > 90% of bars
   - log-return excess kurtosis `< 0.5`
   - `high == max(open, close)` in `< 0.1%` of bars
   - integer-like fraction of volume `< 50%`
7. Emit a `provenance_report` block into the experiment report (source, checksum, screen results) — provenance travels with results.

Call sites to add the gate to (today they do not check): `app/quant/research/s6_runner.py:176`, `scripts/run_session_study.py:45`, and the new PAP runner. `vortex_snap/backtest/data_loader.py` already complies.

### 3.1 Phase −1 data requirements

| Requirement | Status |
|---|---|
| SENSEX 1m, real, ≥ 24 months | **not present** (only the fixture) |
| NIFTY 1m, real | **not present** (`data/raw/nifty/` is empty) |
| BANKNIFTY 1m, real | **absent entirely** |
| A volume source for VWAP | **undetermined** — see H3 |

**History budget.** 375 bars/session. To pool 5 folds × 3 horizons × 3 instruments with ≥ 2,000 decisions per fold-test: ≥ 500 sessions (**≈ 24 months**) per instrument. Below 12 months, the session × regime decomposition is not feasible at all and Phase 1 must run pooled-only with the slice analysis deferred. Count the bars *before* designing the grid, not after.

**Do not delete the synthetic fixtures.** They are valid test inputs. Move them to `backend/tests/fixtures/` and keep them out of `data/datasets/` and `data/raw/`, which are the paths the loaders search.

---

## 4. Phase 0 — validation integrity

Precondition for any PAP result. Small, test-heavy.

1. **Consolidate splitters.** Pick `purged_wfo.PurgedWalkForwardSplitter` as canonical. Fix `ml/validation/purged_cv.py`: apply `embargo_bars`, remove the unpurged fallback (raise `InsufficientDataError` under 250 samples, or delegate to the canonical splitter), and mark it `# DEPRECATED`. Do not leave two live splitters with different leakage behaviour.
2. **Regression tests** (`backend/tests/quant/test_purged_wfo.py` exists and is the right home):
   - a training sample whose `[t, t+h]` label window overlaps the val/test period is removed
   - embargo removes exactly `embargo_bars` after an evaluation block
   - small datasets raise; they never downgrade to an unpurged split
   - horizon-specific purge widths (3, 5, 10 bars) each behave correctly
   - scaler/encoder fit statistics for fold *k* are computed from fold *k*'s training indices only
3. **Causality test** (extends `app/ml/validation/leakage_checks.py`):
   - compute the feature vector at `t`; snapshot; rewrite every candle after `t`; recompute; assert byte-identical
   - the same test at `t`+3m must not move the 5m or 10m vectors
   - horizon isolation: assert by import-graph inspection that `model_3m` cannot reach 5m/10m labels (a test that fails on import is better than a convention)
4. **Timestamp convention (hazard H1).** The SENSEX fixture's bars are **open-anchored** (first 09:15, last 15:29 ⇒ 375 open-labelled bars). If that convention holds for real data, then `close[t]` is not knowable at `t`; a "decision at `t` using `close[t]`" is a one-bar lookahead. Pin the convention explicitly, derive `decision_time` from it, and assert it in a test. This off-by-one invalidates an entire experiment silently and is the single most likely way to produce a spectacular, entirely fake result.
5. `assert_no_lookahead_in_matrix` currently only checks monotonic ordering despite its name. Rename it or make it check causality. Names that overpromise are how leakage survives review.

**Gate:** if Phase 0 cannot demonstrate leakage-free validation on synthetic data with a known injected leak, stop. Do not run Phase 1 on a leaking evaluator.

---

## 5. Phase 1 — the offline experiment

### 5.1 New code, complete list

| File | Purpose |
|---|---|
| `app/quant/indicators.py` | **extend**: `calculate_fisher_transform`, `calculate_linreg_slope` |
| `app/ml/features/pap_schema.py` | new versioned schema `f_pap-v1`, additive; f28-v3 consumers untouched |
| `app/quant/data/provenance_gate.py` | Phase −1 gate |
| `scripts/run_pap_experiment.py` | the runner |
| `config/pap/prereg_v1.json` | pre-registration, frozen before test evaluation |

Five files. Everything else is a call into §2.

### 5.2 Features (`f_pap-v1`)

Only what is new plus what is referenced from existing implementations:

- **Fisher 9** (new): `fisher_value`, `fisher_slope_1`, `fisher_slope_3`, `fisher_acceleration`, `fisher_extreme`, `fisher_reversal`. Role: turning point.
- **VWAP** (canonical semantics): `vwap_distance_atr`, `vwap_slope`, `above_vwap`, `vwap_cross`. Fail-closed when volume is unusable.
- **ADX/DMI** (`calculate_adx`): `adx`, `adx_slope`, `plus_di`, `minus_di`, `di_difference`. Role: trend regime.
- **LR slope 20** (new): `lr_slope_normalized` (= slope / ATR), `lr_slope_change`, `lr_acceleration`, `regression_position`.
- **BB width 20/2.0** (`calculate_bollinger_bands`): `bb_width`, `bb_width_percentile`, `bb_width_change`. Not directional.
- **Context**: `atr`, `session_minute`, `day_of_week`, `instrument`.

Missing-data policy: every feature declares one of `require` (raise), `neutral_with_flag` (value + mask bit), or `drop_sample`. **Silent imputation is prohibited.** A mask column per nullable feature; the missing-rate is reported per instrument per session (this doubles as the first drift signal).

### 5.3 Targets

Extend `SUPPORTED_HORIZONS` (currently `(5, 15, 30, 60, 90, 120)`) to include **3 and 10**. That is a target-spec version bump — record it. Note `INTRADAY_CLEAN_HORIZONS = (5, 15, 30)`; a 10-minute label opened at 15:20 crosses the close and is unsettleable. The existing harness already handles this via `app.ml.sessions.classify_window` / `resolve_forward_spot`: **drop the window and count it, never bridge it.** Report `n_unsettleable` per horizon; expect it to be materially non-zero for 10m.

Labels: sign of forward return with the existing `±NEUTRAL_BAND_ATR (0.25) × ATR14(T) / spot(T)` dead zone, on 1-minute ATR14. `K = 0.25` is the default; it is tunable but **only** on train/validation, never on the test block, and never to balance classes.

Path metrics: MFE, MAE, bars-to-favourable, bars-to-adverse — see hazard H4. Report as OHLC-bounded diagnostics; **excluded from pass criteria**.

### 5.4 Protocol

- Decision grid: every bar satisfying warmup, subject to settlement. Count and report drops.
- 3 isolated pipelines (`model_3m`, `model_5m`, `model_10m`). No cross-horizon features or labels, ever, in Phase 1.
- Models: **Logistic Regression** (multinomial, `class_weight="balanced"`, `StandardScaler` fit on fold-train only) and **LightGBM** multiclass (declared in `pyproject.toml`, and the house choice per `artifacts/lgb_model*.txt`). No deep learning.
- Class imbalance: weighting only. **No SMOTE, no resampling, no duplication.**
- Calibration: Platt/sigmoid per class, fit on validation only. Isotonic only if `n_val > 5000` per class. Never fit on test.
- Baseline comparison via `baseline.py`, plus a **two-condition** rule baseline (e.g. `price > VWAP AND lr_slope > 0`). The six-conjunct version in the external spec has ~1% coverage and is a strawman.

### 5.5 Statistics contract

- **Primary:** balanced accuracy uplift over the class-prior baseline. Secondary: macro-F1, then accuracy.
  *Why:* a majority-class classifier's macro-F1 is a function of class imbalance, so "+0.03" is not comparable across instruments or horizons; balanced accuracy is bounded and comparable.
- **Confidence intervals: day-block bootstrap**, resampling whole trading sessions, ≥ 2,000 resamples, resampling at fold level. **An i.i.d. row bootstrap is prohibited** — with a 10-minute label on 1-minute bars, roughly one independent observation exists per ten rows, and a row bootstrap will understate the interval enough to manufacture the false positive the rest of this protocol exists to prevent.
- **Multiplicity:** declare one primary hypothesis and at most five secondary comparisons *before* touching the test block. Apply Benjamini–Hochberg across the secondary family. White's Reality Check / Hansen SPA is **not** required for Phase 1 — pre-registration plus one primary test is the real protection, and SPA is a week of integration spent on the wrong problem.
- **Sample sufficiency:** use `power.required_n(...)` from `app/research/validation/power.py`; do **not** hard-code 200. Run the power analysis first, then decide whether the grid is affordable. If a cell is under-powered, mark it and exclude it from retention/discard reasoning.
- **Slicing:** Phase 1 reports pooled results, plus per-instrument and per-horizon. Session × regime decomposition is **deferred to Phase 1b** and gated on the power analysis. Requesting 3 × 3 × 5 × 5 cells from 24 months of data produces `INSUFFICIENT_SAMPLE` nearly everywhere and an INCONCLUSIVE verdict by construction — which would be an artefact of the analysis plan, not a fact about the market.

### 5.6 Economic gate

Call `apply_costs` with explicit `spread_bps`, `slippage_bps`, `statutory_pct`, `brokerage_flat`. Require **positive net expectancy at 1.5× the base cost assumption**. Report `sensitivity_summary` across the parameter range.

Index direction is **not** option P&L. Phase 1 asks only whether the index is predictable. Option-level tradability (delta, gamma, theta, IV, contract selection, real marks) is a separate stage using the existing options infrastructure (`contract_resolver.py`, `option_marks.py`, `portfolio_greeks.py`, `expected_move.py`). If the required cost inputs are unavailable, the report says `TRADABILITY NOT EVALUATED` — and **that is not a PASS**.

### 5.7 Report

Reuse `app/research/validation/report.py` + `statistical_evaluator.py`. Required blocks: dataset provenance (§3), config hash, fold table (boundaries, purge, embargo, n_train/val/test, settleable/unsettleable), base rates, class distribution, per-model metrics with CIs, ablation, baselines, calibration, latency, cost sensitivity, and one of **PASS / FAIL / INCONCLUSIVE**.

The report must visually separate **factual results**, **interpretation**, and **exploratory findings**. Exploratory findings never appear in a summary.

---

## 6. Pre-registration (`config/pap/prereg_v1.json`)

Frozen and hashed before the test block is evaluated. Post-hoc edits are recorded as a new version, never as an edit.

```json
{
  "prereg_version": "pap-1.0",
  "instruments": ["NIFTY", "BANKNIFTY", "SENSEX"],
  "horizons_minutes": [3, 5, 10],
  "neutral_band_atr": 0.25,
  "features_schema": "f_pap-v1",
  "folds": 5,
  "purge_bars": {"3m": 3, "5m": 5, "10m": 10},
  "embargo_bars": {"3m": 3, "5m": 5, "10m": 10},
  "primary_metric": "balanced_accuracy_uplift_vs_class_prior",
  "min_effect_abs": 0.02,
  "ci_method": "day_block_bootstrap",
  "bootstrap_resamples": 2000,
  "fold_stability": ">=3_of_5_folds_positive",
  "cost_multiplier": 1.5,
  "min_net_expectancy": 0.0,
  "secondary_family": 5,
  "multiplicity": "benjamini_hochberg_0.05"
}
```

**Verdict rule:**

- **PASS** — all of: (P1) pooled balanced-accuracy uplift ≥ `min_effect_abs` with day-block CI lower bound > 0; (P2) positive in ≥ 3 of 5 folds; (P3) net expectancy > 0 at 1.5× costs; (P4) all leakage/causality/provenance tests green.
- **FAIL** — P1, P2 or P3 missed with adequate power (≥ 80% at the declared effect).
- **INCONCLUSIVE** — inadequate power, low coverage, unresolved validation defect, or missing cost inputs.

`min_effect_abs = 0.02` is a judgment call, not a law. It must be **justified by the power analysis**, not chosen for comfort. If the power analysis says only effects ≥ 0.05 are detectable with available data, that number is the honest one and the shortfall is a data problem, not a threshold problem.

**If FAIL: stop.** Document the null. Do not reinterpret, do not slice harder, do not add oscillators. A null result here is a real finding about the market and the most likely single outcome.

---

## 7. Non-goals for Phase 1

Not built: frontend UI · live shadow service · PAP prediction FSM · Signal Factory or enrichment integration · conflict banner or alerting · drift *service* (hooks only) · latency budget tiers · API surface · execution influence of any kind · P1 candle-anatomy features · ensemble/stacking/SHAP/deep learning.

Also not built: the `price_action_prediction/` 20-file package. If Phase 1 PASSes, Phase 2 is a **5–7 file** specialist component that reuses every row of §2. It is not a parallel application, and it never places orders.

---

## 8. Hazard register

| # | Hazard | Mitigation |
|---|---|---|
| **H1** | Open-labelled bars + `close[t]` at decision `t` = one-bar lookahead | Pin convention; derive `decision_time`; assert in test (§4.4) |
| **H2** | Synthetic fixture on the research path | Provenance gate (§3) |
| **H3** | **VWAP needs volume; indices have none.** If spot volume is 0 or constant, session VWAP is undefined and `price − vwap` degenerates to a rolling mean | Determine the volume source before Phase 1; fail closed; if unusable, VWAP drops out of the stack and the ablation is reported at 4 families, with the reason recorded |
| **H4** | 1-minute OHLC cannot resolve intrabar sequence — MFE/MAE are simultaneously optimistic bounds, time-to-move is quantised to 1 bar | Report as bounded diagnostics; exclude from pass criteria |
| **H5** | Overlapping labels → effective N ≪ row count | Day-block bootstrap; power analysis before slicing |
| **H6** | Index direction ≠ option P&L | Phase 1 stops at the index; option stage gated separately |
| **H7** | Four splitters, one fail-open | One canonical splitter (§4.1) |
| **H8** | Fail-open degradation inventing values | §2.1 invariant, enforced by test |
| **H9** | Multiple testing across instruments/horizons/sessions/regimes/ablations | Pre-registration + BH; session×regime deferred to 1b |
| **H10** | Prior research conclusions (`quant_session_study.json`, `experiment_*.md`) drawn on the fixture | Flag publicly; re-run or withdraw after real data lands |

### Open items requiring a human decision

1. **Where does real 1-minute data come from?** Fyers API pull, an existing vendor export, or elsewhere. Nothing proceeds without this.
2. **What is the volume source for VWAP on an index?** (H3.)
3. **Were the VORTEX-SNAP / session-study reports used to make any real decision?** (H10.)

---

## 9. Execution order

1. Phase −1: provenance gate + test; move fixtures out of research paths; flag H10.
2. Acquire real 1m data (3 instruments + volume source); run the gate; report bars, sessions, coverage, gaps.
3. Phase 0: consolidate splitters, fix `purged_cv.py`, land causality + convention tests.
4. Power analysis → decide the affordable grid.
5. Write and freeze `prereg_v1.json`; record its hash.
6. Build the five files; run Logistic + LightGBM + baselines; pooled, per-instrument, per-horizon.
7. Ablation A→E on the same folds.
8. Show report. Then, and only then, touch the test block.
9. Verdict: PASS → Phase 1b and Phase 2 planning. FAIL → document and stop. INCONCLUSIVE → state which input was inadequate.

Nothing in this sequence enables live execution, and PAP remains advisory-only for the whole of Phase 1 and Phase 2.

---

## 10. Implementation status (2026-09-22)

### Landed: Phase −1

| Artefact | Purpose |
|---|---|
| `app/quant/data/provenance.py` | `assert_real_dataset` (strict), `check_provenance` (soft), `ProvenanceReport`, error taxonomy, checksum/metadata verification, provenance block for reports |
| `app/quant/data/data_firewall.py` | `SimulationScreen` + `DataQualityFirewall.screen_simulation_signals` |
| `tests/quant/test_provenance_gate.py` | 15 tests: screen behaviour, each refusal path, loader enforcement |

Enforcement wired into `app/quant/research/s6_runner.py`, `scripts/run_session_study.py`, and `app/signals/strategies/vortex_snap/backtest/data_loader.py`. `app/api/vortex.py` now maps `ProvenanceError` to HTTP 503.

Both on-disk SENSEX datasets are now refused. Verified independently of the manifest: the screen trips all five signals on both files (180/180 gap-free sessions, excess kurtosis 0.0003, zero-wick fraction 0.0000, integer-volume fraction 0.0013).

### Landed: Phase 0

`app/ml/validation/purged_cv.py` rewritten — embargo applied via an explicit `gap_bars = purge_bars + embargo_bars`, exact label-window purging when `timestamps` and `label_end_times` are supplied, `horizon_bars` cross-check, `for_horizon()` constructor, `describe()` for report metadata, and `InsufficientDataError` instead of the unpurged 80/20 fallback (explicit `allow_single_split=True` retains the small-dataset case, still purged and embargoed). Marked deprecated in favour of `quant/validation/purged_wfo.PurgedWalkForwardSplitter`. Covered by 19 tests in `tests/test_purged_cv_validation.py`.

### Round 2 — root cause, and reconciling prior results

**Root cause of Finding 1 is now established.** `scripts/fetch_fyers_history.py` wrote fixtures and real data through the *same* `DatasetManager` path, differing only by the sidecar's `source` field — which nothing read. Four separate `use_fixture_on_fail` branches (missing credentials, auth failure, per-chunk exception, zero candles) all wrote `source="synthetic_fixture"` into `data/raw`, the directory the loaders search for real history. The fallback was **on by default**. Audit of the live credentials: `FYERS_ACCESS_TOKEN` is empty and the history endpoint returns HTTP 401, so every one of those branches has been reachable.

Fixes applied:

1. Fixture fallback now defaults **off**; `--fixture-fallback` opts in, `--no-fixture-fallback` is retained as a no-op for compatibility.
2. All four branches collapse into one `_persist_fixture` helper that writes to `data/fixtures/`, never `data/raw`, and logs at error level.
3. `instrument_slug()` replaces `"sensex" if "SENSEX" in symbol else "nifty"`, which filed **BANKNIFTY under `nifty`** — a second, independent integrity bug.
4. A successful fetch is verified with `assert_real_dataset` before being reported, so a partial or empty fetch cannot be persisted as history.
5. `s6_runner` historical mode no longer falls back to generated history when no dataset is found; smoke mode is the explicit path for synthetic runs.
6. The existing fixtures were relocated to `data/fixtures/sensex/`, out of `data/raw` and `data/datasets`.

**Screen asymmetry added.** Refusing *real* data is as damaging as accepting generated data, and a continuous index series legitimately trips `open_equals_prior_close` because one minute's close is the next minute's open. Confirming suspicion therefore takes 2 signals, but overriding an admissible broker provenance takes 3 (`STRONG_SIMULATION_SIGNALS`).

**Artifact reconciliation.** `scripts/audit_artifact_provenance.py` resolves every artifact in `app/ml/artifacts` to a dataset and states a verdict; results in `data/experiments/artifact_provenance_audit.{json,md}`.

| Verdict | Count | Notable |
|---|---:|---|
| SYNTHETIC | 2 | `meta.json` (`n_samples: 1669`) and `daily_settlement_report.json` (`total_records_evaluated: 1669`) both resolve to `data/ml_datasets/candidates_v3.parquet`, which is **100% `data_fidelity == 'SYNTHETIC'`** |
| UNVERIFIABLE | 16 | Includes `meta_h60.json` (`n_samples: 120`, no dataset of that size exists), all four `champion/` and `challenger/` model metas, and `env_manifest.json` |
| OK | 0 | — |

The consequential item is the drift report: it evaluated the same 1,669 synthetic records and returned `status: STABLE`, `retrain_recommended: false`, `action_taken: MAINTAIN_CHAMPION`. The monitoring layer certified a simulator as healthy. `promotion_audit.jsonl` then records two promotions of models built this way. None of the artifact metadata records dataset provenance at all — `env_manifest.json` carries `feature_schema_version` and `target_spec_version`, but no dataset identity.

These artifacts are flagged, not deleted or retrained. Retraining requires real data, which requires a valid token.

### Deliberate deviations from this note

1. **The screen lives on `DataQualityFirewall`, not in the gate.** Measuring whether a series looks generated is a data-quality question, and the firewall is where a maintainer looks for "is this data trustworthy". Policy (was it legitimately sourced?) stays in `provenance.py`. Two layers, one axis each.
2. **Refusal-vocabulary is reused, not reinvented.** `FIXTURE_SOURCES` unions `app.signals.quote_quality.SYNTHETIC_PROVIDERS` — the repo's existing canonical set — with the dataset-ingest names. This repo has already paid for four divergent copies of a similar predicate.
3. **`CandleSource` widened.** `is_simulated` was defined as `type == "synthetic"`, which is what let a generated parquet advertise itself as real. It now covers provenance failure, and `provenance_verified` was added. Invariant: `is_simulated == (type == "synthetic" or not provenance_verified)`. Two HUD contract tests asserted the old, false invariant and were updated; they now opt into the fixture explicitly via `VORTEX_SNAP_REQUIRE_REAL_DATA=false`, which is the documented local-dev escape. A new test asserts the strict default 503s on a fixture dataset.

### Real data has landed (2026-09-22, later same day)

The blocker above is resolved for two of three instruments. `data/historical/parquet/` now holds genuine FYERS v3 history ingested by the Historical Data Module:

- **SENSEX 1m** — 92,698 bars, 248 sessions, 2025-09-22 → 2026-09-22 (`candles_v1`, `candles_v2`)
- **NIFTY 1m** — 92,703 bars, same span (`candles_v1`)
- **BANKNIFTY 1m** — directory present, parquet absent (ingestion incomplete)

The simulation screen confirms these independently of the sidecar: excess kurtosis 239 (SENSEX) / 202 (NIFTY) — fat tails no simulator produces — integer volume 100%, `looks_simulated: false`. This unblocks Phase 1 on SENSEX and NIFTY; BANKNIFTY awaits ingestion completion.

**The gate initially refused this real data, and the reason matters.** The HDM sidecar schema (`symbol`/`lineage`/`quality_score`) was unknown to `read_sidecar`, so genuinely real data failed provenance with `sidecar_unreadable`. This is the refusal side of the same fail-open/fail-closed balance the gate was built for: refusing real data is as damaging as accepting generated data. `read_sidecar` now translates the HDM schema explicitly (provider from `lineage.provider_id` + API version; simulator vocabulary kept bare so it lands in `FIXTURE_SOURCES`; checksum verification still applies). Locked by four `TestHdmSidecarTranslation` tests, including the fixture-provider and checksum-mismatch refusals.

**PAP status surface (new).** The Lab now has a **PAP Research** tab (`frontend/src/components/lab/PapResearchPanel.tsx`, backend `app/api/pap.py`) serving `GET /api/v1/pap/status`: phase gates (credentials, per-instrument provenance-verified data, experiment report), the frozen pre-registered criteria (`pap-criteria-v1`), and the latest experiment verdict. It is read-only by construction — no run/trigger endpoint exists; the verdict comes only from the offline runner's report. The phase currently reports `STAGE_1_BLOCKED_NO_REAL_DATA` until BANKNIFTY ingests and a report exists. This panel is the user-visible success/failure surface for Stage 1, deliberately showing the methodological verdict rather than a prediction display.

**Remaining before Phase 1 can run:** (1) complete BANKNIFTY ingestion; (2) H3 — the VWAP volume source for indices (HDM parquet includes a `volume` column; whether index volume is meaningful for VWAP remains a human call); (3) H10 — whether the pre-audit synthetic-trained artifacts influenced any real decision.

### Not done, and blocked

Phase 1 (the experiment itself) is not started — by design it waits on the pre-registered config and the runner, not on blocked infrastructure, since SENSEX/NIFTY data readiness is now established above. The three open human decisions from §8 are listed in the section above.

### Pre-existing failures beyond this work

The backend suite is `1819 passed, 20 failed`, and the 20 are unchanged from the pre-work baseline. None exercise provenance, dataset loading, or CV splitting. The closest, `test_module_boundaries.py::test_loc_budget_no_monolith_growth`, names `signals_persistence.py:1200 > baseline 1163`, a file not touched here.

**One regression was introduced and repaired during this work**, and it is instructive. Relocating the fixture out of `data/datasets` broke 10 tests in `tests/quant/test_quant_api.py` — the quant API endpoints require a 1m dataset on disk and return 404 without one, and `test_list_datasets` literally asserted `"SENSEX" in symbols`. Those tests were green **only because generated data sat in the real-data tree**: the same defect as Finding 1, expressed in the test suite. They now provision their own dataset in a temp root and the API is pointed at it, so the suite never depends on undisclosed market data and never writes into `data/raw`.
