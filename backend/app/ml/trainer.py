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

# v2.3 (P2-3): sibling modules may land in parallel — import defensively.
try:  # prefer canonical v2 spec string when targets_v2 exists
    from app.ml.targets_v2 import TARGET_SPEC_VERSION_V2 as _TARGET_SPEC_V2  # type: ignore
except Exception:
    _TARGET_SPEC_V2 = "v2-atr-em-session"
TARGET_SPEC_VERSION_V2: str = str(_TARGET_SPEC_V2)
ACCEPTED_TARGET_SPECS: tuple[str, ...] = (TARGET_SPEC_VERSION, TARGET_SPEC_VERSION_V2)
V2_HORIZON_MINUTES = 60
try:  # prefer canonical schema tag when the extractor exists
    from app.ml.feature_extractor_v2 import FEATURE_SCHEMA_V2 as _SCHEMA_V2  # type: ignore

    FEATURE_SCHEMA_V2: str = str(_SCHEMA_V2)
except Exception:
    FEATURE_SCHEMA_V2 = "f12-v1"

try:  # prefer canonical v2 names when the extractor exists
    from app.ml.feature_extractor_v2 import FEATURE_NAMES_V2 as _V2_NAMES  # type: ignore

    FEATURE_NAMES_V2: list[str] = list(_V2_NAMES)
except Exception:  # fallback contract: 12 PIT-safe v2 features (f12-v1)
    # Placeholder subset of the P2-2 candidate list; frozen so width
    # mismatches fail loudly once the real extractor lands.
    FEATURE_NAMES_V2 = [
        "rsi_1h",
        "adx_1h",
        "supertrend_1h",
        "bb_pct_b_1h",
        "atr_pct_1h",
        "ret_5",
        "ret_15",
        "relative_volume",
        "vwap_distance",
        "pcr_oi",
        "vix_norm",
        "minutes_to_close",
    ]

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


def validate_width(features, expected_width: int | None = None, what: str = "features") -> int:
    """Validate feature width without hardcoding a schema size.

    Accepts a training matrix (list of rows), a single inference vector
    (flat list), or an int width. Returns the validated width. Raises
    ValueError on empty/ragged input or on ``expected_width`` mismatch.
    """
    if isinstance(features, int):
        width = int(features)
        if width <= 0:
            raise ValueError(f"{what}: width must be positive (got {features!r})")
    elif isinstance(features, (list, tuple)):
        if len(features) == 0:
            raise ValueError(f"{what}: empty feature input")
        first = features[0]
        if isinstance(first, (list, tuple)):
            width = len(first)
            if width == 0:
                raise ValueError(f"{what}: empty feature row")
            for i, row in enumerate(features):
                if not isinstance(row, (list, tuple)) or len(row) != width:
                    raise ValueError(
                        f"{what}: ragged row {i} (len "
                        f"{len(row) if isinstance(row, (list, tuple)) else '?'} != {width})"
                    )
        else:
            width = len(features)
            if width == 0:
                raise ValueError(f"{what}: empty feature vector")
    else:
        raise ValueError(f"{what}: unsupported feature input type {type(features).__name__}")
    if expected_width is not None and width != int(expected_width):
        raise ValueError(
            f"{what}: width mismatch (got {width}, expected {int(expected_width)})"
        )
    return int(width)


def _feature_names_for_width(width: int) -> list[str]:
    """Resolve artifact feature names for a validated training width."""
    if width == len(FEATURE_NAMES_V2):
        return list(FEATURE_NAMES_V2)
    if width == len(FEATURE_NAMES):
        return list(FEATURE_NAMES)
    return [f"feature_{i}" for i in range(width)]


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
    expected_width: int | None = None,
    feature_names: list[str] | None = None,
) -> dict:
    """Train XGBoost + LightGBM ensemble on real historical feature vectors and save artifacts.

    Horizon-aware: H=60 challenger rows use the v2 feature width (12 under
    f12-v1) with ``target_spec_version="v2-atr-em-session"``. Width is
    validated generically (never hardcoded to 10); v1 and v2 specs are both
    accepted and recorded verbatim in meta.
    """
    horizon_minutes = validate_horizon(horizon_minutes)
    if target_spec_version not in ACCEPTED_TARGET_SPECS:
        raise ValueError(
            f"Unknown target_spec_version {target_spec_version!r} "
            f"(trainer implements {ACCEPTED_TARGET_SPECS!r}). Refusing to train "
            "against an undefined label definition."
        )
    if not features or not labels or len(features) < 100 or len(features) != len(labels):
        raise ValueError(
            "Training requires a verified historical dataset of at least 100 samples with corresponding labels. Synthetic training generation is disallowed."
        )
    width = validate_width(features, expected_width, what="train features")
    if feature_names is not None and len(feature_names) != width:
        raise ValueError(
            f"feature_names length {len(feature_names)} != feature width {width}"
        )
    resolved_feature_names = list(feature_names) if feature_names else _feature_names_for_width(width)

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
        "feature_names": resolved_feature_names,
        "n_features": width,
        "horizon_minutes": horizon_minutes,
        "target_spec_version": target_spec_version,
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


def load_ensemble_strict(
    horizon_minutes: int = V2_HORIZON_MINUTES,
    expected_width: int | None = None,
    expected_spec: str | None = None,
):
    """Strict v2 loader: NO fallback to the default-horizon artifacts.

    Returns ``(xgb_model, lgb_model, meta)`` only when the H-specific triple
    exists AND ``meta.horizon_minutes == horizon`` AND
    ``meta.target_spec_version == expected_spec`` AND
    ``len(meta.feature_names) == expected_width``. Returns ``None`` on any
    mismatch (callers surface model_source=unavailable + confidence cap,
    never a silent h15 remap). ``load_ensemble`` above is untouched for v1
    compat.

    Defaults pin the H=60 challenger contract (width 12, v2 spec); pass
    explicit args for other horizons.
    """
    horizon_minutes = validate_horizon(horizon_minutes)
    width = int(expected_width) if expected_width is not None else len(FEATURE_NAMES_V2)
    spec = str(expected_spec) if expected_spec is not None else TARGET_SPEC_VERSION_V2
    xgb_path, lgb_path, meta_path = artifact_paths(horizon_minutes)
    if not xgb_path.exists() or not lgb_path.exists() or not meta_path.exists():
        logger.info(
            "ml_strict_missing_artifact",
            horizon_minutes=horizon_minutes,
            expected_width=width,
            expected_spec=spec,
        )
        return None
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as e:
        logger.warning("ml_strict_meta_unreadable", error=str(e))
        return None
    if int(meta.get("horizon_minutes", -1)) != int(horizon_minutes):
        logger.warning(
            "ml_strict_horizon_mismatch",
            got=meta.get("horizon_minutes"),
            expected=horizon_minutes,
        )
        return None
    if str(meta.get("target_spec_version", "")) != spec:
        logger.warning(
            "ml_strict_spec_mismatch",
            got=meta.get("target_spec_version"),
            expected=spec,
        )
        return None
    names = meta.get("feature_names", [])
    if not isinstance(names, list) or len(names) != width:
        logger.warning(
            "ml_strict_width_mismatch",
            got=len(names) if isinstance(names, list) else type(names).__name__,
            expected=width,
        )
        return None
    try:
        import xgboost as xgb
        import lightgbm as lgb

        xgb_model = xgb.XGBClassifier()
        xgb_model.load_model(str(xgb_path))
        lgb_model = lgb.Booster(model_file=str(lgb_path))
        return xgb_model, lgb_model, meta
    except Exception as e:
        logger.warning("ml_strict_load_failed", error=str(e))
        return None


def _average_ensemble_proba(xgb_model, lgb_model, feature_vec: list[float]):
    """Shared XGB+LGB averaging inference -> (bear, neut, bull) pct or None."""
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
        bear = round(bear, 1)
        neut = round(neut, 1)
        bull = round(100.0 - bear - neut, 1)
        return bear, neut, bull
    except Exception as e:
        logger.warning("ml_ensemble_predict_failed", error=str(e))
        return None


def ensemble_predict_proba(
    feature_vec: list[float],
    horizon_minutes: int = DEFAULT_HORIZON_MINUTES,
    use_strict: bool = False,
    expected_width: int | None = None,
    expected_spec: str | None = None,
) -> tuple[float, float, float] | None:
    """Run ensemble inference for horizon H. Returns (bearish, neutral, bullish) or None.

    ``use_strict=True`` routes through :func:`load_ensemble_strict` (no h15
    fallback; width/spec mismatches return None) for the v2 path. Default
    ``False`` preserves the legacy ``load_ensemble`` fallback for v1 callers.
    """
    if use_strict:
        loaded = load_ensemble_strict(
            horizon_minutes, expected_width, expected_spec
        )
        if loaded is None:
            return None
        xgb_model, lgb_model, _ = loaded
        return _average_ensemble_proba(xgb_model, lgb_model, feature_vec)
    xgb_model, lgb_model, _ = load_ensemble(horizon_minutes)
    if xgb_model is None:
        return None
    return _average_ensemble_proba(xgb_model, lgb_model, feature_vec)


def ensemble_predict_proba_strict(
    feature_vec: list[float],
    horizon_minutes: int = V2_HORIZON_MINUTES,
    expected_width: int | None = None,
    expected_spec: str | None = None,
) -> tuple[float, float, float] | None:
    """v2 inference entry-point: strict loader, no fallback (see above).

    Defaults pin H=60 / width-12 / ``v2-atr-em-session``; explicit args
    override. Existing ``ensemble_predict_proba`` callers are unaffected.
    """
    width = int(expected_width) if expected_width is not None else len(FEATURE_NAMES_V2)
    spec = str(expected_spec) if expected_spec is not None else TARGET_SPEC_VERSION_V2
    try:
        validate_width(feature_vec, width, what="strict inference vector")
    except ValueError as e:
        logger.warning("ml_strict_input_width_mismatch", error=str(e))
        return None
    return ensemble_predict_proba(
        feature_vec,
        horizon_minutes=horizon_minutes,
        use_strict=True,
        expected_width=width,
        expected_spec=spec,
    )
