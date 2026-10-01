"""DROID — MACD + Fisher-9 Divergence Research Runner (§23R).

Answers the core research question:
> Does the presence of divergence at the time of a dual-extreme / confluence event
> improve the forward outcome compared to events without divergence?

Also runs the §23R Parameter Sensitivity Matrix:
- pivot_left_bars: [3, 5, 7, 10]
- pivot_right_bars: [3, 5, 7, 10]
- max_pivot_separation: [50, 100, 150]
Checks for directional stability (robust vs FRAGILE_DIVERGENCE).
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
import sys

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import numpy as np

from research.core.fisher import calculate_fisher_point
from research.core.macd import calculate_macd
from research.core.atr import calculate_atr_series
from research.core.event_detector import ResearchEvent
from research.core.outcome_engine import compute_forward_outcomes
from research.core.divergence import (
    DivergenceType,
    detect_divergences,
    get_active_divergence_at_bar,
)


def evaluate_divergence_lift(
    df: pd.DataFrame,
    pivot_left: int = 5,
    pivot_right: int = 5,
    max_sep: int = 100,
    target_atr: float = 0.5,
    stop_atr: float = 1.0,
    horizon_bars: int = 12,
):
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    closes = df["close"].tolist()
    timestamps = [str(t) for t in df["timestamp"]] if "timestamp" in df.columns else [f"Bar {i}" for i in range(len(df))]

    f_pts = calculate_fisher_point(highs, lows, period=9, price_source="HL2")
    m_pts = calculate_macd(closes, fast_period=12, slow_period=26, signal_period=9)
    atr_pts = calculate_atr_series(highs, lows, closes, period=14)

    fisher_vals = [p.fisher for p in f_pts]
    trigger_vals = [p.trigger for p in f_pts]
    macd_vals = [p.macd_line for p in m_pts]
    signal_vals = [p.signal_line for p in m_pts]
    atr_vals = [p.atr if hasattr(p, "atr") else p for p in atr_pts]

    df["fisher"] = fisher_vals
    df["trigger"] = trigger_vals
    df["macd"] = macd_vals
    df["signal"] = signal_vals
    df["atr"] = atr_vals

    # Detect divergences on Fisher-9 and MACD
    fisher_divs = detect_divergences(
        highs=highs,
        lows=lows,
        indicator_values=fisher_vals,
        atr_values=atr_vals,
        indicator_name="fisher_9",
        timestamps=timestamps,
        pivot_left_bars=pivot_left,
        pivot_right_bars=pivot_right,
        max_pivot_separation=max_sep,
    )

    macd_divs = detect_divergences(
        highs=highs,
        lows=lows,
        indicator_values=macd_vals,
        atr_values=atr_vals,
        indicator_name="macd",
        timestamps=timestamps,
        pivot_left_bars=pivot_left,
        pivot_right_bars=pivot_right,
        max_pivot_separation=max_sep,
    )

    all_divs = sorted(fisher_divs + macd_divs, key=lambda d: d.confirmation_index)

    # Detect Confluence Events
    events: list[ResearchEvent] = []
    has_div_flags: list[bool] = []
    div_types: list[str] = []

    for i in range(30, len(df) - horizon_bars):
        f_prev = fisher_vals[i - 1]
        f_curr = fisher_vals[i]
        trig_prev = trigger_vals[i - 1]
        trig_curr = trigger_vals[i]
        m_curr = macd_vals[i]
        s_curr = signal_vals[i]
        atr = atr_vals[i]

        if (
            atr is None or np.isnan(atr) or atr <= 0
            or m_curr is None or s_curr is None
            or f_curr is None or f_prev is None
            or trig_curr is None or trig_prev is None
        ):
            continue

        ts_val = timestamps[i]

        is_bull = (m_curr > s_curr and f_prev < -1.0 and f_prev <= trig_prev and f_curr > trig_curr)
        is_bear = (m_curr < s_curr and f_prev > 1.0 and f_prev >= trig_prev and f_curr < trig_curr)

        if not (is_bull or is_bear):
            continue

        direction = "BULLISH_REVERSAL" if is_bull else "BEARISH_REVERSAL"

        # Check if matching divergence was confirmed within past 20 bars
        active_div = get_active_divergence_at_bar(i, all_divs, max_recency_bars=20)
        div_aligned = False
        div_label = "NONE"

        if active_div:
            if is_bull and active_div.divergence_type in (DivergenceType.REGULAR_BULLISH, DivergenceType.HIDDEN_BULLISH):
                div_aligned = True
                div_label = f"{active_div.indicator_name}_{active_div.divergence_type.value}"
            elif is_bear and active_div.divergence_type in (DivergenceType.REGULAR_BEARISH, DivergenceType.HIDDEN_BEARISH):
                div_aligned = True
                div_label = f"{active_div.indicator_name}_{active_div.divergence_type.value}"

        ev = ResearchEvent(
            bar_index=i,
            timestamp=ts_val,
            direction=direction,
            stage="CONFLUENCE",
            price=float(df["close"].iloc[i]),
            atr=float(atr),
            fisher=float(f_curr),
            trigger=float(trig_curr),
            macd=float(m_curr),
            macd_signal=float(s_curr),
            macd_hist=float(m_curr - s_curr),
        )
        events.append(ev)
        has_div_flags.append(div_aligned)
        div_types.append(div_label)

    if not events:
        return None

    # Compute outcomes for all events
    outcomes = compute_forward_outcomes(
        df,
        events,
        horizon_bars=horizon_bars,
        target_atr_multiple=target_atr,
        stop_atr_multiple=stop_atr,
    )

    # Split into With Divergence vs Without Divergence
    outcomes_with_div = [o for o, d in zip(outcomes, has_div_flags) if d]
    outcomes_no_div = [o for o, d in zip(outcomes, has_div_flags) if not d]

    def _stats(subset):
        if not subset:
            return {"n": 0, "wins": 0, "win_rate": 0.0, "ev": 0.0, "pf": 0.0}
        w = sum(1 for o in subset if o.success)
        l = len(subset) - w
        wr = (w / len(subset)) * 100
        gross_p = w * target_atr
        gross_l = l * stop_atr
        net_gain = gross_p - gross_l
        ev = net_gain / len(subset)
        pf = (gross_p / gross_l) if gross_l > 0 else (99.0 if w > 0 else 0.0)
        return {"n": len(subset), "wins": w, "win_rate": round(wr, 1), "ev": round(ev, 3), "pf": round(pf, 2)}

    stats_all = _stats(outcomes)
    stats_with = _stats(outcomes_with_div)
    stats_without = _stats(outcomes_no_div)

    lift_win_rate = round(stats_with["win_rate"] - stats_without["win_rate"], 1) if stats_with["n"] > 0 and stats_without["n"] > 0 else 0.0
    lift_ev = round(stats_with["ev"] - stats_without["ev"], 3) if stats_with["n"] > 0 and stats_without["n"] > 0 else 0.0

    return {
        "params": {"pivot_left": pivot_left, "pivot_right": pivot_right, "max_sep": max_sep},
        "total_divergences_detected": len(all_divs),
        "total_events": len(events),
        "events_with_divergence": stats_with["n"],
        "events_without_divergence": stats_without["n"],
        "stats_all": stats_all,
        "stats_with_divergence": stats_with,
        "stats_without_divergence": stats_without,
        "lift_win_rate_pct": lift_win_rate,
        "lift_ev_atr": lift_ev,
    }


def main():
    parser = argparse.ArgumentParser(description="DROID MACD + Fisher-9 Divergence Research Runner (§23R)")
    parser.add_argument("--symbol", type=str, default="NIFTY")
    parser.add_argument("--target-atr", type=float, default=0.5)
    parser.add_argument("--stop-atr", type=float, default=1.0)
    parser.add_argument("--run-sensitivity", action="store_true", help="Run full 3x3x3 parameter sensitivity grid")
    args = parser.parse_args()

    data_path = Path("backend/data/historical/parquet/nifty/5m/candles_v2.parquet")
    if not data_path.exists():
        data_path = Path("backend/data/historical/parquet/nifty/5m/candles_v1.parquet")

    df = pd.read_parquet(data_path).iloc[-5000:].reset_index(drop=True)

    print("=" * 85)
    print("DROID MACD + FISHER-9 DIVERGENCE ENGINE RESEARCH (§23R)")
    print("=" * 85)
    print(f"* Instrument   : {args.symbol.upper()} 5m ({len(df):,} bars)")
    print(f"* Exit Targets : Target = +{args.target_atr} ATR | Stop = -{args.stop_atr} ATR")

    # 1. Baseline Run with Default Parameters (Left=5, Right=5, MaxSep=100)
    res = evaluate_divergence_lift(
        df,
        pivot_left=5,
        pivot_right=5,
        max_sep=100,
        target_atr=args.target_atr,
        stop_atr=args.stop_atr,
    )

    print("\n[1] DEFAULT PARAMETER EVALUATION (Left=5, Right=5, MaxSep=100):")
    print("-" * 85)
    print(f"Total Divergences Discovered in History : {res['total_divergences_detected']}")
    print(f"Total Confluence Trades Evaluated       : {res['total_events']}")
    print(f"  * Trades WITH Co-occurring Divergence : {res['events_with_divergence']}")
    print(f"  * Trades WITHOUT Divergence           : {res['events_without_divergence']}")
    print("-" * 85)
    print(f"ALL CONFLUENCE TRADES       : Win Rate = {res['stats_all']['win_rate']}% | EV = {res['stats_all']['ev']:+.3f} ATR | PF = {res['stats_all']['pf']}")
    print(f"CONFLUENCE + DIVERGENCE     : Win Rate = {res['stats_with_divergence']['win_rate']}% | EV = {res['stats_with_divergence']['ev']:+.3f} ATR | PF = {res['stats_with_divergence']['pf']}")
    print(f"CONFLUENCE ALONE (NO DIV)   : Win Rate = {res['stats_without_divergence']['win_rate']}% | EV = {res['stats_without_divergence']['ev']:+.3f} ATR | PF = {res['stats_without_divergence']['pf']}")
    print("-" * 85)
    print(f"INCREMENTAL LIFT FROM DIVERGENCE: {res['lift_win_rate_pct']:+.1f}% Win Rate | {res['lift_ev_atr']:+.3f} ATR per trade")
    print("-" * 85)

    # 2. Parameter Sensitivity Grid (§23R)
    print("\n[2] PARAMETER SENSITIVITY GRID (§23R / §35):")
    grid_left = [3, 5, 7, 10]
    grid_right = [3, 5, 7, 10]
    grid_sep = [50, 100, 150]

    sensitivity_rows = []
    lifts = []

    for l_bars, r_bars, m_sep in itertools.product(grid_left, grid_right, grid_sep):
        r_run = evaluate_divergence_lift(
            df,
            pivot_left=l_bars,
            pivot_right=r_bars,
            max_sep=m_sep,
            target_atr=args.target_atr,
            stop_atr=args.stop_atr,
        )
        if r_run and r_run["events_with_divergence"] > 0:
            lift_wr = r_run["lift_win_rate_pct"]
            lift_ev = r_run["lift_ev_atr"]
            lifts.append(lift_wr)
            sensitivity_rows.append({
                "left": l_bars,
                "right": r_bars,
                "max_sep": m_sep,
                "n_with_div": r_run["events_with_divergence"],
                "wr_with_div": r_run["stats_with_divergence"]["win_rate"],
                "lift_wr": lift_wr,
                "lift_ev": lift_ev,
            })

    # Display sample sensitivity results
    print(f"{'Left':<6} {'Right':<6} {'MaxSep':<8} {'Trades':<8} {'WR With Div':<13} {'WR Lift':<10} {'EV Lift':<10}")
    print("-" * 65)
    for row in sensitivity_rows[::6]:  # sample every 6th configuration
        print(f"{row['left']:<6} {row['right']:<6} {row['max_sep']:<8} {row['n_with_div']:<8} {row['wr_with_div']:.1f}%{'':<6} {row['lift_wr']:+.1f}%{'':<4} {row['lift_ev']:+.3f} ATR")

    # Check stability
    positive_lifts = sum(1 for x in lifts if x >= 0)
    stability_pct = (positive_lifts / len(lifts) * 100) if lifts else 0.0
    is_robust = stability_pct >= 70.0
    flag = "ROBUST_DIVERGENCE" if is_robust else "FRAGILE_DIVERGENCE"

    print("-" * 65)
    print(f"Divergence Stability Classification: >>> {flag} <<< ({stability_pct:.1f}% of param combinations yield positive lift)")
    print("=" * 85)


if __name__ == "__main__":
    main()
