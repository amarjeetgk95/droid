"""
Run Rolling Walk-Forward Validator for VORTEX-SNAP (§31).

Usage:
    python scripts/vortex_snap/run_walkforward.py --instrument NIFTY --days 6 --folds 3 --synthetic
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.signals.strategies.vortex_snap.backtest.data_loader import HistoricalDataLoader
from app.signals.strategies.vortex_snap.backtest.walk_forward import RollingWalkForwardValidator


def main():
    parser = argparse.ArgumentParser(description="VORTEX-SNAP Rolling Walk-Forward Validator")
    parser.add_argument("--instrument", type=str, default="NIFTY", choices=["SENSEX", "NIFTY", "BANKNIFTY"])
    parser.add_argument("--days", type=int, default=6, help="Number of trading days (minimum 5)")
    parser.add_argument("--folds", type=int, default=3, help="Number of rolling folds")
    parser.add_argument("--synthetic", action="store_true", default=True, help="Generate synthetic market data")
    args = parser.parse_args()

    loader = HistoricalDataLoader()
    print(f"Generating {args.days} sessions of market data for {args.instrument}...")

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
            drift=20.0 if i % 2 == 0 else -15.0,
            volatility=9.0,
            add_compression_and_breakout=True,
            seed=300 + i,
        )
        all_candles.extend(day_candles)
        curr_price = day_candles[-1].close

    contexts = loader.compute_session_levels(all_candles)
    print(f"Loaded {len(contexts):,} bar contexts. Running rolling walk-forward validation ({args.folds} folds)...")

    validator = RollingWalkForwardValidator(n_folds=args.folds, embargo_bars=60)
    summary = validator.evaluate(contexts, instrument=args.instrument)

    print("\n" + "=" * 90)
    print(f"| {'Fold':<5} | {'Train Bars':<11} | {'Val Bars':<9} | {'Test Bars':<10} | {'IS Sharpe':<10} | {'OOS Sharpe':<11} | {'WFE':<6} | {'Overfit?':<8} |")
    print("=" * 90)
    for f in summary.folds:
        flag = "YES" if f.is_overfit_suspected else "NO"
        print(
            f"| {f.fold_index:<5} | {f.train_bars_count:<11} | {f.val_bars_count:<9} | {f.test_bars_count:<10} | "
            f"{f.train_metrics.annualized_sharpe:>9.2f}  | {f.test_metrics.annualized_sharpe:>10.2f}  | {f.walk_forward_efficiency:>5.2f} | {flag:<8} |"
        )
    print("-" * 90)
    print(f"Aggregate Walk-Forward Efficiency (WFE): {summary.mean_wfe:.2f}")
    print(f"Mean In-Sample Sharpe:                 {summary.mean_is_sharpe:.2f}")
    print(f"Mean Out-Of-Sample Sharpe:             {summary.mean_oos_sharpe:.2f}")
    print(f"Mean Out-Of-Sample Win Rate:           {summary.mean_oos_win_rate:.1f}%\n")


if __name__ == "__main__":
    main()
