"""CLI Runner for Gate G1: Orthogonal ML Ablation & Disjoint Calibration.

Usage:
  python scripts/run_g1_ablation.py --timeframe 5m --strategy ALL --threshold 0.52
"""

import argparse
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.quant.data.dataset_manager import DatasetManager
from app.quant.validation.gate_g1_evaluator import GateG1Evaluator


def main():
    parser = argparse.ArgumentParser(description="Run Gate G1 Orthogonal ML Ablation Study")
    parser.add_argument("--symbol", type=str, default="sensex", help="Underlying asset symbol")
    parser.add_argument("--timeframe", type=str, default="5m", choices=["1m", "5m", "15m"], help="Candle resolution")
    parser.add_argument("--strategy", type=str, default="ALL", choices=["S1", "S2", "S3", "ALL"], help="Strategy set")
    parser.add_argument("--folds", type=int, default=5, help="Number of Purged WFO folds")
    parser.add_argument("--threshold", type=float, default=0.52, help="Probability qualification threshold")
    parser.add_argument("--max-disagreement", type=float, default=0.35, help="Max disagreement threshold")
    args = parser.parse_args()

    print(f"\n================================================================================")
    print(f"             DROID TIER 1: GATE G1 ORTHOGONAL ML ABLATION EVALUATION")
    print(f"================================================================================")
    print(f" Asset:               BSE:{args.symbol.upper()}-INDEX")
    print(f" Timeframe:           {args.timeframe}")
    print(f" Strategies:          {args.strategy}")
    print(f" Walk-Forward Folds:  {args.folds}")
    print(f" Threshold / Max Dis: {args.threshold} / {args.max_disagreement}")
    print(f"--------------------------------------------------------------------------------\n")

    dm = DatasetManager()
    df_raw, meta = dm.load_dataset(args.symbol, "1m")
    print(f"[*] Loaded base 1m dataset: {len(df_raw):,} bars ({meta.start_time[:10]} to {meta.end_time[:10]})")

    if args.timeframe != "1m":
        rule = "5m" if args.timeframe == "5m" else "15m"
        df = dm.resample_candles(df_raw, target_timeframe=rule)
        print(f"[*] Resampled to {args.timeframe}: {len(df):,} bars")
    else:
        df = df_raw

    evaluator = GateG1Evaluator(
        n_folds=args.folds,
        confidence_threshold=args.threshold,
        max_disagreement=args.max_disagreement,
    )

    print(f"[*] Running Purged & Embargoed Walk-Forward Ablation across 5 Arms...")
    report = evaluator.evaluate(df, strategy_key=args.strategy, trend_aligned=True)

    print(f"\n================================================================================")
    print(f"                        ABLATION STUDY RESULTS (5 ARMS)")
    print(f"================================================================================")
    header = f"| {'Arm Name':<30} | {'Trades':>6} | {'Win %':>7} | {'Gross %':>8} | {'Net %':>8} | {'PF':>6} | {'MaxDD %':>7} | {'DSR':>6} |"
    sep = f"|{'-'*32}|{'-'*8}|{'-'*9}|{'-'*10}|{'-'*10}|{'-'*8}|{'-'*9}|{'-'*8}|"
    print(header)
    print(sep)

    for arm_key, res in report.arms.items():
        row = (
            f"| {res.arm_name:<30} | "
            f"{res.total_trades:>6} | "
            f"{res.win_rate*100:>6.1f}% | "
            f"{res.gross_expectancy_pct*100:>7.3f}% | "
            f"{res.net_expectancy_pct*100:>7.3f}% | "
            f"{res.profit_factor:>6.2f} | "
            f"{res.max_drawdown_pct*100:>6.1f}% | "
            f"{res.deflated_sharpe_ratio:>6.3f} |"
        )
        print(row)
    print(sep)

    print(f"\n================================================================================")
    print(f"               MODEL DIVERSITY & DISAGREEMENT TELEMETRY")
    print(f"================================================================================")
    print(f" Feature-View Correlation (A vs B):   {report.model_correlation:.4f}  (Target: < 0.85)")
    print(f" Mean Out-of-Sample Disagreement:     {report.mean_disagreement:.4f}")
    print(f" Disagreement-Triggered Rejections:   {report.disagreement_rejections} ({report.disagreement_rejection_pct:.1f}% of evaluations)")

    print(f"\n================================================================================")
    print(f"                       GATE G1 VERDICT: {report.gate_g1_verdict}")
    print(f"================================================================================")
    for r in report.verdict_reasons:
        print(f" - {r}")
    print(f"================================================================================\n")


if __name__ == "__main__":
    main()
