# DROID MACD + Fisher-9 Exhaustion Research — Decision Register

This document records all significant methodological, statistical, and architectural decisions made for the MACD + Fisher-9 Exhaustion Research system (§60).

---

## DEC-001: Fisher-9 Reference Implementation

**Date:** 2026-09-29  
**Decision:** Use John F. Ehlers' original Fisher Transform (2004, Chapter 4) with 0.33/0.67 smoothing on normalized position within 9-period High-Low channel, clamped to `(-0.999, +0.999)` float64, and output blended `0.5 * ln(...) + 0.5 * Fisher[1]`.  
**Alternatives Considered:**  
- TradingView Pine Script `ta.fisher` (uses slightly different internal smoothing and clamp).  
- AmiBroker Fisher Transform (uses differing initial bar lookback).  
**Rationale:** Ehlers (2004) is the canonical published reference. Pinned formula defined in §10R eliminates ambiguity. Deviations require an explicit `config_version_hash`.  
**Reversible:** Yes, with new `config_version_hash`.  
**Status:** Active.

---

## DEC-002: MACD EMA Initialization Method

**Date:** 2026-09-29  
**Decision:** Standard EMA formula with multiplier `alpha = 2.0 / (period + 1.0)`. Fast period = 12, slow period = 26, signal period = 9 on price `Close`. The seed value for each EMA is the Simple Moving Average (SMA) of the first `period` bars. Bars prior to slow period completion (26 bars) yield `NaN`/`None`. Signal line yields `NaN` until `26 + 9 - 1` bars have elapsed.  
**Alternatives Considered:**  
- Seed with initial bar close: introduces long transient distortion.  
- 0.85 scaling factor approximation (observed in legacy prototype): rejected under v4 §10R / §2.1 fail-open prohibition.  
**Rationale:** SMA seed with proper lookback ensures mathematically honest EMAs without synthetic approximation or premature unseeded values.  
**Reversible:** Yes, with new `config_version_hash`.  
**Status:** Active.

---

## DEC-003: ATR Calculation Method

**Date:** 2026-09-29  
**Decision:** Standard Wilder's 14-period Average True Range (ATR). First 14 bars compute True Range `TR = max(High - Low, |High - Close[1]|, |Low - Close[1]|)`. Bar 14 seeds ATR via 14-period SMA of TR. Subsequent bars use Wilder's recursive smoothing: `ATR[t] = (ATR[t-1] * 13 + TR[t]) / 14.0`.  
**Alternatives Considered:**  
- Standard 14-period EMA of TR: diverges from classic Wilder ATR.  
- Simple rolling 14-bar SMA: higher variance.  
**Rationale:** Matches canonical Wilder definition and aligns with `backend/app/quant/indicators.py:calculate_atr`.  
**Reversible:** Yes, with new `config_version_hash`.  
**Status:** Active.

---

## DEC-004: Pivot Detection Parameters for Divergence

**Date:** 2026-09-29  
**Decision:** Default pivot window is `pivot_left_bars = 5`, `pivot_right_bars = 5`. Confirmation lag is strictly `right_bars` (5 bars). Timestamp convention: `event_timestamp = bar_close_ts[i + right_bars]`; `pivot_timestamp = bar_close_ts[i]`. `max_pivot_separation = 100`, `min_pivot_separation = 5`. Pairing strategy: `nearest` valid pair.  
**Alternatives Considered:**  
- Unconfirmed pivots at bar `i`: introduces fatal look-ahead bias.  
- ZigZag with threshold: arbitrary percentage threshold, unstable in intraday indices.  
**Rationale:** Prevents look-ahead leakage. Parameter sensitivity test across `[3, 5, 7, 10]` left/right bars detects and flags `FRAGILE_DIVERGENCE`.  
**Reversible:** Yes, with new `config_version_hash`.  
**Status:** Active.

---

## DEC-005: Episode De-duplication Rules

**Date:** 2026-09-29  
**Decision:** When consecutive bars trigger the same extreme/exhaustion criteria within an active wave, collapse them into a single **Episode**. An episode opens on the first qualifying bar and extends until the indicator exits the extreme zone (Fisher returns to normal range `[-1.5, +1.5]` or opposite crossing). Only the initial qualifying signal or the peak extremum within the episode is evaluated for forward outcomes to prevent clustered auto-correlated sample inflation.  
**Alternatives Considered:**  
- Treat every bar as an independent event: severely violates independence, inflates sample size $N$, and destroys statistical power validity.  
**Rationale:** Conforms to v4 §19 and §31 (effective $N$ calculation).  
**Reversible:** Yes, with new `config_version_hash`.  
**Status:** Active.

---

## DEC-006: First-Passage Same-Bar Double-Touch Resolution

**Date:** 2026-09-29  
**Decision:** When both upper target barrier (+1.0 ATR) and adverse barrier (-1.0 ATR) are touched within the same forward bar:  
1. If 1m granular bar data is available within the 5m bar, resolve path order causality using the 1m sequence.  
2. If 1m path is ambiguous or equal, resolve conservatively as **adverse hit** (pessimistic resolution).  
**Alternatives Considered:**  
- Ignore double touches or mark as unresolved: biases survival rates.  
- Assume favorable touch first: creates optimistic bias.  
**Rationale:** Trading science requires worst-case assumptions when intraday path is unobservable.  
**Reversible:** Yes, with new `config_version_hash`.  
**Status:** Active.

---

## DEC-007: Chronological Split Date Boundaries

**Date:** 2026-09-29  
**Decision:** For the 1-year historical dataset (2025-09-22 to 2026-09-22, 18,542 5m bars):  
- **Training Set (60%):** 2025-09-22 to 2026-04-30 (~11,100 bars)  
- **Validation Set (20%):** 2026-05-01 to 2026-07-15 (~3,700 bars)  
- **Holdout Set (20%):** 2026-07-16 to 2026-09-22 (~3,742 bars) — *Sealed until Gate 3 completion*.  
**Alternatives Considered:**  
- Random k-fold cross validation: strictly prohibited due to temporal leakage and autocorrelation.  
**Rationale:** Chronological splits with embargo and purge guarantee zero future-leakage and preserve market regime transitions.  
**Reversible:** Yes, with documented rationale and version change.  
**Status:** Active.

---

## DEC-008: Effective N Clustering Method

**Date:** 2026-09-29  
**Decision:** Single-instrument effective sample size $n_{\text{eff}}$ uses trading-day clustering:  
$$n_{\text{eff}} = \frac{N}{1 + (\bar{m} - 1) \rho_{\text{intra}}}$$  
where $\bar{m}$ is the average number of events per trading day with at least one event, and $\rho_{\text{intra}}$ is the intra-day event outcome correlation. Cross-instrument pooling applies:  
$$n_{\text{eff\_instruments}} = \frac{N_{\text{inst}}}{1 + (N_{\text{inst}} - 1) \bar{\rho}_{\text{pair}}}$$  
**Alternatives Considered:**  
- Raw $N$: overestimates statistical power and creates false discovery.  
**Rationale:** Enforces §31, §56, and §57. Guarantees that clustered intraday occurrences do not generate illusory significance.  
**Reversible:** No (required by statistical framework).  
**Status:** Active.

---

## DEC-009: Price Basis Choice (Spot vs Continuous Futures)

**Date:** 2026-09-29  
**Decision:** Phase 0–3 core research uses **Spot Index** data (`NIFTY 50`, `BANKNIFTY`, `BSE SENSEX`) from real historical feeds (Fyers v3 API). Friction analysis (§58) is disabled for Spot Index (as spot is not directly tradable) and enabled when evaluating Continuous Futures in Phase 4+.  
**Alternatives Considered:**  
- Continuous futures as default: introduces roll-yield anomalies and contract adjustment artifacts into baseline statistical indicator research.  
**Rationale:** Purity of price action indicator properties is best isolated on cash indices; economic friction is tested as a secondary layer.  
**Reversible:** Yes.  
**Status:** Active.

---

## DEC-010: Session Boundary Handling for Overnight Gaps

**Date:** 2026-09-29  
**Decision:** Indicator computations (EMA, Fisher, ATR) run continuously across sessions with natural overnight gaps preserved (no artificial price stitching). Forward outcome evaluation for intraday horizons (e.g. 5 bars = 25 minutes) does **not** cross the 15:30 IST market close: events occurring within $H$ bars of market close are either capped at session close (3:30 PM) or segregated into an overnight-holding cohort.  
**Alternatives Considered:**  
- Treat 09:15 as contiguous with 15:30: introduces overnight jump gap into intraday forward returns.  
**Rationale:** Prevents overnight gap volatility from polluting intraday forward return measurement.  
**Reversible:** Yes.  
**Status:** Active.
