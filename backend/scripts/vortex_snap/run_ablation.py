"""
Run 9-Stage Component Ablation Study for VORTEX-SNAP (§32, §52).

Usage:
    python scripts/vortex_snap/run_ablation.py --instrument NIFTY --days 5 --synthetic
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.signals.strategies.vortex_snap.backtest.data_loader import HistoricalDataLoader
from app.signals.strategies.vortex_snap.backtest.ablation import ComponentAblationRunner
from app.signals.strategies.vortex_snap.backtest.report import ResearchReportGenerator


def main():
    parser = argparse.ArgumentParser(description="VORTEX-SNAP 9-Stage Component Ablation")
    parser.add_argument("--instrument", type=str, default="NIFTY", choices=["SENSEX", "NIFTY", "BANKNIFTY"])
    parser.add_argument("--synthetic", action="store_true", default=True, help="Generate synthetic market data")
    parser.add_argument("--days", type=int, default=5, help="Number of trading days")
    parser.add_argument("--output-dir", type=str, default="data/experiments", help="Output directory for reports")
    args = parser.parse_args()

    loader = HistoricalDataLoader()
    print(f"Preparing {args.days} sessions of market data for {args.instrument}...")

    all_candles = []
    base_date = datetime(2026, 9, 21, tzinfo=timezone.utc)
    curr_price = 24000.0 if args.instrument == "NIFTY" else (52000.0 if args.instrument == "BANKNIFTY" else 78000.0)

    for i in range(args.days):
        d = base_date + timedelta(days=i)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        day_candles = loader.generate_synthetic_session(
            date_obj=d,
            start_price=curr_price,
            drift=25.0 if i % 2 == 0 else -20.0,
            volatility=10.0,
            add_compression_and_breakout=True,
            seed=200 + i,
        )
        all_candles.extend(day_candles)
        curr_price = day_candles[-1].close

    contexts = loader.compute_session_levels(all_candles)
    print(f"Loaded {len(contexts):,} bar contexts. Running 9-stage controlled ablation study...")

    runner = ComponentAblationRunner()
    report = runner.run_study(contexts, instrument=args.instrument)

    print("\n" + "=" * 105)
    print(f"| {'Stage':<5} | {'Configuration':<32} | {'Trades':<6} | {'WinRate':<8} | {'Sharpe':<7} | {'MaxDD%':<7} | {'dSharpe':<9} | {'Marginal':<8} |")
    print("=" * 105)
    for s in report.stages:
        print(
            f"| {s.stage_letter:<5} | {s.config_name:<32} | {s.metrics.total_trades:<6} | "
            f"{s.metrics.win_rate_pct:>7.1f}% | {s.metrics.annualized_sharpe:>7.2f} | {s.metrics.max_drawdown_pct:>6.1f}% | "
            f"{s.delta_sharpe_vs_baseline:>+8.2f}  | {s.marginal_sharpe_gain:>+7.2f}  |"
        )
    print("-" * 105)
    verdict = "SUPPORTED" if report.primary_hypothesis_supported else "REJECTED"
    print(f"\nPRIMARY RESEARCH HYPOTHESIS (Translation Ratio): [{verdict}]")
    print(f"  dSharpe (Stage B -> C):   {report.primary_hypothesis_delta_sharpe:+.2f}")
    print(f"  dWin Rate (Stage B -> C): {report.primary_hypothesis_delta_win_rate:+.1f}%\n")


if __name__ == "__main__":
    main()
