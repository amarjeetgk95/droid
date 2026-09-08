"""XGBoost/LightGBM Ensemble Trainer — trains on historical feature vectors.

Phase 0: horizon-aware. Each horizon H trains its own artifact triple
(xgb/lgb/meta suffixed with _h{H}) against labels built with
app.ml.targets at TARGET_SPEC_VERSION. The unsuffixed legacy paths alias
the default horizon so existing readers keep working.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import structlog

from app.ml.targets import (
    DEFAULT_HORIZON_MINUTES,
    TARGET_SPEC_VERSION,
    validate_horizon,
)

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


def artifact_paths(horizon_minutes: int = DEFAULT_HORIZON_MINUTES) -> tuple[Path, Path, Path]:
    """Per-horizon artifact triple. Default horizon keeps legacy filenames."""
    h = validate_horizon(horizon_minutes)
    if h == DEFAULT_HORIZON_MINUTES:
        return XGB_PATH, LGB_PATH, META_PATH
    return (
        MODEL_DIR / f"xgb_model_h{h}.json",
        MODEL_DIR / f"lgb_model_h{h}.txt",
        MODEL_DIR / f"meta_h{h}.json",
    )


async def train_ensemble(
    features: list[list[float]] | None = None,
    labels: list[int] | None = None,
    horizon_minutes: int = DEFAULT_HORIZON_MINUTES,
    target_spec_version: str = TARGET_SPEC_VERSION,
) -> dict:
    """Train XGBoost + LightGBM ensemble on real historical feature vectors and save artifacts."""
    horizon_minutes = validate_horizon(horizon_minutes)
    if target_spec_version != TARGET_SPEC_VERSION:
        raise ValueError(
            f"Unknown target_spec_version {target_spec_version!r} "
            f"(trainer implements {TARGET_SPEC_VERSION!r}). Refusing to train "
            "against an undefined label definition."
        )
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
    xgb_pred = xgb_model.predict(X_test)
    xgb_proba = xgb_model.predict_proba(X_test)
    xgb_acc = accuracy_score(y_test, xgb_pred)
    xgb_ll = log_loss(y_test, xgb_proba)

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

    # Save per-horizon artifacts
    xgb_path, lgb_path, meta_path = artifact_paths(horizon_minutes)
    xgb_model.save_model(str(xgb_path))
    lgb_model.booster_.save_model(str(lgb_path))
    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": len(features),
        "feature_names": FEATURE_NAMES,
        "horizon_minutes": horizon_minutes,
        "target_spec_version": TARGET_SPEC_VERSION,
        "model_version": f"XGBoost-LightGBM-Ensemble-v2.0-h{horizon_minutes}",
        "metrics": {
            "xgb_accuracy": round(float(xgb_acc), 4),
            "xgb_logloss": round(float(xgb_ll), 4),
            "lgb_accuracy": round(float(lgb_acc), 4),
            "lgb_logloss": round(float(lgb_ll), 4),
            "ensemble_accuracy": round(float(ens_acc), 4),
        },
    }
    meta_path.write_text(json.dumps(meta, indent=2))

    logger.info("ml_ensemble_trained", horizon_minutes=horizon_minutes, **meta["metrics"])
    return meta


def load_ensemble(horizon_minutes: int = DEFAULT_HORIZON_MINUTES):
    """Load trained models for horizon H if available, else return (None, None, None).

    Falls back to the default-horizon artifacts so a 15m model serves until
    per-horizon models are trained — callers must surface calibrated=False.
    """
    horizon_minutes = validate_horizon(horizon_minutes)
    candidates = [artifact_paths(horizon_minutes)]
    if horizon_minutes != DEFAULT_HORIZON_MINUTES:
        candidates.append(artifact_paths(DEFAULT_HORIZON_MINUTES))
    for xgb_path, lgb_path, meta_path in candidates:
        if not xgb_path.exists() or not lgb_path.exists():
            continue
        try:
            import xgboost as xgb
            import lightgbm as lgb

            xgb_model = xgb.XGBClassifier()
            xgb_model.load_model(str(xgb_path))
            lgb_model = lgb.Booster(model_file=str(lgb_path))
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            return xgb_model, lgb_model, meta
        except Exception as e:
            logger.warning("ml_load_failed_fallback_to_heuristic", error=str(e))
            return None, None, None
    return None, None, None


def ensemble_predict_proba(
    feature_vec: list[float],
    horizon_minutes: int = DEFAULT_HORIZON_MINUTES,
) -> tuple[float, float, float] | None:
    """Run ensemble inference for horizon H. Returns (bearish, neutral, bullish) or None."""
    xgb_model, lgb_model, _ = load_ensemble(horizon_minutes)
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
