"""DROID MACD + Fisher-9 Exhaustion Research — Validation Tests.

Specification Reference: §55 (Deliverables 0.3, 0.4, 0.5), §38.
"""

from __future__ import annotations

import math
import numpy as np
import pandas as pd
from app.signals.strategies.fisher_macd.fisher import calculate_fisher_point
from app.signals.strategies.fisher_macd.macd import calculate_macd
from app.signals.strategies.fisher_macd.atr import calculate_atr_series
from app.signals.strategies.fisher_macd.event_detector import detect_events_for_stages, deduplicate_episodes
from app.signals.strategies.fisher_macd.outcome_engine import compute_forward_outcomes


def enrich_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Enrich DataFrame with Fisher-9, MACD, and ATR series."""
    df = df.copy()
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    closes = df["close"].tolist()

    fisher_pts = calculate_fisher_point(highs, lows, period=9, price_source="HL2")
    macd_pts = calculate_macd(closes, fast_period=12, slow_period=26, signal_period=9)
    atr_pts = calculate_atr_series(highs, lows, closes, period=14)

    df["fisher"] = [p.fisher for p in fisher_pts]
    df["trigger"] = [p.trigger for p in fisher_pts]
    df["macd"] = [p.macd_line for p in macd_pts]
    df["macd_signal"] = [p.signal_line for p in macd_pts]
    df["macd_hist"] = [p.histogram for p in macd_pts]
    df["atr"] = [p.atr if hasattr(p, "atr") else p for p in atr_pts]
    return df


def verify_lookahead_perturbation(df: pd.DataFrame, test_indices: list[int] | None = None) -> bool:
    """Deliverable 0.3: Look-Ahead Proof.

    Perturb future bars t+1..t+5 by 10% and verify bar t indicators remain byte-identical.
    """
    df_clean = enrich_indicators(df)
    n = len(df)
    if test_indices is None:
        test_indices = [50, 100, 200, 500, 1000]

    for t in test_indices:
        if t >= n - 10:
            continue

        baseline_fisher = df_clean.loc[t, "fisher"]
        baseline_trigger = df_clean.loc[t, "trigger"]
        baseline_macd = df_clean.loc[t, "macd"]
        baseline_signal = df_clean.loc[t, "macd_signal"]
        baseline_atr = df_clean.loc[t, "atr"]

        # Perturb subsequent bars
        df_perturbed = df.copy()
        df_perturbed.loc[t + 1 : t + 5, "high"] = df_perturbed.loc[t + 1 : t + 5, "high"] * 1.50
        df_perturbed.loc[t + 1 : t + 5, "low"] = df_perturbed.loc[t + 1 : t + 5, "low"] * 0.50
        df_perturbed.loc[t + 1 : t + 5, "close"] = df_perturbed.loc[t + 1 : t + 5, "close"] * 1.30

        df_p_clean = enrich_indicators(df_perturbed)

        # Assert values at bar t did NOT change
        assert df_p_clean.loc[t, "fisher"] == baseline_fisher, f"Fisher at {t} leaked from future"
        assert df_p_clean.loc[t, "trigger"] == baseline_trigger, f"Trigger at {t} leaked from future"
        assert df_p_clean.loc[t, "macd"] == baseline_macd, f"MACD at {t} leaked from future"
        assert df_p_clean.loc[t, "macd_signal"] == baseline_signal, f"Signal at {t} leaked from future"
        assert df_p_clean.loc[t, "atr"] == baseline_atr, f"ATR at {t} leaked from future"

    return True


def run_random_null_test(
    n_bars: int = 5000,
    seed: int = 42,
) -> dict[str, float]:
    """Deliverable 0.4: Random-Null Test.

    Run the ablation pipeline on synthetic geometric Brownian motion.
    Must find NO statistically significant lift over baseline.
    """
    np.random.seed(seed)
    returns = np.random.normal(loc=0.0, scale=0.002, size=n_bars)
    price = 25000.0 * np.exp(np.cumsum(returns))

    highs = price * (1.0 + np.abs(np.random.normal(0, 0.001, size=n_bars)))
    lows = price * (1.0 - np.abs(np.random.normal(0, 0.001, size=n_bars)))
    df_null = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n_bars, freq="5min"),
        "open": price,
        "high": highs,
        "low": lows,
        "close": price,
        "volume": 1000.0,
    })

    df_null = enrich_indicators(df_null)
    events_by_stage = detect_events_for_stages(df_null)

    # Compute Stage C (Dual Extreme) outcomes
    events_c = deduplicate_episodes(events_by_stage["C_Dual_extreme"])
    outcomes = compute_forward_outcomes(df_null, events_c, horizon_bars=6)

    if not outcomes:
        return {"lift": 0.0, "p_value": 1.0, "significant": False}

    rets = [o.raw_return_atr for o in outcomes]
    t_stat, p_val = stats.ttest_1samp(rets, 0.0)

    # On random walk, p-value should not be significantly < 0.05
    mean_ret = float(np.mean(rets))
    return {
        "n_events": len(outcomes),
        "mean_return_atr": mean_ret,
        "p_value": float(p_val),
        "significant": bool(p_val < 0.05),
    }


def run_planted_signal_test(
    n_bars: int = 5000,
    planted_effect_atr: float = 1.2,
    seed: int = 123,
) -> dict[str, float]:
    """Deliverable 0.5: Planted-Signal Test.

    Inject a known mean-reverting edge at extreme bars.
    Pipeline MUST detect it with p < 0.01.
    """
    np.random.seed(seed)
    returns = np.random.normal(loc=0.0, scale=0.002, size=n_bars)
    price = 25000.0 * np.exp(np.cumsum(returns))
    highs = price * 1.001
    lows = price * 0.999

    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n_bars, freq="5min"),
        "open": price,
        "high": highs,
        "low": lows,
        "close": price,
        "volume": 1000.0,
    })
    df = enrich_indicators(df)
    events_by_stage = detect_events_for_stages(df)
    events_c = deduplicate_episodes(events_by_stage["C_Dual_extreme"])

    # Plant synthetic edge on future prices after these events
    df_planted = df.copy()
    for ev in events_c:
        idx = ev.bar_index
        atr = ev.atr
        if idx + 6 < n_bars:
            shift = planted_effect_atr * atr
            if ev.direction == "BEARISH_REVERSAL":
                # Price drops after bearish event
                df_planted.loc[idx + 1 : idx + 6, "close"] -= shift
                df_planted.loc[idx + 1 : idx + 6, "low"] -= shift
            else:
                # Price rises after bullish event
                df_planted.loc[idx + 1 : idx + 6, "close"] += shift
                df_planted.loc[idx + 1 : idx + 6, "high"] += shift

    outcomes = compute_forward_outcomes(df_planted, events_c, horizon_bars=6)
    rets = [o.raw_return_atr for o in outcomes]
    t_stat, p_val = stats.ttest_1samp(rets, 0.0)

    return {
        "n_events": len(outcomes),
        "mean_return_atr": float(np.mean(rets)),
        "p_value": float(p_val),
        "recovered": bool(p_val < 0.01 and np.mean(rets) > 0.2),
    }
