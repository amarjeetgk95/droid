"""XGBoost/LightGBM Ensemble Trainer — trains on historical feature vectors."""
import os
import json
import math
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


def _generate_synthetic_dataset(n_samples: int = 1000):
    """Generate synthetic training data from heuristic rules for cold-start.
    Uses the same logic as predictor.py: bullish if weighted score > 0.15 else bearish/neutral.
    This bootstraps the models before real historical labels are available.
    """
    import numpy as np

    rng = np.random.default_rng(42)
    X = []
    y = []
    for _ in range(n_samples):
        f = {
            "rsi_norm": float(rng.uniform(-1, 1)),
            "adx_strength": float(rng.uniform(0, 1)),
            "supertrend_signal": float(rng.choice([-1, 1])),
            "bollinger_pct_b": float(rng.uniform(-0.5, 1.5)),
            "pcr_oi_deviation": float(rng.uniform(-1, 1)),
            "max_pain_distance_pct": float(rng.uniform(-0.05, 0.05)),
            "futures_basis_pct": float(rng.uniform(-0.01, 0.01)),
            "price_above_ema20": float(rng.uniform(-0.02, 0.02)),
            "price_above_sma200": float(rng.uniform(-0.05, 0.05)),
            "pivot_position": float(rng.uniform(-1, 1)),
        }
        # Heuristic label generation (same as predictor weights)
        w_st = 0.25 * f["supertrend_signal"]
        w_rsi = 0.20 * f["rsi_norm"]
        w_pcr = 0.15 * f["pcr_oi_deviation"]
        w_basis = 0.15 * (1.0 if f["futures_basis_pct"] > 0 else -1.0) * min(1.0, abs(f["futures_basis_pct"]) * 200)
        w_ema = 0.15 * min(1.0, max(-1.0, f["price_above_ema20"] * 100))
        w_pivot = 0.10 * f["pivot_position"]
        score = w_st + w_rsi + w_pcr + w_basis + w_ema + w_pivot
        adx = f["adx_strength"]
        if score > 0.15 and adx > 0.4:
            label = "BULLISH"
        elif score < -0.15 and adx > 0.4:
            label = "BEARISH"
        else:
            label = "NEUTRAL"
        X.append([f[k] for k in FEATURE_NAMES])
        y.append(LABEL_MAP[label])
    import numpy as np

    return np.array(X, dtype=float), np.array(y, dtype=int)


async def train_ensemble(n_samples: int = 2000) -> dict:
    """Train XGBoost + LightGBM ensemble on synthetic (or historical) data and save artifacts."""
    try:
        import numpy as np
        import xgboost as xgb
        import lightgbm as lgb
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, log_loss
    except ImportError as e:
        logger.error("ml_train_import_error", error=str(e))
        raise RuntimeError(f"ML deps not installed: {e}. Run pip install -e .")

    X, y = _generate_synthetic_dataset(n_samples)

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
        "n_samples": n_samples,
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
