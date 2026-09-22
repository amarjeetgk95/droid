"""CLI Script to Execute Gate G0 Baseline Falsification Evaluation (Tier 0).

Executes:
1. Historical dataset ingestion/loading (with optional timeframe resampling, e.g. 5m)
2. Purged & embargoed walk-forward backtesting across S1, S2, S3, and Random Baseline R
3. Cost stress testing (1.0x, 1.25x, 1.5x, 2.0x)
4. Formal Gate G0 Go / No-Go verdict
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.quant.data.dataset_manager import DatasetManager
from app.quant.backtest.backtest_harness import BacktestHarness
from scripts.fetch_fyers_history import download_history


def run_g0(
    instrument: str = "sensex",
    timeframe: str = "1m",
    resample: str = None,
    days: int = 30,
    k_tp: float = 2.0,
    k_sl: float = 1.0,
    trend_aligned: bool = False,
    t_max: int = 15,
):
    print("=" * 80)
    print(f" DROID TIER 0 — GATE G0 BASELINE FALSIFICATION EVALUATION")
    tf_display = f"{resample} (resampled from {timeframe})" if resample else timeframe
    print(f" Target: {instrument.upper()} {tf_display} | R:R = {k_tp}:{k_sl} | Trend Aligned: {trend_aligned}")
    print("=" * 80)

    mgr = DatasetManager()
    if not mgr.exists(instrument, timeframe):
        print(f"Dataset not found locally. Initiating download for {instrument}...")
        sym = "BSE:SENSEX-INDEX" if "sensex" in instrument.lower() else "NSE:NIFTY50-INDEX"
        import asyncio
        df = asyncio.run(download_history(symbol=sym, days=days))
    else:
        df, meta = mgr.load_dataset(instrument, timeframe)
        print(f"Loaded base dataset from local Parquet: {len(df)} bars ({meta.start_time} to {meta.end_time})")

    # Resample if requested
    if resample and resample != timeframe:
        print(f"Resampling {len(df)} {timeframe} bars to {resample} bars...")
        df = DatasetManager.resample_candles(df, target_timeframe=resample)
        print(f"Resampled dataset: {len(df)} {resample} bars.")

    harness = BacktestHarness(
        lot_size=10 if "sensex" in instrument.lower() else 25,
        t_max_bars=t_max,
        k_tp=k_tp,
        k_sl=k_sl,
        trend_aligned=trend_aligned,
    )

    strategies = ["S1", "S2", "S3", "R"]
    stress_levels = [1.0, 1.25, 1.5, 2.0]

    print("\n" + "-" * 80)
    print(f"{'Strategy':<8} | {'Stress':<6} | {'Trades':<6} | {'Win Rate':<8} | {'PF':<6} | {'Net Exp %':<10} | {'Max DD %':<8} | {'DSR':<6} | {'G0 Verdict':<8}")
    print("-" * 80)

    results = {}
    for strat in strategies:
        strat_results = []
        for stress in stress_levels:
            trades, metrics = harness.run_backtest(df, strategy_key=strat, stress_multiplier=stress)
            strat_results.append((stress, metrics))

            print(
                f"{strat:<8} | "
                f"{stress}x{'':<3} | "
                f"{metrics.total_trades:<6} | "
                f"{metrics.win_rate*100:6.1f}% | "
                f"{metrics.profit_factor:6.2f} | "
                f"{metrics.net_expectancy_pct*100:8.3f}% | "
                f"{metrics.max_drawdown_pct*100:6.1f}% | "
                f"{metrics.deflated_sharpe_ratio:6.2f} | "
                f"{metrics.gate_g0_verdict:<8}"
            )
        results[strat] = strat_results

    print("-" * 80)

    # Summary Evaluation
    print("\n=== GATE G0 FALSIFICATION SUMMARY ===")
    g0_passed = False
    for strat, res_list in results.items():
        base_stress, base_metrics = res_list[0]
        stress_1_5x, stress_1_5_metrics = res_list[2]
        
        if strat == "R":
            print(f"Random Baseline R: Net Expectancy = {base_metrics.net_expectancy_pct*100:.3f}% (Reference control)")
            continue

        if base_metrics.gate_g0_verdict == "PASSED":
            print(f"[PASS] Strategy {strat}: Positive net expectancy ({base_metrics.net_expectancy_pct*100:.3f}%) and PF {base_metrics.profit_factor:.2f} at 1.0x.")
            if stress_1_5_metrics.net_expectancy_pct > 0:
                print(f"       Survived 1.5x cost stress! (Net Exp = {stress_1_5_metrics.net_expectancy_pct*100:.3f}%)")
                g0_passed = True
            else:
                print(f"       Killed by 1.5x cost stress. Breakeven multiplier < 1.5x.")
        else:
            reasons = "; ".join(base_metrics.verdict_reasons)
            print(f"[FAIL] Strategy {strat}: {reasons}")

    print("=" * 80)
    if g0_passed:
        print("GATE G0 VERDICT: PASSED -> Tier 1 (ML Validation) is unlocked.")
    else:
        print("GATE G0 VERDICT: FAILED -> Base edge not proven. Strategy core requires revision before ML.")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--instrument", default="sensex")
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--resample", default=None, help="Resample to higher timeframe e.g. 5m")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--k-tp", type=float, default=2.0, help="Reward-to-risk multiplier (default: 2.0)")
    parser.add_argument("--k-sl", type=float, default=1.0, help="Stop loss multiplier (default: 1.0)")
    parser.add_argument("--trend-aligned", action="store_true", help="Enable trend and regime pre-gating")
    parser.add_argument("--t-max", type=int, default=12, help="Maximum bars held")
    args = parser.parse_args()

    run_g0(
        instrument=args.instrument,
        timeframe=args.timeframe,
        resample=args.resample,
        days=args.days,
        k_tp=args.k_tp,
        k_sl=args.k_sl,
        trend_aligned=args.trend_aligned,
        t_max=args.t_max,
    )
