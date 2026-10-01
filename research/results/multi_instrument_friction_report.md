# DROID Multi-Instrument Independence & Friction Research Report (§56, §3R, §58)

**Date:** 2026-09-29  
**Specification:** MACD + Fisher-9 Exhaustion Research v4  
**Evaluated Instruments:** NIFTY, BANKNIFTY, SENSEX (5m Historical Parquet)  

---

## 1. Cross-Instrument Independence Analysis (§56 & §3R)

### Pairwise Daily Return Correlation Matrix

| Index Pair | Pearson Correlation ($r$) | Independence Tier |
|---|---|---|
| **NIFTY – BANKNIFTY** | 0.8055 | Low Independence (~0.15 - 0.25) |
| **NIFTY – SENSEX** | 0.9391 | Near-Zero Independence (~0.05) |
| **BANKNIFTY – SENSEX** | 0.7723 | Low Independence |

- **Nominal Instruments ($N$):** 3
- **Average Pairwise Correlation ($\bar{\rho}$):** 0.8389
- **Effective Instruments ($n_{\text{eff}}$):** **1.12**

> **Scientific Caution (§3R):** A strategy that succeeds on NIFTY, BANKNIFTY, and SENSEX has an effective independent confirmation count of **1.12**, not 3.0. True independent replication requires Tier 3 instruments (S&P 500, DAX) or non-equity assets (Gold, Crude).

---

## 2. Cross-Instrument Performance Summary

| Instrument | Trades | Win Rate % | Profit Factor | Net Gain (ATR) | Expected Value (EV) | Directional Alignment |
|---|---|---|---|---|---|---|
| **NIFTY** | 45 | 68.9% | 1.11 | +1.50 ATR | +0.033 ATR | **POSITIVE** |
| **BANKNIFTY** | 29 | 69.0% | 1.11 | +1.00 ATR | +0.034 ATR | **POSITIVE** |
| **SENSEX** | 47 | 63.8% | 0.88 | -2.00 ATR | -0.043 ATR | **POSITIVE** |

---

## 3. Friction-Aware Outcome Analysis (§58)

| Instrument | Raw EV | After 0.05 ATR Friction | After 0.10 ATR Friction | After 0.15 ATR Friction | Economic Viability |
|---|---|---|---|---|---|
| **NIFTY** | +0.033 ATR | -0.017 ATR | -0.067 ATR | -0.117 ATR | DEGRADES |
| **BANKNIFTY** | +0.034 ATR | -0.016 ATR | -0.066 ATR | -0.116 ATR | DEGRADES |
| **SENSEX** | -0.043 ATR | -0.093 ATR | -0.143 ATR | -0.193 ATR | DEGRADES |
