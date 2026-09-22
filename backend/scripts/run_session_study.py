"""Empirical Session Liquidity Study Runner (Tier 0 Quant).

Executes comparative empirical backtests on BSE SENSEX across 1m, 5m, and 15m
for S1, S2, S3, S4, and ALL portfolio combination:
- Baseline (All day 09:15-15:30 IST)
- Session-Conditioned (Institutional liquidity windows: 09:20-10:30 & 14:15-15:15 IST)

Quantifies:
1. Mid-day chop elimination
2. Statutory transaction cost drag reduction
3. Net expectancy, Win Rate, Profit Factor, and Max Drawdown impacts
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure backend root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import polars as pl
from app.quant.data.dataset_manager import DatasetManager
from app.quant.data.provenance import assert_real_dataset
from app.quant.backtest.backtest_harness import BacktestHarness
from app.quant.strategies.strategies import DEFAULT_SESSION_WINDOWS

STRATEGY_DESCRIPTIONS: dict[str, str] = {
    "S1": "Opening Range Breakout (ORB)",
    "S2": "Momentum Breakout",
    "S3": "VWAP Reclaim / Reject",
    "S4": "Volatility Squeeze Breakout",
    "ALL": "Orthogonal Ensemble (S1+S2+S3+S4)",
}


def find_sensex_dataset() -> Path:
    """Locates the SENSEX 1m Parquet dataset."""
    candidates = [
        BASE_DIR / "data" / "datasets" / "SENSEX_1m.parquet",
        BASE_DIR / "data" / "raw" / "sensex" / "1m.parquet",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"SENSEX dataset not found in candidates: {[str(c) for c in candidates]}")


def run_session_study_for_timeframe(
    df_1m: pl.DataFrame,
    timeframe: str,
    k_tp: float = 2.5,
    k_sl: float = 1.0,
    t_max_bars: int = 12,
    trend_aligned: bool = True,
    stress_multiplier: float = 1.0,
    allowed_windows: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Runs baseline vs session-conditioned backtests for all strategies at a given timeframe."""
    windows = allowed_windows or DEFAULT_SESSION_WINDOWS

    if timeframe != "1m":
        df = DatasetManager.resample_candles(df_1m, target_timeframe=timeframe)
    else:
        df = df_1m

    results = []

    for strat_key in ["S1", "S2", "S3", "S4", "ALL"]:
        strat_name = STRATEGY_DESCRIPTIONS.get(strat_key, strat_key)

        # 1. Baseline Run (All Day)
        harness_baseline = BacktestHarness(
            lot_size=10,
            t_max_bars=t_max_bars,
            k_tp=k_tp,
            k_sl=k_sl,
            trend_aligned=trend_aligned,
            session_filter=False,
        )
        trades_base, metrics_base = harness_baseline.run_backtest(
            df=df,
            strategy_key=strat_key,
            stress_multiplier=stress_multiplier,
            session_filter=False,
        )

        # 2. Session-Conditioned Run (09:20-10:30 & 14:15-15:15)
        harness_session = BacktestHarness(
            lot_size=10,
            t_max_bars=t_max_bars,
            k_tp=k_tp,
            k_sl=k_sl,
            trend_aligned=trend_aligned,
            session_filter=True,
            allowed_windows=windows,
        )
        trades_session, metrics_session = harness_session.run_backtest(
            df=df,
            strategy_key=strat_key,
            stress_multiplier=stress_multiplier,
            session_filter=True,
            allowed_windows=windows,
        )

        # Compute improvements / deltas
        trade_reduction_pct = (
            ((metrics_base.total_trades - metrics_session.total_trades) / max(1, metrics_base.total_trades)) * 100.0
        )
        cost_drag_reduction_pct = (metrics_base.cost_drag_pct - metrics_session.cost_drag_pct) * 100.0
        net_exp_delta_pct = (metrics_session.net_expectancy_pct - metrics_base.net_expectancy_pct) * 100.0
        pf_delta = metrics_session.profit_factor - metrics_base.profit_factor
        dd_delta_pct = (metrics_session.max_drawdown_pct - metrics_base.max_drawdown_pct) * 100.0

        results.append({
            "strategy_key": strat_key,
            "strategy_name": strat_name,
            "baseline": {
                "trades": metrics_base.total_trades,
                "win_rate": round(metrics_base.win_rate, 4),
                "gross_expectancy_pct": round(metrics_base.gross_expectancy_pct, 4),
                "net_expectancy_pct": round(metrics_base.net_expectancy_pct, 4),
                "profit_factor": round(metrics_base.profit_factor, 2),
                "max_drawdown_pct": round(metrics_base.max_drawdown_pct, 4),
                "cost_drag_pct": round(metrics_base.cost_drag_pct, 4),
                "annualized_sharpe": round(metrics_base.annualized_sharpe, 2),
                "deflated_sharpe_ratio": round(metrics_base.deflated_sharpe_ratio, 4),
                "gate_g0_verdict": metrics_base.gate_g0_verdict,
            },
            "session": {
                "trades": metrics_session.total_trades,
                "win_rate": round(metrics_session.win_rate, 4),
                "gross_expectancy_pct": round(metrics_session.gross_expectancy_pct, 4),
                "net_expectancy_pct": round(metrics_session.net_expectancy_pct, 4),
                "profit_factor": round(metrics_session.profit_factor, 2),
                "max_drawdown_pct": round(metrics_session.max_drawdown_pct, 4),
                "cost_drag_pct": round(metrics_session.cost_drag_pct, 4),
                "annualized_sharpe": round(metrics_session.annualized_sharpe, 2),
                "deflated_sharpe_ratio": round(metrics_session.deflated_sharpe_ratio, 4),
                "gate_g0_verdict": metrics_session.gate_g0_verdict,
            },
            "deltas": {
                "trade_reduction_pct": round(trade_reduction_pct, 2),
                "cost_drag_reduction_pct": round(cost_drag_reduction_pct, 4),
                "net_exp_delta_pct": round(net_exp_delta_pct, 4),
                "pf_delta": round(pf_delta, 2),
                "dd_delta_pct": round(dd_delta_pct, 4),
            },
        })

    return {
        "timeframe": timeframe,
        "total_bars": len(df),
        "results": results,
    }


def format_timeframe_markdown_table(tf_data: dict[str, Any]) -> str:
    """Generates formatted side-by-side comparative Markdown table for a timeframe."""
    lines = []
    tf = tf_data["timeframe"]
    bars = tf_data["total_bars"]
    lines.append(f"### SENSEX Empirical Session Study - {tf} (Total Bars: {bars:,})")
    lines.append("")
    lines.append("| Strategy | Condition | Trades | Win Rate | Gross Exp % | Net Exp % | Profit Factor | Max DD % | Cost Drag % | Verdict |")
    lines.append("|:---|:---|---:|---:|---:|---:|---:|---:|---:|:---:|")

    for r in tf_data["results"]:
        s_key = r["strategy_key"]
        b = r["baseline"]
        s = r["session"]

        b_wr = f"{b['win_rate'] * 100:.2f}%"
        b_gross = f"{b['gross_expectancy_pct'] * 100:+.2f}%"
        b_net = f"{b['net_expectancy_pct'] * 100:+.2f}%"
        b_pf = f"{b['profit_factor']:.2f}"
        b_dd = f"{b['max_drawdown_pct'] * 100:.2f}%"
        b_cost = f"{b['cost_drag_pct'] * 100:.2f}%"
        b_v = f"`{b['gate_g0_verdict']}`"

        s_wr = f"{s['win_rate'] * 100:.2f}%"
        s_gross = f"{s['gross_expectancy_pct'] * 100:+.2f}%"
        s_net = f"{s['net_expectancy_pct'] * 100:+.2f}%"
        s_pf = f"{s['profit_factor']:.2f}"
        s_dd = f"{s['max_drawdown_pct'] * 100:.2f}%"
        s_cost = f"{s['cost_drag_pct'] * 100:.2f}%"
        s_v = f"**{s['gate_g0_verdict']}**"

        lines.append(f"| `{s_key}` | Baseline (All Day) | {b['trades']:,} | {b_wr} | {b_gross} | {b_net} | {b_pf} | {b_dd} | {b_cost} | {b_v} |")
        lines.append(f"| `{s_key}` | **Session (09:20-10:30 & 14:15-15:15)** | **{s['trades']:,}** | **{s_wr}** | **{s_gross}** | **{s_net}** | **{s_pf}** | **{s_dd}** | **{s_cost}** | {s_v} |")

    lines.append("")
    return "\n".join(lines)


def format_delta_summary_table(all_tf_data: list[dict[str, Any]]) -> str:
    """Generates an institutional executive summary table of filtering impact."""
    lines = []
    lines.append("### Session Conditioning Impact Summary (Deltas vs All-Day Baseline)")
    lines.append("")
    lines.append("| Timeframe | Strategy | Trade Filtered % | Net Exp Delta | PF Delta | Max DD Delta | Fee Drag Saved % |")
    lines.append("|:---:|:---|---:|---:|---:|---:|---:|")

    for tf_item in all_tf_data:
        tf = tf_item["timeframe"]
        for r in tf_item["results"]:
            d = r["deltas"]
            s_key = r["strategy_key"]
            tr_pct = f"-{d['trade_reduction_pct']:.1f}%" if d['trade_reduction_pct'] > 0 else f"{d['trade_reduction_pct']:.1f}%"
            net_d = f"{d['net_exp_delta_pct']:+.3f}%"
            pf_d = f"{d['pf_delta']:+.2f}"
            dd_d = f"{d['dd_delta_pct']:+.2f}%"
            drag_d = f"{d['cost_drag_reduction_pct']:+.3f}%"
            lines.append(f"| {tf} | `{s_key}` | {tr_pct} | {net_d} | {pf_d} | {dd_d} | {drag_d} |")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run SENSEX empirical session liquidity study.")
    parser.add_argument("--k_tp", type=float, default=2.5, help="Profit target multiplier")
    parser.add_argument("--k_sl", type=float, default=1.0, help="Stop loss multiplier")
    parser.add_argument("--t_max_bars", type=int, default=12, help="Max holding horizon bars")
    parser.add_argument("--trend_aligned", action="store_true", default=True, help="Trend filter alignment")
    parser.add_argument("--stress", type=float, default=1.0, help="Cost stress multiplier")
    args = parser.parse_args()

    dataset_path = find_sensex_dataset()

    # Findings here are reported as empirical market evidence. Refuse a fixture:
    # a session study computed on generated candles is a study of the generator.
    provenance = assert_real_dataset(dataset_path, label="SENSEX 1m session study")

    print("=" * 100)
    print(" DROID QUANTITATIVE RESEARCH: INSTITUTIONAL SESSION LIQUIDITY STUDY")
    print(f" Dataset: {dataset_path}")
    print(f" Provenance: source={provenance.source} sha256={(provenance.checksum_sha256 or '')[:12]}")
    print(f" Institutional Windows: {DEFAULT_SESSION_WINDOWS} IST")
    print(f" Parameters: k_tp={args.k_tp}, k_sl={args.k_sl}, t_max={args.t_max_bars}, trend_aligned={args.trend_aligned}, stress={args.stress}x")
    print("=" * 100 + "\n")

    df_1m = pl.read_parquet(dataset_path).sort("timestamp")
    print(f"Loaded 1m dataset: {len(df_1m):,} bars from {df_1m['timestamp'][0]} to {df_1m['timestamp'][-1]}\n")

    timeframes = ["1m", "5m", "15m"]
    study_results = []
    markdown_sections = []

    for tf in timeframes:
        print(f"[*] Running empirical backtests for {tf}...")
        tf_data = run_session_study_for_timeframe(
            df_1m=df_1m,
            timeframe=tf,
            k_tp=args.k_tp,
            k_sl=args.k_sl,
            t_max_bars=args.t_max_bars,
            trend_aligned=args.trend_aligned,
            stress_multiplier=args.stress,
        )
        study_results.append(tf_data)
        md_table = format_timeframe_markdown_table(tf_data)
        markdown_sections.append(md_table)
        print(f"    Completed {tf} comparative evaluation.")

    delta_table = format_delta_summary_table(study_results)
    markdown_sections.append(delta_table)

    full_markdown = "\n".join(markdown_sections)
    print("\n" + "=" * 100)
    print(" EMPIRICAL COMPARISON RESULTS (MARKDOWN)")
    print("=" * 100 + "\n")
    print(full_markdown)

    # Save results to JSON artifact
    output_json = BASE_DIR / "data" / "quant_session_study.json"
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "dataset": str(dataset_path),
            "parameters": {
                "k_tp": args.k_tp,
                "k_sl": args.k_sl,
                "t_max_bars": args.t_max_bars,
                "trend_aligned": args.trend_aligned,
                "stress_multiplier": args.stress,
                "allowed_windows": DEFAULT_SESSION_WINDOWS,
            },
            "study_results": study_results,
        }, f, indent=2)

    print(f"\n[+] Empirical study results saved to {output_json}")


if __name__ == "__main__":
    main()
