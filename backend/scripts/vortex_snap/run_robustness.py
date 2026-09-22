"""
Run Robustness & Stress Battery for VORTEX-SNAP (§33, §52).

Usage:
    python scripts/vortex_snap/run_robustness.py --instrument NIFTY --days 5 --synthetic
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.signals.strategies.vortex_snap.backtest.data_loader import HistoricalDataLoader
from app.signals.strategies.vortex_snap.backtest.robustness import RobustnessTester


def main():
    parser = argparse.ArgumentParser(description="VORTEX-SNAP Robustness & Stress Battery")
    parser.add_argument("--instrument", type=str, default="NIFTY", choices=["SENSEX", "NIFTY", "BANKNIFTY"])
    parser.add_argument("--days", type=int, default=5, help="Number of trading days")
    parser.add_argument("--synthetic", action="store_true", default=True, help="Generate synthetic market data")
    parser.add_argument("--mc-iterations", type=int, default=1000, help="Monte Carlo permutation iterations")
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
            drift=25.0 if i % 2 == 0 else -20.0,
            volatility=10.0,
            add_compression_and_breakout=True,
            seed=400 + i,
        )
        all_candles.extend(day_candles)
        curr_price = day_candles[-1].close

    contexts = loader.compute_session_levels(all_candles)
    print(f"Loaded {len(contexts):,} bar contexts. Running robustness stress battery...")

    tester = RobustnessTester()
    report = tester.run_all(contexts, instrument=args.instrument, mc_iterations=args.mc_iterations)

    print("\n" + "=" * 70)
    print("1. TRANSACTION COST FRICTION STRESS TESTING")
    print("=" * 70)
    print(f"| {'Multiplier':<12} | {'Net PnL (INR)':<15} | {'Profit Factor':<15} | {'Sharpe':<8} | {'Profitable?':<12} |")
    print("-" * 70)
    for c in report.cost_stress:
        p_str = "YES" if c.is_profitable else "NO"
        print(f"| {c.multiplier:<12.1f} | {c.net_pnl:>15,.2f} | {c.profit_factor:>15.2f} | {c.annualized_sharpe:>8.2f} | {p_str:<12} |")

    print("\n" + "=" * 70)
    print("2. EXECUTION LATENCY LAG STRESS")
    print("=" * 70)
    print(f"| {'Lag Bars':<12} | {'Net PnL (INR)':<15} | {'Win Rate %':<15} | {'Sharpe':<8} |")
    print("-" * 70)
    for l in report.latency_stress:
        print(f"| {l.lag_bars:<12} | {l.net_pnl:>15,.2f} | {l.win_rate_pct:>14.1f}% | {l.annualized_sharpe:>8.2f} |")

    print("\n" + "=" * 70)
    print(f"3. MONTE CARLO PERMUTATION ANALYSIS ({args.mc_iterations:,} RUNS)")
    print("=" * 70)
    print(f"P05 Max Drawdown:         {report.monte_carlo.p05_max_dd_pct:.1f}%")
    print(f"Median (P50) Max Drawdown:{report.monte_carlo.p50_max_dd_pct:.1f}%")
    print(f"P95 Max Drawdown:         {report.monte_carlo.p95_max_dd_pct:.1f}%")
    print(f"Probability of Ruin (>25%):{report.monte_carlo.probability_of_ruin_pct:.1f}%")

    print("\n" + "=" * 70)
    verdict = "FRAGILE" if report.is_fragile else "ROBUST"
    print(f"OVERALL SYSTEM RESILIENCE VERDICT: [{verdict}]")
    if report.fragility_reasons:
        for r in report.fragility_reasons:
            print(f"  * {r}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
