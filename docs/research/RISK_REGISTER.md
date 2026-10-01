# DROID MACD + Fisher-9 Exhaustion Research — Risk Register

This document tracks all critical risks to project success, data integrity, and statistical validity (§61), along with their active mitigations and verification mechanisms.

---

## Active Risk Matrix

| # | Risk | Likelihood | Impact | Severity | Active Mitigation & Verification Gate |
|---|---|---|---|---|---|
| **R1** | **Primary hypothesis is false** | Medium | High | **CRITICAL** | **Phase 0 MVR Hard Gate:** Run stage ablation on real NIFTY 5m data before any DB/UI build. Document a null result honestly if effect size < 0.15 ATR or 95% CI encompasses zero (§55). |
| **R2** | **Insufficient data for statistical power** | Medium | High | **HIGH** | **Power Analysis (§57):** Mandate pre-experiment sample size check (`required_n`). Flag any result with $n_{\text{eff}} < 20$ as `INSUFFICIENT_SAMPLE`. Never present underpowered nulls as proof of absence. |
| **R3** | **Scope creep delays core research** | High | High | **HIGH** | **Hard Phase Gates (§51R):** Strict 4-week Phase 0 budget. Phase 1–5 gated by automated test criteria and go/no-go checklists. |
| **R4** | **Fisher implementation mismatch** | Low | Critical | **CRITICAL** | **Pinned Reference Formula (§10R):** John F. Ehlers (2004) float64 formula with explicit golden-value fixture ($\ge 50$ bars) tested via automated pytest assertions. |
| **R5** | **Look-ahead bias in implementation** | Medium | Critical | **CRITICAL** | **Perturbation & AS-OF Tests (§55 0.3):** Systematically modify future bars $t+1 \dots t+k$ and assert that features and events at bar $t$ remain byte-identical. Enforce confirmation lag on pivots. |
| **R6** | **Multiple-testing inflation** | High | Medium | **HIGH** | **FDR / Benjamini-Hochberg Control (§33):** Centralized `trial_registry.json` recording every parameter search. Adjust all p-values to Benjamini-Hochberg q-values. |
| **R7** | **Overfitting to NIFTY** | Medium | Medium | **MEDIUM** | **Cross-Instrument Independence Framework (§3R, §56):** Report correlation-adjusted effective instrument count ($n_{\text{eff\_instruments}} \approx 1.1–1.5$). Mandate out-of-market Tier 3 expansion for final claims. |
| **R8** | **Data quality issues in 1m/5m spine** | Low | High | **HIGH** | **Data Provenance Gate (§3):** Enforce `backend/app/quant/data/provenance_gate.py` sidecar checks, SHA-256 checksums, and synthetic generator screens before running experiments. |
| **R9** | **Divergence parameter sensitivity** | High | Low | **MEDIUM** | **Parameter Sensitivity Testing (§23R):** Grid test pivot parameters `[3, 5, 7, 10]`. Automatically flag fragile signals as `FRAGILE_DIVERGENCE`. Treat divergence strictly as a modifier. |
| **R10** | **Phase 5 (UI) consumes budget before answers** | Medium | Medium | **MEDIUM** | **Prioritized Build Order (§44R):** Build P1 MVP research views (Pattern Comparison, Validation, Baselines) first as static/notebook outputs before investing in interactive UI components. |

---

## Status Reviews

- **2026-09-29:** Initialized Risk Register for v4 revision. All 10 risks mapped to Phase 0–5 deliverables.
