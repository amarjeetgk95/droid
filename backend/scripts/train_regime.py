"""Train Regime Challenger Model.

Fits a regularized LightGBM classifier on the Feature V3 dataset and saves
the model artifact + JSON manifest to backend/app/ml/artifacts/challenger/.
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
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, log_loss

from app.ml.features.schema import FEATURE_NAMES_V3
from app.ml.models.regime_model import REGIME_CLASSES

ARTIFACTS_DIR = Path(__file__).parent.parent / "app" / "ml" / "artifacts"
CHALLENGER_DIR = ARTIFACTS_DIR / "challenger"
CHALLENGER_DIR.mkdir(parents=True, exist_ok=True)


def train_regime(dataset_path: str) -> None:
    print(f"Loading dataset: {dataset_path}")
    df = pd.read_parquet(dataset_path)

    # Synthetic / derived regime labels for bootstrap training
    # 0=TREND_UP, 1=TREND_DOWN, 2=RANGE, 3=HIGH_VOL, 4=LOW_VOL, 5=VOL_EXPANSION
    feature_cols = [f"f_{c}" for c in FEATURE_NAMES_V3]
    X = df[feature_cols].values

    # Determine regime labels
    labels = []
    for _, row in df.iterrows():
        adx = row.get("f_adx_14", 20.0)
        ema_align = row.get("f_ema_alignment_score", 0.0)
        vol_exp = row.get("f_vol_expansion_flag", 0.0)
        if vol_exp > 0.5:
            labels.append(5)  # VOL_EXPANSION
        elif adx >= 25.0 and ema_align > 0:
            labels.append(0)  # TREND_UP
        elif adx >= 25.0 and ema_align < 0:
            labels.append(1)  # TREND_DOWN
        elif adx < 18.0:
            labels.append(2)  # RANGE
        elif row.get("f_vix_level", 14.0) > 18.0:
            labels.append(3)  # HIGH_VOL
        else:
            labels.append(4)  # LOW_VOL

    y = np.array(labels)

    # Chronological train/val split (no shuffling to prevent leakage)
    split_idx = int(len(X) * 0.8)
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    print(f"Training LightGBM Regime classifier (n_train={len(X_train)}, n_val={len(X_val)})...")
    clf = lgb.LGBMClassifier(
        objective="multiclass",
        num_class=len(REGIME_CLASSES),
        max_depth=3,
        num_leaves=12,
        min_child_samples=20,
        learning_rate=0.05,
        n_estimators=60,
        random_state=42,
        verbosity=-1,
    )
    clf.fit(X_train, y_train)

    val_preds = clf.predict_proba(X_val)
    val_acc = accuracy_score(y_val, clf.predict(X_val))
    val_loss = log_loss(y_val, val_preds, labels=list(range(len(REGIME_CLASSES))))

    print(f"Validation Accuracy: {val_acc:.4f}, LogLoss: {val_loss:.4f}")

    # Save artifact and manifest
    model_path = CHALLENGER_DIR / "regime_model.joblib"
    meta_path = CHALLENGER_DIR / "regime_meta.json"

    joblib.dump(clf, model_path)

    meta = {
        "model_version": "regime_v1_challenger",
        "feature_schema": "f28-v3",
        "label_schema": "regime_6class_v1",
        "dataset_version": Path(dataset_path).stem,
        "n_train": len(X_train),
        "n_val": len(X_val),
        "validation_accuracy": round(float(val_acc), 4),
        "validation_log_loss": round(float(val_loss), 4),
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "classes": REGIME_CLASSES,
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"Challenger regime model saved to {model_path}")
    print(f"Manifest written to {meta_path}")


if __name__ == "__main__":
    default_dataset = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ml_datasets", "candidates_v3.parquet")
    train_regime(default_dataset)
