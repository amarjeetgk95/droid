import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import polars as pl
from app.quant.data.dataset_manager import DatasetManager
from app.quant.backtest.backtest_harness import BacktestHarness

def main():
    dm = DatasetManager()
    df_1m, meta = dm.load_dataset("sensex", "1m")
    df_5m = dm.resample_candles(df_1m, "5m")
    df_15m = dm.resample_candles(df_1m, "15m")

    timeframes = [("1m", df_1m), ("5m", df_5m), ("15m", df_15m)]
    strats = ["S1", "S2", "S3", "S4", "S5"]

    print("=" * 105)
    print(f"| {'TF':<4} | {'Strat':<5} | {'Trades':<7} | {'WinRate':<8} | {'ProfitFactor':<12} | {'GrossExp%':<11} | {'NetExp%':<11} | {'CostDrag%':<10} | {'MaxDD%':<8} |")
    print("=" * 105)

    for tf_name, df in timeframes:
        harness = BacktestHarness()
        for strat in strats:
            trades, metrics = harness.run_backtest(df, strategy_key=strat)
            print(
                f"| {tf_name:<4} | {strat:<5} | {metrics.total_trades:<7} | "
                f"{metrics.win_rate*100:>7.2f}% | {metrics.profit_factor:>12.2f} | "
                f"{metrics.gross_expectancy_pct*100:>10.3f}% | {metrics.net_expectancy_pct*100:>10.3f}% | "
                f"{metrics.cost_drag_pct*100:>9.3f}% | {metrics.max_drawdown_pct*100:>7.2f}% |"
            )
        print("-" * 105)

if __name__ == "__main__":
    main()
