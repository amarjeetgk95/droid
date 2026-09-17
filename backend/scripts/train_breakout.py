"""Train Breakout Continuation Challenger Model.

Implements Section 12 of the DROID ML Specification.
Fits a regularized LightGBM classifier on the Feature V3 dataset to distinguish
between valid momentum breakouts and false breakout traps.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, log_loss, roc_auc_score

from app.ml.features.schema import FEATURE_NAMES_V3
from app.ml.validation.purged_cv import PurgedWalkForwardCV

ARTIFACTS_DIR = Path(__file__).parent.parent / "app" / "ml" / "artifacts"
CHALLENGER_DIR = ARTIFACTS_DIR / "challenger"
CHALLENGER_DIR.mkdir(parents=True, exist_ok=True)


def train_breakout(dataset_path: str) -> None:
    print(f"Loading dataset: {dataset_path} for Breakout Validation...")
    df = pd.read_parquet(dataset_path)

    feature_cols = [f"f_{c}" for c in FEATURE_NAMES_V3]
    X = df[feature_cols].values

    # Binary label: 1 = Valid follow-through breakout (MFE >= 1.0R), 0 = False trap
    y = np.where(df["mfe_r"] >= 1.0, 1, 0)

    cv = PurgedWalkForwardCV(n_splits=3, purge_bars=45)
    val_scores = []

    for fold_idx, (train_idx, val_idx) in enumerate(cv.split(X)):
        X_tr, y_tr = X[train_idx], y[train_idx]
        X_v, y_v = X[val_idx], y[val_idx]

        clf = lgb.LGBMClassifier(
            objective="binary",
            max_depth=3,
            num_leaves=12,
            min_child_samples=20,
            learning_rate=0.04,
            n_estimators=70,
            random_state=42,
            verbosity=-1,
        )
        clf.fit(X_tr, y_tr)
        preds = clf.predict_proba(X_v)[:, 1]
        acc = accuracy_score(y_v, clf.predict(X_v))
        val_scores.append(acc)

    print(f"Purged Walk-Forward Fold Accuracies: {val_scores}")

    # Final fit on full chronological train split
    split_idx = int(len(X) * 0.8)
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    final_clf = lgb.LGBMClassifier(
        objective="binary",
        max_depth=3,
        num_leaves=12,
        min_child_samples=20,
        learning_rate=0.04,
        n_estimators=70,
        random_state=42,
        verbosity=-1,
    )
    final_clf.fit(X_train, y_train)

    val_prob = final_clf.predict_proba(X_val)[:, 1]
    val_acc = accuracy_score(y_val, final_clf.predict(X_val))

    try:
        auc = roc_auc_score(y_val, val_prob)
    except Exception:
        auc = 0.50

    print(f"Validation Accuracy: {val_acc:.4f}, AUC: {auc:.4f}")

    model_path = CHALLENGER_DIR / "breakout_model.joblib"
    meta_path = CHALLENGER_DIR / "breakout_meta.json"

    joblib.dump(final_clf, model_path)

    meta = {
        "model_version": "breakout_v1_challenger",
        "feature_schema": "f28-v3",
        "label_schema": "binary_breakout_mfe1R",
        "dataset_version": Path(dataset_path).stem,
        "n_train": len(X_train),
        "n_val": len(X_val),
        "validation_accuracy": round(float(val_acc), 4),
        "validation_auc": round(float(auc), 4),
        "decision_threshold": 0.55,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"Challenger breakout model saved to {model_path}")
    print(f"Manifest written to {meta_path}")


if __name__ == "__main__":
    default_dataset = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ml_datasets", "candidates_v3.parquet")
    train_breakout(default_dataset)
