"""
Train and Calibrate VORTEX-SNAP Machine Learning Validator (§25-§27).

Usage:
    python scripts/vortex_snap/train_ml_validator.py --instrument NIFTY --days 10 --synthetic
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.signals.strategies.vortex_snap.backtest.data_loader import HistoricalDataLoader
from app.signals.strategies.vortex_snap.ml.trainer import VortexMLTrainer


def main():
    parser = argparse.ArgumentParser(description="VORTEX-SNAP ML Validator Training")
    parser.add_argument("--instrument", type=str, default="NIFTY", choices=["SENSEX", "NIFTY", "BANKNIFTY"])
    parser.add_argument("--days", type=int, default=10, help="Number of trading days for training data")
    parser.add_argument("--synthetic", action="store_true", default=True, help="Generate synthetic market data")
    parser.add_argument("--artifact-path", type=str, default="artifacts/vortex_snap_ml_validator.joblib", help="Model save path")
    args = parser.parse_args()

    loader = HistoricalDataLoader()
    print(f"Loading {args.days} sessions for {args.instrument}...")

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
            drift=30.0 if i % 2 == 0 else -25.0,
            volatility=11.0,
            add_compression_and_breakout=True,
            seed=500 + i,
        )
        all_candles.extend(day_candles)
        curr_price = day_candles[-1].close

    contexts = loader.compute_session_levels(all_candles)
    print(f"Loaded {len(contexts):,} bar contexts. Extracting candidates and forward outcomes...")

    trainer = VortexMLTrainer(forward_bars_window=15)
    dataset = trainer.build_dataset_from_contexts(contexts, instrument=args.instrument)
    print(f"Generated {len(dataset.X):,} training samples. Class balance: {float(np.mean(dataset.y)):.1%} positive.")

    print("Training LightGBM classifier and fitting Platt probability calibrator...")
    model, calibrator, report = trainer.train_and_calibrate(dataset)

    saved_path = trainer.save_model_artifact(model, calibrator, report, artifact_path=args.artifact_path)
    print(f"\nModel artifact saved to: {saved_path}")

    print("\n" + "=" * 60)
    print("VORTEX-SNAP ML VALIDATOR EVALUATION")
    print("=" * 60)
    print(f"Test Set Samples:       {report.test_samples}")
    print(f"ROC-AUC:                {report.roc_auc:.3f}")
    print(f"Accuracy:               {report.accuracy:.1%}")
    print(f"Brier Score (Calib):    {report.calibration_diagnostics.brier_score_calibrated:.4f}")
    print(f"Expected Calib Error:   {report.calibration_diagnostics.expected_calibration_error:.4f}")
    print("-" * 60)
    print("TOP 5 PREDICTIVE MICROSTRUCTURE DRIVERS:")
    for rank, (feat, imp) in enumerate(list(sorted(report.feature_importances.items(), key=lambda x: x[1], reverse=True))[:5], 1):
        print(f"  {rank}. {feat:<30} (importance: {imp:.4f})")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    import numpy as np
    main()
