"""DROID MACD + Fisher-9 Exhaustion Research — Phase 0 MVR Pipeline.

Specification Reference: §55, §36R, §57, Gate 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence
import pandas as pd
import numpy as np
from scipy import stats

from app.signals.strategies.fisher_macd.validation_tests import enrich_indicators
from app.signals.strategies.fisher_macd.event_detector import detect_events_for_stages, deduplicate_episodes, ResearchEvent
from app.signals.strategies.fisher_macd.outcome_engine import compute_forward_outcomes, EventOutcome
from app.signals.strategies.fisher_macd.power import evaluate_power, PowerResult


@dataclass
class StageAblationRow:
    """Standardized ablation row per §36R."""
    stage_id: str
    stage_name: str
    n_raw: int
    n_eff: int
    power_category: str
    observed_power: float
    baseline_return_atr: float
    observed_return_atr: float
    lift_atr: float
    ci_lower_95: float
    ci_upper_95: float
    p_value: float
    q_value: float
    direction: str  # POSITIVE, NEUTRAL, NEGATIVE, INSUFFICIENT


def calculate_effective_n_intraday(events: list[ResearchEvent]) -> int:
    """Compute effective sample size with trading-day clustering (DEC-008, §31)."""
    if not events:
        return 0

    dates = [pd.to_datetime(ev.timestamp).date() for ev in events]
    unique_days = len(set(dates))
    total_events = len(events)

    if unique_days == 0:
        return 0

    avg_m = total_events / unique_days
    if avg_m <= 1.0:
        return total_events

    # Conservative intra-cluster correlation assumption rho = 0.25
    rho = 0.25
    design_effect = 1.0 + (avg_m - 1.0) * rho
    n_eff = int(math.ceil(total_events / design_effect))
    return max(1, min(total_events, n_eff))


def run_phase0_ablation(
    df: pd.DataFrame,
    horizon_bars: int = 6,  # 30-minute forward horizon (6 * 5m)
) -> tuple[pd.DataFrame, dict[str, any]]:
    """Run full Phase 0 ablation across stages A-F on real data."""
    df_enriched = enrich_indicators(df)

    # 1. Compute unconditional market baseline (random entry / baseline drift)
    # Forward 6-bar return in ATR units across all valid bars
    n = len(df_enriched)
    closes = df_enriched["close"].values
    atrs = df_enriched["atr"].values
    baseline_returns = []
    for i in range(40, n - horizon_bars):
        if atrs[i] is not None and atrs[i] > 0:
            ret = (closes[i + horizon_bars] - closes[i]) / atrs[i]
            baseline_returns.append(abs(ret))  # Mean absolute return baseline

    baseline_mean = float(np.mean(baseline_returns)) if baseline_returns else 0.0

    # 2. Detect events for all stages
    events_raw = detect_events_for_stages(df_enriched)

    stage_definitions = [
        ("A", "A_MACD_only", "A. MACD only"),
        ("B", "B_Fisher_only", "B. Fisher only"),
        ("C", "C_Dual_extreme", "C. Dual extreme"),
        ("D", "D_Exhaustion", "D. + Exhaustion"),
        ("E", "E_Ind_Confirmation", "E. + Ind. Confirmation"),
        ("F", "F_Price_Confirmation", "F. + Price Confirmation"),
    ]

    p_values: list[float] = []
    rows: list[dict] = []
    stage_outcomes: dict[str, list[EventOutcome]] = {}

    for stage_code, stage_key, stage_label in stage_definitions:
        evs = deduplicate_episodes(events_raw[stage_key])
        outcomes = compute_forward_outcomes(df_enriched, evs, horizon_bars=horizon_bars)
        stage_outcomes[stage_code] = outcomes

        n_raw = len(outcomes)
        if n_raw == 0:
            rows.append({
                "stage_id": stage_code,
                "stage_label": stage_label,
                "n_raw": 0,
                "n_eff": 0,
                "power_category": "INSUFFICIENT_SAMPLE",
                "observed_power": 0.0,
                "baseline": baseline_mean,
                "mean_return": 0.0,
                "lift": 0.0,
                "ci_lower": 0.0,
                "ci_upper": 0.0,
                "p_value": 1.0,
                "direction": "INSUFFICIENT",
            })
            p_values.append(1.0)
            continue

        n_eff = calculate_effective_n_intraday([o.event for o in outcomes])
        power_eval = evaluate_power(available_n_eff=n_eff, effect_size=0.15, baseline_std=1.0)

        rets = [o.raw_return_atr for o in outcomes]
        mean_ret = float(np.mean(rets))
        std_ret = float(np.std(rets, ddof=1)) if len(rets) > 1 else 1.0

        # Lift over zero expected return for direction-aligned signal
        lift = mean_ret
        se = std_ret / math.sqrt(n_eff)
        t_stat = lift / se if se > 0 else 0.0
        p_val = float(2.0 * (1.0 - stats.t.cdf(abs(t_stat), df=max(1, n_eff - 1))))
        p_values.append(p_val)

        ci_lower = lift - 1.96 * se
        ci_upper = lift + 1.96 * se

        if n_eff < 20:
            direction = "INSUFFICIENT"
        elif ci_lower > 0.0 and lift > 0.05:
            direction = "POSITIVE"
        elif ci_upper < 0.0 and lift < -0.05:
            direction = "NEGATIVE"
        else:
            direction = "NEUTRAL"

        rows.append({
            "stage_id": stage_code,
            "stage_label": stage_label,
            "n_raw": n_raw,
            "n_eff": n_eff,
            "power_category": power_eval.category,
            "observed_power": round(power_eval.observed_power, 2),
            "baseline": round(0.0, 3),  # Direction-aligned null baseline is 0.0 ATR
            "mean_return": round(mean_ret, 3),
            "lift": round(lift, 3),
            "ci_lower": round(ci_lower, 3),
            "ci_upper": round(ci_upper, 3),
            "p_value": p_val,
            "direction": direction,
        })

    # Benjamini-Hochberg FDR q-value adjustment (§33)
    m = len(p_values)
    sorted_indices = np.argsort(p_values)
    q_values = np.zeros(m)
    for rank, idx in enumerate(sorted_indices):
        q = p_values[idx] * m / (rank + 1)
        q_values[idx] = min(1.0, q)

    for i in range(len(rows)):
        rows[i]["q_value"] = round(q_values[i], 4)
        rows[i]["p_value"] = round(rows[i]["p_value"], 4)

    ablation_df = pd.DataFrame(rows)

    # Evaluate Gate 0 Go/No-Go criteria (§55)
    # Criteria:
    # 1. Ablation shows consistent positive lift at dual/exhaustion stage?
    # 2. CI excludes zero?
    # 3. Adequate power?
    c_lift = ablation_df.loc[ablation_df["stage_id"] == "C", "lift"].values[0]
    d_lift = ablation_df.loc[ablation_df["stage_id"] == "D", "lift"].values[0]
    d_ci_lower = ablation_df.loc[ablation_df["stage_id"] == "D", "ci_lower"].values[0]
    d_dir = ablation_df.loc[ablation_df["stage_id"] == "D", "direction"].values[0]
    d_q = ablation_df.loc[ablation_df["stage_id"] == "D", "q_value"].values[0]

    if d_dir == "POSITIVE" and d_q < 0.05:
        decision = "GO"
        rationale = "Dual extreme + exhaustion demonstrates statistically significant positive lift (CI excludes zero, q < 0.05)."
    elif d_lift > 0.0 and (c_lift > 0 or d_lift > c_lift):
        decision = "CONDITIONAL GO"
        rationale = "Positive directional lift observed across dual/exhaustion stages, but confidence intervals or sample sizes require targeted Phase 1 scope."
    elif d_lift <= 0.0 and c_lift <= 0.0:
        decision = "PIVOT"
        rationale = "Primary hypothesis shows no measurable directional edge on NIFTY 5m. Pivot or investigate before infrastructure investment."
    else:
        decision = "NO-GO"
        rationale = "Effect indistinguishable from random noise or underpowered."

    summary = {
        "decision": decision,
        "rationale": rationale,
        "stages": rows,
    }

    return ablation_df, summary
