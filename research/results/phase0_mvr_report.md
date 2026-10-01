# DROID MACD + Fisher-9 Exhaustion Research — Phase 0 MVR Report

**Date:** 2026-09-29  
**Instrument:** NIFTY (Spot Index)  
**Timeframe:** 5-minute  
**Dataset Bars:** 18,542 (2025-09-22 03:45:00+00:00 to 2026-09-22 09:55:00+00:00)  
**Gate 0 Decision:** **PIVOT**  

---

## 1. Validation Integrity Gates

| Test | Deliverable | Result | Status |
|---|---|---|---|
| **Look-Ahead Perturbation Test** | 0.3 | Byte-identical outputs under future perturbation | **PASS** |
| **Random-Null Test** | 0.4 | Mean Return: -0.2855 ATR, p-val: 0.3290 | **PASS (No spurious edge)** |
| **Planted-Signal Test** | 0.5 | Recovered: 1.2039 ATR, p-val: 2.0524e-06 | **PASS (Signal recovered)** |

---

## 2. Standardized Ablation Table (§36R)

| Stage | N | n_eff | Power | Obs. Power | Baseline | Lift | 95% CI | q-value | Direction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A. MACD only | 143 | 138 | UNDERPOWERED | 0.42 | 0.000 | -0.099 | [-0.524, 0.326] | 0.6483 | NEUTRAL |
| B. Fisher only | 383 | 324 | MARGINALLY_POWERED | 0.77 | 0.000 | -0.300 | [-0.577, -0.023] | 0.2089 | NEGATIVE |
| C. Dual extreme | 127 | 122 | UNDERPOWERED | 0.38 | 0.000 | -0.195 | [-0.651, 0.262] | 0.4852 | NEUTRAL |
| D. + Exhaustion | 116 | 111 | UNDERPOWERED | 0.35 | 0.000 | -0.278 | [-0.729, 0.172] | 0.3425 | NEUTRAL |
| E. + Ind. Confirmation | 116 | 110 | UNDERPOWERED | 0.35 | 0.000 | -0.347 | [-0.845, 0.150] | 0.3482 | NEUTRAL |
| F. + Price Confirmation | 51 | 50 | SEVERELY_UNDERPOWERED | 0.19 | 0.000 | -0.743 | [-1.653, 0.167] | 0.3477 | NEUTRAL |

---

## 3. Gate 0 Decision Rationale

> **PIVOT:** Primary hypothesis shows no measurable directional edge on NIFTY 5m. Pivot or investigate before infrastructure investment.

---

## 4. Power Analysis Summary (§57)

- **Minimum Detectable Effect Size:** 0.15 ATR
- **Effective Sample Sizes ($n_{\text{eff}}$):** Clustered by trading day per DEC-008.
- **Reporting Thresholds:** All stages satisfy $n_{\text{eff}} \ge 20$ for valid statistical reporting.
