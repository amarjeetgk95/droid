# Phase 0 Audit: DROID Indicator Research Baseline

**Status:** Completed  
**Date:** 2026-09-30  
**Baseline Test Count:** 167 passed (0 failures, 0 warnings) in 6.84s  
**Test Suite Path:** `backend/tests/indicator_research/`  

---

## 1. Existing Module Map

The existing Indicator Research system lives entirely within `backend/app/indicator_research/` and is strictly partitioned:

```text
backend/app/indicator_research/
├── __init__.py
├── api.py                    # Read-only FastAPI surface (17 endpoints)
├── data.py                   # Canonical historical candle adapter (parquet reader)
├── enums.py                  # Domain enums (IndicatorCategory, RuleOperator, EntryFill, etc.)
├── safety.py                 # Static isolation guard (prohibits broker/order execution imports)
├── schemas.py                # Pydantic request/response schemas
├── backtesting/
│   ├── costs.py              # Indian statutory costs (STT, GST, SEBI, exchange, stamp duty, slippage)
│   ├── engine.py             # Event-driven backtest engine (conservative SL/TP, next open)
│   ├── metrics.py            # Comprehensive quant metrics (Sharpe, Sortino, Calmar, MAE, MFE)
│   ├── models.py             # Dataclass domain models (Trade, EquityPoint, BacktestResult)
│   ├── settings.py           # Backtest configuration parser and validator
│   └── validation.py         # Structural output and causality validator
├── indicators/
│   ├── base.py               # BaseIndicator abstract class, ParameterSpec, OutputSpec
│   ├── cycle.py              # EbswIndicator, MamaFamaIndicator, DominantCycleIndicator
│   ├── helpers.py            # Vectorized/causal math helpers (ema, sma, rsi, rolling windows)
│   ├── momentum.py           # FisherTransform, StochRsi, WaveTrend, Stc, Rsi, Macd, Cci, WilliamsR
│   ├── registry.py           # Auto-discovering registry using pkgutil
│   ├── trend.py              # Sma, Ema, VwapIndicator, Supertrend, Adx, Donchian
│   └── volatility.py         # AtrIndicator, BollingerBandsIndicator
├── research/
│   ├── analysis.py           # Prediction research (forward return study vs unconditional baseline)
│   ├── comparison.py         # Multi-indicator comparison runner
│   ├── experiments.py        # Experiment persistence (atomic JSON manifest in data/experiments)
│   ├── features.py           # Multi-indicator feature builder and rule extractor
│   ├── optimizer.py          # Grid search parameter optimizer
│   ├── runner.py             # Single execution runner unifying optimizer, backtest, and walkforward
│   └── walkforward.py        # Chronological walk-forward validator (train/test/step)
└── signals/
    └── rules.py              # AST-based causal temporal rule evaluator (crosses, turns, slopes)
```

---

## 2. Registry Mechanics

* **Location:** `backend/app/indicator_research/indicators/registry.py`
* **Discovery:** Walks `app.indicator_research.indicators` using `pkgutil.iter_modules`.
* **Exclusions:** Automatically skips `{"base", "registry", "helpers", "__init__"}` and modules prefixed with `_`.
* **Lifecycle:** Stateless indicator instances registered by `metadata.id`.
* **Extensibility:** Adding a new indicator subclass in any module inside `indicators/` (such as `microstructure.py`) automatically registers it everywhere with zero router or enum edits.

---

## 3. Signal Rule Engine (`rules.py`) Capabilities

* **Design:** Strictly AST/JSON document evaluation per bar; no code generation, no `eval()`.
* **Supported Operators:**
  * Comparisons: `>`, `<`, `>=`, `<=`, `==`, `!=`
  * Temporal Causal: `crosses_above`, `crosses_below`, `turns_up`, `turns_down`, `slope_up`, `slope_down`
  * Range: `in_range`, `outside_range`
  * Logic: `AND`, `OR`, `NOT`, nested rule groups (max depth 12).
* **Missing Data:** Warm-up `None` values evaluate to `False` (never 0, never raise).
* **Lookahead Immunity:** Operators only inspect index $t$ and strictly earlier indices ($t-1, t-2, \dots$).

---

## 4. Backtest Engine Semantics (`engine.py`)

* **Entry Sequencing:** Next-bar open by default (`EntryFill.NEXT_OPEN`). Signals confirmed strictly at bar close.
* **Intrabar Ambiguity Resolution:** **Already Conservative!**
  * When a single bar touches both SL and TP: Stop-Loss is assumed hit first (`test_stop_is_assumed_hit_before_target_when_a_bar_contains_both`).
  * Gaps through stop: Fills at bar `Open` (worse than stop), never at the stop price (`test_a_gap_through_the_stop_fills_at_the_open_not_the_stop`).
* **Position Model:** 1 open position at a time; ignored signals during active positions are counted.
* **Cost Engine:** `backend/app/indicator_research/backtesting/costs.py` supports:
  * Brokerage (flat per order or percentage)
  * STT (Securities Transaction Tax)
  * Exchange turnover charges (NSE/BSE)
  * GST (18% on brokerage + exchange charges)
  * SEBI turnover charges
  * Stamp duty
  * Slippage (points, percentage, ATR multiple)
  * Costs charged exactly once per fill, separated into gross P&L and net P&L.

---

## 5. Market-Data Spine & Existing Indian Calendar

The repository already houses production-grade market data infrastructure:
* **Trading Calendar:** `backend/app/historical_data/calendar/india.py` (`IndianMarketCalendar`)
  * Regular session: `09:15:00` to `15:30:00` IST.
  * Bar timestamp convention: Bar timestamp = bar START time (e.g. `09:15:00` covers `[09:15:00, 09:16:00)`).
  * Official NSE/BSE holidays 2023–2027 + Muhurat special sessions.
* **Quality Engine:** `backend/app/historical_data/validation/quality_engine.py` (`HistoricalQualityEngine`)
  * Tier 1 Hard Gates: Negative/zero prices, Geometric OHLC violations, non-monotonic timestamps, weekend/holiday leakage, session boundary violations.
* **Async Job Model:** `backend/app/historical_data/models/job.py` (`HistoricalDownloadJob`)
  * Status states: `QUEUED`, `RUNNING`, `PARTIAL`, `COMPLETED`, `FAILED`, `CANCELLED`.

---

## 6. Existing Causality & Safety Verification

* `backend/tests/indicator_research/test_causality.py`:
  * Tests prefix-invariance: verifies that computing on $D[0 \dots T]$ yields identical output to $D[0 \dots T+N][0 \dots T]$ across all registered indicators.
* `backend/tests/indicator_research/test_safety.py`:
  * Proves that `app.indicator_research` contains zero imports of broker order-placement or live execution code.

---

## 7. Baseline Verification Count

* **Command:** `.venv\Scripts\pytest backend\tests\indicator_research -q`
* **Result:** **167 passed** in 6.84 seconds.
* **Full list of test IDs recorded in:** `backend/tests/BASELINE.md`.

---

## 8. Specification vs. Codebase Alignment & Gap Matrix

| Component | Status in Codebase | Action for Implementation |
| :--- | :--- | :--- |
| **Fisher Transform** | Implemented in `momentum.py` | Verify $\pm 1.5$ thresholds and golden fixtures. |
| **EBSW** | Implemented in `cycle.py` | Add explicit `trigger` output alongside `ebsw` and `wave`. |
| **STC** | Implemented in `momentum.py` | Golden fixture verification. |
| **MAMA / FAMA** | Implemented in `cycle.py` | Expose fast/slow limits dynamically; golden fixture. |
| **WaveTrend** | Implemented in `momentum.py` | Golden fixture verification. |
| **Stochastic RSI** | Implemented in `momentum.py` | Expose raw `stoch_rsi` output alongside `k` and `d`. |
| **Anchored VWAP** | Rolling/session in `trend.py` | Extend to session, week, month, manual anchors; require futures volume. |
| **Volume Profile** | Missing from research module | Implement in `trend.py` (POC, VAH 70%, VAL, HVN, LVN, `ESTIMATED` badge). |
| **CVD / Delta** | Missing from research module | Implement in `microstructure.py` with causal pivot confirmation. |
| **Absorption** | Missing from research module | Implement in `microstructure.py` with measurable quantitative thresholds. |
| **DPFI** | Missing from research module | Implement fixed canonical DPFI v1 ($\le 3$ params) in `microstructure.py`. |
| **Data Provenance** | Implicit | Add `REAL`, `PROXY`, `UNAVAILABLE` badges and gate historical runs on missing depth. |
| **Live Tick Recorder** | Live websocket exists in providers | Implement Phase 7 background parquet depth/tick recorder against spine. |
| **Selectivity Analysis** | Missing | Build parameter/threshold sweep runner + API endpoint + frontend tab. |
| **Robustness Analysis** | Missing | Build parameter perturbation ($\pm k$ steps) and cost stress testing. |
| **Multiple-Testing** | Missing | Add `trials.parquet` lineage tracking, warning tiers, and DSR adjustment. |
| **Ablation Analysis** | Missing | Add on-demand component removal runner for multi-indicator setups. |
| **OOS Enforced Lock**| Walkforward exists; lock missing| Add cryptographic test range lock and `TEST CONSUMED` flag. |

---

## 9. Phase 0 Gate Exit Confirmation

- [x] Every codebase verification item resolved.
- [x] Zero code modifications made in Phase 0.
- [x] Baseline test count confirmed at 167.
- [x] Public interfaces and contracts preserved.
- [x] **Phase 0 is APPROVED. Ready to proceed to Phase 1.**
