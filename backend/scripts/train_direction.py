"""Train Direction Challenger Model.

Fits a regularized LightGBM classifier on the Feature V3 dataset for horizon H=15m
and saves the artifact + JSON manifest to backend/app/ml/artifacts/challenger/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, log_loss

from app.ml.features.schema import FEATURE_NAMES_V3

ARTIFACTS_DIR = Path(__file__).parent.parent / "app" / "ml" / "artifacts"
CHALLENGER_DIR = ARTIFACTS_DIR / "challenger"
CHALLENGER_DIR.mkdir(parents=True, exist_ok=True)

DIRECTIONS = ["BEARISH", "NEUTRAL", "BULLISH"]


def train_direction(dataset_path: str, horizon_minutes: int = 15) -> None:
    print(f"Loading dataset: {dataset_path} for H={horizon_minutes}m")
    df = pd.read_parquet(dataset_path)

    feature_cols = [f"f_{c}" for c in FEATURE_NAMES_V3]
    X = df[feature_cols].values
    y = df["label_direction_15m"].values

    # Chronological train/val split (80/20)
    split_idx = int(len(X) * 0.8)
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    print(f"Training LightGBM Direction classifier (n_train={len(X_train)}, n_val={len(X_val)})...")
    clf = lgb.LGBMClassifier(
        objective="multiclass",
        num_class=3,
        max_depth=3,
        num_leaves=12,
        min_child_samples=25,
        learning_rate=0.04,
        n_estimators=80,
        random_state=42,
        verbosity=-1,
    )
    clf.fit(X_train, y_train)

    val_preds = clf.predict_proba(X_val)
    val_acc = accuracy_score(y_val, clf.predict(X_val))
    val_loss = log_loss(y_val, val_preds, labels=[0, 1, 2])

    print(f"Validation Accuracy: {val_acc:.4f}, LogLoss: {val_loss:.4f}")

    # Multi-class Brier score
    y_val_onehot = np.zeros_like(val_preds)
    for i, label in enumerate(y_val):
        y_val_onehot[i, label] = 1.0
    brier = float(np.mean(np.sum((val_preds - y_val_onehot) ** 2, axis=1)))
    print(f"Validation Brier Score: {brier:.4f}")

    prefix = f"direction_h{horizon_minutes}"
    model_path = CHALLENGER_DIR / f"{prefix}_lgb.joblib"
    meta_path = CHALLENGER_DIR / f"{prefix}_meta.json"

    joblib.dump(clf, model_path)

    meta = {
        "model_version": f"direction_h{horizon_minutes}_v1_challenger",
        "horizon_minutes": horizon_minutes,
        "feature_schema": "f28-v3",
        "label_schema": "direction_3class_15m",
        "dataset_version": Path(dataset_path).stem,
        "n_train": len(X_train),
        "n_val": len(X_val),
        "validation_accuracy": round(float(val_acc), 4),
        "validation_log_loss": round(float(val_loss), 4),
        "validation_brier_score": round(brier, 4),
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "classes": DIRECTIONS,
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"Challenger direction model saved to {model_path}")
    print(f"Manifest written to {meta_path}")


if __name__ == "__main__":
    default_dataset = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ml_datasets", "candidates_v3.parquet")
    train_direction(default_dataset, horizon_minutes=15)
