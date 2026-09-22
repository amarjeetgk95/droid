"""
Run Baseline Backtest Experiment for VORTEX-SNAP (§52).

Usage:
    python scripts/vortex_snap/run_experiment.py --instrument SENSEX --days 10
    python scripts/vortex_snap/run_experiment.py --instrument NIFTY --synthetic --days 5
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add backend directory to path
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.signals.strategies.vortex_snap.backtest.data_loader import HistoricalDataLoader
from app.signals.strategies.vortex_snap.backtest.engine import VortexBacktestEngine
from app.signals.strategies.vortex_snap.backtest.report import ResearchReportGenerator


def main():
    parser = argparse.ArgumentParser(description="VORTEX-SNAP Quantitative Backtest Experiment")
    parser.add_argument("--instrument", type=str, default="SENSEX", choices=["SENSEX", "NIFTY", "BANKNIFTY"])
    parser.add_argument("--synthetic", action="store_true", help="Generate synthetic market data")
    parser.add_argument("--days", type=int, default=5, help="Number of trading days")
    parser.add_argument("--capital", type=float, default=500000.0, help="Initial capital in INR")
    parser.add_argument("--output-dir", type=str, default="data/experiments", help="Output directory for reports")
    args = parser.parse_args()

    loader = HistoricalDataLoader()
    contexts = []

    if not args.synthetic:
        try:
            print(f"Loading historical parquet dataset for {args.instrument}...")
            candles = loader.load_parquet(args.instrument)
            print(f"Loaded {len(candles):,} 1m candles. Computing session levels...")
            # If days specified, slice last N days (375 bars per day)
            max_bars = args.days * 375
            if len(candles) > max_bars:
                candles = candles[-max_bars:]
            contexts = loader.compute_session_levels(candles)
        except Exception as e:
            print(f"Parquet load failed ({e}). Falling back to synthetic market generation...")
            args.synthetic = True

    if args.synthetic:
        print(f"Generating {args.days} synthetic trading sessions for {args.instrument}...")
        all_candles = []
        base_date = datetime(2026, 9, 21, tzinfo=timezone.utc)
        curr_price = 24000.0 if args.instrument == "NIFTY" else (52000.0 if args.instrument == "BANKNIFTY" else 78000.0)

        for i in range(args.days):
            d = base_date + timedelta(days=i)
            # Skip weekends
            while d.weekday() >= 5:
                d += timedelta(days=1)
            day_candles = loader.generate_synthetic_session(
                date_obj=d,
                start_price=curr_price,
                drift=25.0 if i % 2 == 0 else -20.0,
                volatility=10.0,
                add_compression_and_breakout=True,
                seed=100 + i,
            )
            all_candles.extend(day_candles)
            curr_price = day_candles[-1].close

        contexts = loader.compute_session_levels(all_candles)

    print(f"Total bar contexts prepared: {len(contexts):,}. Running event-driven simulation...")
    engine = VortexBacktestEngine(initial_capital=args.capital)
    metrics = engine.run(contexts, instrument=args.instrument)

    reporter = ResearchReportGenerator(output_dir=args.output_dir)
    md_path, json_path = reporter.save_report(
        instrument=args.instrument,
        baseline=metrics,
        filename_prefix="experiment",
    )

    print("=" * 80)
    print(f"VORTEX-SNAP BACKTEST SUMMARY: {args.instrument}")
    print("=" * 80)
    print(f"Total Trades:        {metrics.total_trades}")
    print(f"Win Rate:            {metrics.win_rate_pct:.1f}% ({metrics.winning_trades} wins / {metrics.losing_trades} losses)")
    print(f"Gross PnL:           INR {metrics.gross_pnl_rupees:,.2f}")
    print(f"Net PnL:             INR {metrics.net_pnl_rupees:,.2f}")
    print(f"Friction (Taxes/Slip):INR {metrics.total_friction_rupees:,.2f} (Drag: {metrics.cost_drag_pct:.1f}%)")
    print(f"Profit Factor:       {metrics.profit_factor:.2f}")
    print(f"Annualized Sharpe:   {metrics.annualized_sharpe:.2f}")
    print(f"Max Drawdown:        {metrics.max_drawdown_pct:.1f}% (INR {metrics.max_drawdown_rupees:,.2f})")
    print(f"Calmar Ratio:        {metrics.calmar_ratio:.2f}")
    print(f"Avg Holding Time:    {metrics.avg_holding_minutes:.1f} minutes")
    print("-" * 80)
    print(f"Markdown Report:     {md_path}")
    print(f"JSON Report:         {json_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
