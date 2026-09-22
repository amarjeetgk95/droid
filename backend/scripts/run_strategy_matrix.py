"""Empirical Strategy Matrix Evaluation Runner across 1m, 5m, and 15m (Tier 0 Quant).

Executes strategy isolation (S1, S2, S3, S4, ALL) for SENSEX across:
- 1m: High-frequency micro-structure resolution
- 5m: Tactical intermediate intraday resolution
- 15m: Core quantitative regime baseline resolution

Saves empirical results into `data/quant_experiments.json` and prints
formatted Markdown comparison tables.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.quant.data.dataset_manager import DatasetManager
from app.quant.backtest.backtest_harness import BacktestHarness

STRATEGY_DESCRIPTIONS = {
    "S1": "Opening Range Breakout (ORB)",
    "S2": "1m Momentum Breakout",
    "S3": "VWAP Reclaim / Reject",
    "S4": "Volatility Compression Breakout (Experimental)",
    "ALL": "Portfolio Combination (S1+S2+S3+S4)",
}


def run_matrix_for_timeframe(
    symbol: str = "sensex",
    timeframe: str = "15m",
    k_tp: float = 2.5,
    k_sl: float = 1.0,
    t_max_bars: int = 12,
    trend_aligned: bool = True,
    stress_multiplier: float = 1.0,
) -> dict:
    """Runs strategy isolation matrix for a given symbol and timeframe."""
    dm = DatasetManager(base_dir=BASE_DIR / "data" / "raw")
    if not dm.exists(symbol, "1m"):
        raise FileNotFoundError(f"Base 1m dataset not found for symbol: {symbol}")

    df_raw, meta = dm.load_dataset(symbol, "1m")
    if timeframe != "1m":
        df = dm.resample_candles(df_raw, target_timeframe=timeframe)
    else:
        df = df_raw

    date_start = (meta.start_time.isoformat() if hasattr(meta.start_time, "isoformat") else str(meta.start_time)) if meta and meta.start_time else None
    date_end = (meta.end_time.isoformat() if hasattr(meta.end_time, "isoformat") else str(meta.end_time)) if meta and meta.end_time else None

    provenance = {
        "source_symbol": symbol.upper(),
        "source_timeframe": "1m",
        "source_bars": len(df_raw),
        "analysis_timeframe": timeframe,
        "analysis_bars": len(df),
        "date_start": date_start,
        "date_end": date_end,
        "data_quality_score": meta.data_quality_score if meta else 100.0,
    }

    matrix_rows = []
    lot_size = 10 if "sensex" in symbol.lower() else 25

    for strat_key in ["S1", "S2", "S3", "S4", "ALL"]:
        harness = BacktestHarness(
            lot_size=lot_size,
            t_max_bars=t_max_bars,
            k_tp=k_tp,
            k_sl=k_sl,
            trend_aligned=trend_aligned,
        )
        _, metrics = harness.run_backtest(
            df=df,
            strategy_key=strat_key,
            stress_multiplier=stress_multiplier,
        )
        matrix_rows.append({
            "strategy_key": strat_key,
            "strategy_name": STRATEGY_DESCRIPTIONS.get(strat_key, strat_key),
            "total_trades": metrics.total_trades,
            "win_rate": round(metrics.win_rate, 4),
            "gross_expectancy_pct": round(metrics.gross_expectancy_pct, 4),
            "net_expectancy_pct": round(metrics.net_expectancy_pct, 4),
            "profit_factor": round(metrics.profit_factor, 2),
            "max_drawdown_pct": round(metrics.max_drawdown_pct, 4),
            "annualized_sharpe": round(metrics.annualized_sharpe, 2),
            "deflated_sharpe_ratio": round(metrics.deflated_sharpe_ratio, 4),
            "gate_g0_verdict": metrics.gate_g0_verdict,
            "verdict_reasons": metrics.verdict_reasons,
        })

    return {
        "provenance": provenance,
        "matrix": matrix_rows,
    }


def format_markdown_table(timeframe: str, matrix_rows: list[dict], provenance: dict) -> str:
    """Formats matrix results as a clean Markdown table."""
    lines = []
    lines.append(f"### SENSEX Empirical Strategy Matrix - {timeframe} (Bars: {provenance['analysis_bars']:,})")
    lines.append("")
    lines.append("| Strategy Key | Strategy Name | Trades | Win Rate | Gross Exp % | Net Exp % | Profit Factor | Max DD % | Ann. Sharpe | DSR | Gate G0 Verdict |")
    lines.append("|:---|:---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|")

    for row in matrix_rows:
        wr_str = f"{row['win_rate'] * 100:.2f}%"
        gross_str = f"{row['gross_expectancy_pct'] * 100:+.2f}%"
        net_str = f"{row['net_expectancy_pct'] * 100:+.2f}%"
        pf_str = f"{row['profit_factor']:.2f}"
        dd_str = f"{row['max_drawdown_pct'] * 100:.2f}%"
        sr_str = f"{row['annualized_sharpe']:.2f}"
        dsr_str = f"{row['deflated_sharpe_ratio']:.2f}"
        verdict = f"**{row['gate_g0_verdict']}**"
        lines.append(
            f"| `{row['strategy_key']}` | {row['strategy_name']} | {row['total_trades']:,} | {wr_str} | {gross_str} | {net_str} | {pf_str} | {dd_str} | {sr_str} | {dsr_str} | {verdict} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_all_timeframes():
    timeframes = ["1m", "5m", "15m"]
    symbol = "sensex"
    k_tp = 2.5
    k_sl = 1.0
    t_max_bars = 12
    trend_aligned = True
    stress_multiplier = 1.0

    print("=" * 100)
    print(" DROID QUANTITATIVE ENGINE: EMPIRICAL MULTI-TIMEFRAME STRATEGY MATRIX")
    print(f" Symbol: {symbol.upper()} | Timeframes: {', '.join(timeframes)}")
    print(f" Parameters: k_tp={k_tp}, k_sl={k_sl}, t_max_bars={t_max_bars}, trend_aligned={trend_aligned}, stress={stress_multiplier}x")
    print("=" * 100 + "\n")

    results_by_tf = {}
    markdown_tables = []

    for tf in timeframes:
        print(f"[*] Computing strategy isolation matrix for {tf}...")
        result = run_matrix_for_timeframe(
            symbol=symbol,
            timeframe=tf,
            k_tp=k_tp,
            k_sl=k_sl,
            t_max_bars=t_max_bars,
            trend_aligned=trend_aligned,
            stress_multiplier=stress_multiplier,
        )
        results_by_tf[tf] = result
        md_table = format_markdown_table(tf, result["matrix"], result["provenance"])
        markdown_tables.append(md_table)
        print(f"    Completed {tf}: {len(result['matrix'])} strategy rows generated.")

    # Save to data/quant_experiments.json
    output_path = BASE_DIR / "data" / "quant_experiments.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    experiment_data = {
        "experiment_id": "empirical_strategy_matrix_sensex_multitimeframe",
        "symbol": symbol.upper(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "k_tp": k_tp,
            "k_sl": k_sl,
            "t_max_bars": t_max_bars,
            "trend_aligned": trend_aligned,
            "stress_multiplier": stress_multiplier,
        },
        "timeframes": timeframes,
        "results": results_by_tf,
        "1m": results_by_tf.get("1m"),
        "5m": results_by_tf.get("5m"),
        "15m": results_by_tf.get("15m"),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(experiment_data, f, indent=2)

    print(f"\n[+] Empirical results saved successfully to: {output_path}\n")

    # Print formatted Markdown tables
    print("=" * 100)
    print(" EMPIRICAL COMPARISON TABLES (MARKDOWN)")
    print("=" * 100 + "\n")
    for md in markdown_tables:
        print(md)

    # Print cross-timeframe ALL portfolio comparison
    print("### Cross-Timeframe Portfolio Combination (ALL) Comparison\n")
    print("| Timeframe | Source Bars | Analysis Bars | Total Trades | Win Rate | Gross Exp % | Net Exp % | Profit Factor | Max DD % | Ann. Sharpe | DSR | G0 Verdict |")
    print("|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|")
    for tf in timeframes:
        res = results_by_tf[tf]
        prov = res["provenance"]
        all_row = next(r for r in res["matrix"] if r["strategy_key"] == "ALL")
        print(
            f"| `{tf}` | {prov['source_bars']:,} | {prov['analysis_bars']:,} | {all_row['total_trades']:,} | "
            f"{all_row['win_rate']*100:.2f}% | {all_row['gross_expectancy_pct']*100:+.2f}% | {all_row['net_expectancy_pct']*100:+.2f}% | "
            f"{all_row['profit_factor']:.2f} | {all_row['max_drawdown_pct']*100:.2f}% | {all_row['annualized_sharpe']:.2f} | "
            f"{all_row['deflated_sharpe_ratio']:.2f} | **{all_row['gate_g0_verdict']}** |"
        )
    print("\n" + "=" * 100)


if __name__ == "__main__":
    run_all_timeframes()
