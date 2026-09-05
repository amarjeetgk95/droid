"""XGBoost/LightGBM Ensemble Trainer — trains on historical feature vectors."""
import json
from datetime import datetime, timezone
from pathlib import Path

import structlog

logger = structlog.get_logger()

MODEL_DIR = Path(__file__).parent / "artifacts"
MODEL_DIR.mkdir(exist_ok=True)

XGB_PATH = MODEL_DIR / "xgb_model.json"
LGB_PATH = MODEL_DIR / "lgb_model.txt"
META_PATH = MODEL_DIR / "meta.json"

FEATURE_NAMES = [
    "rsi_norm",
    "adx_strength",
    "supertrend_signal",
    "bollinger_pct_b",
    "pcr_oi_deviation",
    "max_pain_distance_pct",
    "futures_basis_pct",
    "price_above_ema20",
    "price_above_sma200",
    "pivot_position",
]

LABEL_MAP = {"BEARISH": 0, "NEUTRAL": 1, "BULLISH": 2}
INV_LABEL = {v: k for k, v in LABEL_MAP.items()}


async def train_ensemble(
    features: list[list[float]] | None = None,
    labels: list[int] | None = None,
) -> dict:
    """Train XGBoost + LightGBM ensemble on real historical feature vectors and save artifacts."""
    if not features or not labels or len(features) < 100 or len(features) != len(labels):
        raise ValueError(
            "Training requires a verified historical dataset of at least 100 samples with corresponding labels. Synthetic training generation is disallowed."
        )

    try:
        import xgboost as xgb
        import lightgbm as lgb
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, log_loss
        import numpy as np
    except ImportError as e:
        logger.error("ml_train_import_error", error=str(e))
        raise RuntimeError(f"ML deps not installed: {e}. Run pip install -e .")

    X = np.array(features, dtype=float)
    y = np.array(labels, dtype=int)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    # XGBoost
    xgb_model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.05,
        objective="multi:softprob",
        num_class=3,
        random_state=42,
        eval_metric="mlogloss",
    )
    xgb_model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    # LightGBM
    lgb_model = lgb.LGBMClassifier(
        n_estimators=100,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="multiclass",
        num_class=3,
        random_state=42,
        verbose=-1,
        n_jobs=2,
    )
    lgb_model.fit(X_train, y_train)
    lgb_pred = lgb_model.predict(X_test)
    lgb_proba = lgb_model.predict_proba(X_test)
    lgb_acc = accuracy_score(y_test, lgb_pred)
    lgb_ll = log_loss(y_test, lgb_proba)

    # Ensemble accuracy (average proba)
    ens_proba = (xgb_proba + lgb_proba) / 2.0
    ens_pred = ens_proba.argmax(axis=1)
    ens_acc = accuracy_score(y_test, ens_pred)

    # Save artifacts
    xgb_model.save_model(str(XGB_PATH))
    lgb_model.booster_.save_model(str(LGB_PATH))
    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": len(features),
        "feature_names": FEATURE_NAMES,
        "model_version": "XGBoost-LightGBM-Ensemble-v2.0",
        "metrics": {
            "xgb_accuracy": round(float(xgb_acc), 4),
            "xgb_logloss": round(float(xgb_ll), 4),
            "lgb_accuracy": round(float(lgb_acc), 4),
            "lgb_logloss": round(float(lgb_ll), 4),
            "ensemble_accuracy": round(float(ens_acc), 4),
        },
    }
    META_PATH.write_text(json.dumps(meta, indent=2))

    logger.info("ml_ensemble_trained", **meta["metrics"])
    return meta


def load_ensemble():
    """Load trained models if available, else return None."""
    if not XGB_PATH.exists() or not LGB_PATH.exists():
        return None, None, None
    try:
        import xgboost as xgb
        import lightgbm as lgb

        xgb_model = xgb.XGBClassifier()
        xgb_model.load_model(str(XGB_PATH))
        lgb_model = lgb.Booster(model_file=str(LGB_PATH))
        meta = json.loads(META_PATH.read_text()) if META_PATH.exists() else {}
        return xgb_model, lgb_model, meta
    except Exception as e:
        logger.warning("ml_load_failed_fallback_to_heuristic", error=str(e))
        return None, None, None


def ensemble_predict_proba(feature_vec: list[float]) -> tuple[float, float, float] | None:
    """Run ensemble inference. Returns (bearish_pct, neutral_pct, bullish_pct) or None if models not loaded."""
    xgb_model, lgb_model, _ = load_ensemble()
    if xgb_model is None:
        return None
    try:
        import numpy as np

        X = np.array([feature_vec], dtype=float)
        # XGBoost proba shape (1,3) order 0=BEARISH,1=NEUTRAL,2=BULLISH
        xgb_proba = xgb_model.predict_proba(X)[0]
        # LightGBM booster predict returns proba
        lgb_proba = lgb_model.predict(X)[0]
        # Average ensemble
        ens = (xgb_proba + lgb_proba) / 2.0
        # Map: 0 BEARISH, 1 NEUTRAL, 2 BULLISH
        bear = float(ens[0] * 100.0)
        neut = float(ens[1] * 100.0)
        bull = float(ens[2] * 100.0)
        # Clamp rounding
        total = bear + neut + bull
        bear = round(bear, 1)
        neut = round(neut, 1)
        bull = round(100.0 - bear - neut, 1)
        return bear, neut, bull
    except Exception as e:
        logger.warning("ml_ensemble_predict_failed", error=str(e))
        return None
