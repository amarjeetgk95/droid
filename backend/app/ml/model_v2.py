"""1H Forecast v2.3 — L2 multinomial logistic primary (P2-3).

Primary candidate for H=60 on the v2 feature schema (``f12-v1``) and target
spec (``v2-atr-em-session``). Small, auditable, reproducible.

Backend selection:
- If scikit-learn is installed (``backend/pyproject.toml`` ``ml`` extra
  declares ``scikit-learn>=1.5.0``), training delegates to
  ``LogisticRegression(multi_class='multinomial', solver='lbfgs', C=1.0,
  max_iter=500)`` on standardized features.
- Otherwise a small full-batch gradient-descent multinomial logistic with L2
  (pure numpy, documented below) is used so unit tests and offline runs never
  require sklearn. Both paths share the same artifact schema and the same
  ``predict_proba_v2`` softmax inference.

Artifact contract (JSON, human-auditable):
- ``backend/app/ml/artifacts/model_h60_logistic.json`` — model weights +
  scaler (coef 3xD, intercept 3, classes [0,1,2]).
- ``backend/app/ml/artifacts/meta_h60_logistic.json`` — meta
  ``{model_version, dataset_hash, feature_schema, target_spec,
  training_time, n, git_sha}`` with
  ``model_version="logistic-v2-h60-v1"``,
  ``feature_schema="f12-v1"``, ``target_spec="v2-atr-em-session"``.

Label order is fixed: index 0=BEARISH, 1=NEUTRAL, 2=BULLISH, matching
``app.ml.targets.LABEL_MAP``. ``predict_proba_v2`` returns
``[bear, neut, bull]`` on the simplex.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODEL_DIR = Path(__file__).parent / "artifacts"
MODEL_DIR.mkdir(exist_ok=True)

MODEL_VERSION_V2 = "logistic-v2-h60-v1"
TARGET_SPEC_V2 = "v2-atr-em-session"
V2_HORIZON_MINUTES = 60

try:  # prefer canonical schema tag when the extractor exists
    from app.ml.feature_extractor_v2 import FEATURE_SCHEMA_V2 as _SCHEMA_V2  # type: ignore

    FEATURE_SCHEMA_V2: str = str(_SCHEMA_V2)
except Exception:
    FEATURE_SCHEMA_V2 = "f12-v1"

LOGISTIC_MODEL_PATH = MODEL_DIR / "model_h60_logistic.json"
LOGISTIC_META_PATH = MODEL_DIR / "meta_h60_logistic.json"

# Sibling agent may create backend/app/ml/feature_extractor_v2.py in
# parallel — import it defensively, else fall back to a pinned 12-name
# contract so this module (and its tests) never fail import. When the real
# extractor lands, its FEATURE_NAMES_V2 (must stay width-12 under f12-v1)
# takes precedence automatically.
try:  # pragma: no cover - exercised when extractor exists
    from app.ml.feature_extractor_v2 import FEATURE_NAMES_V2 as _EXTRACTOR_NAMES  # type: ignore

    FEATURE_NAMES_V2: list[str] = list(_EXTRACTOR_NAMES)
except Exception:  # fallback contract: 12 PIT-safe v2 features (f12-v1)
    # NOTE: placeholder subset of the P2-2 candidate list (rsi/adx/
    # supertrend/bb/atr-pct/returns/volume/vwap/pcr/vix/minutes-to-close).
    # futures_basis + supertrend_agreement deferred pending the P2-1 basis
    # plumbing decision; frozen here so width mismatches fail loudly.
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

EXPECTED_WIDTH_V2 = len(FEATURE_NAMES_V2)  # 12 under f12-v1
CLASSES_V2 = [0, 1, 2]  # BEARISH, NEUTRAL, BULLISH

try:
    from sklearn.linear_model import LogisticRegression as _SkLogReg  # noqa: F401

    HAS_SKLEARN = True
except Exception:
    HAS_SKLEARN = False


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _git_sha() -> str:
    """Best-effort git SHA, else 'unknown' (never raises)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(Path(__file__).resolve().parents[3]),
        )
        sha = (out.stdout or "").strip()
        return sha if sha else "unknown"
    except Exception:
        return "unknown"


def hash_dataset(X: list[list[float]], y: list[int]) -> str:
    """Stable short hash of a training set (rounded floats + labels)."""
    h = hashlib.sha256()
    try:
        for row in X:
            h.update((",".join(f"{float(v):.6f}" for v in row) + ";").encode())
        h.update(("|" + ",".join(str(int(v)) for v in y)).encode())
    except Exception:
        h.update(repr((X, y)).encode())
    return h.hexdigest()[:16]


def _as_numpy():
    try:
        import numpy as np  # type: ignore

        return np
    except Exception as e:
        raise RuntimeError(f"numpy is required for model_v2: {e}")


def _validate_train_inputs(
    X: list[list[float]], y: list[int], expected_width: int | None = EXPECTED_WIDTH_V2
) -> tuple[Any, Any, int, int]:
    np = _as_numpy()
    if X is None or y is None or len(X) == 0 or len(y) == 0:
        raise ValueError("train_logistic_v2 requires non-empty X and y")
    if len(X) != len(y):
        raise ValueError(f"X/y length mismatch: {len(X)} != {len(y)}")
    if len(X) < 3:
        raise ValueError("train_logistic_v2 requires at least 3 samples")
    Xa = np.array(X, dtype=float)
    ya = np.array(y, dtype=int)
    if Xa.ndim != 2:
        raise ValueError(f"X must be 2-D (got ndim={Xa.ndim})")
    n, d = int(Xa.shape[0]), int(Xa.shape[1])
    if expected_width is not None and d != int(expected_width):
        raise ValueError(
            f"Feature width mismatch: got {d}, expected {int(expected_width)} "
            f"(feature_schema={FEATURE_SCHEMA_V2})"
        )
    for v in ya.tolist():
        if int(v) not in (0, 1, 2):
            raise ValueError(f"Labels must be in {{0,1,2}} (got {v})")
    if len(set(int(v) for v in ya.tolist())) < 2:
        raise ValueError("train_logistic_v2 requires at least 2 distinct classes")
    return Xa, ya, n, d


def _standardize_fit(Xa: Any) -> tuple[Any, Any, Any]:
    np = _as_numpy()
    mean = Xa.mean(axis=0)
    std = Xa.std(axis=0)
    std = np.where(std < 1e-8, 1.0, std)  # constant feature -> scale 1 (no blowup)
    return mean, std, (Xa - mean) / std


def _softmax_rows(Z: Any) -> Any:
    np = _as_numpy()
    Zm = Z - Z.max(axis=1, keepdims=True)
    E = np.exp(Zm)
    return E / E.sum(axis=1, keepdims=True)


def _fit_numpy_gd(
    Xs: Any,
    ya: Any,
    n: int,
    d: int,
    C: float = 1.0,
    max_iter: int = 1000,
    lr: float = 0.5,
) -> tuple[Any, Any]:
    """Full-batch gradient descent for multinomial logistic + L2.

    Minimizes ``mean NLL + (1/(2*C*N)) * ||W||^2`` (bias unpenalized),
    matching sklearn's convention that C is the inverse regularization
    strength (smaller C -> stronger shrinkage). Deterministic: zero init,
    fixed lr, no minibatch noise. Fast for N~hundreds, D=12.
    """
    np = _as_numpy()
    n_classes = 3
    Y = np.zeros((n, n_classes), dtype=float)
    Y[np.arange(n), np.clip(ya.astype(int), 0, 2)] = 1.0
    W = np.zeros((d, n_classes), dtype=float)
    b = np.zeros((n_classes,), dtype=float)
    reg = float(1.0 / max(float(C), 1e-12))
    iters = int(max(50, min(int(max_iter), 5000)))
    for _ in range(iters):
        P = _softmax_rows(Xs @ W + b)
        G = (P - Y) / n  # (n,3)
        gW = Xs.T @ G + (reg / n) * W
        gb = G.sum(axis=0)
        W -= float(lr) * gW
        b -= float(lr) * gb
    # coef rows = classes, cols = features (sklearn layout)
    return W.T.copy(), b.copy()


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def train_logistic_v2(
    X: list[list[float]],
    y: list[int],
    C: float = 1.0,
    max_iter: int = 500,
    expected_width: int | None = EXPECTED_WIDTH_V2,
) -> dict:
    """Train L2 multinomial logistic on standardized v2 features.

    Returns ``{coef, intercept, classes}`` plus scaler/lineage keys
    (``scaler_mean``, ``scaler_scale``, ``n_features``, ``backend``, ...).
    ``coef`` is 3xD rows [BEARISH, NEUTRAL, BULLISH]; ``intercept`` len 3.
    """
    Xa, ya, n, d = _validate_train_inputs(X, y, expected_width)
    np = _as_numpy()
    mean, std, Xs = _standardize_fit(Xa)
    backend = "sklearn" if HAS_SKLEARN else "numpy-gd"
    if HAS_SKLEARN:
        from sklearn.linear_model import LogisticRegression

        clf = LogisticRegression(
            multi_class="multinomial",
            solver="lbfgs",
            C=float(C),
            max_iter=int(max(100, max_iter)),
        )
        clf.fit(Xs, ya)
        # Expand to full 3-class layout when a training split misses a class.
        full_coef = np.zeros((3, d), dtype=float)
        full_intercept = np.zeros((3,), dtype=float)
        for row, cls in zip(clf.coef_, clf.classes_):
            full_coef[int(cls)] = row
        for val, cls in zip(clf.intercept_, clf.classes_):
            full_intercept[int(cls)] = float(val)
        coef, intercept = full_coef, full_intercept
    else:
        coef, intercept = _fit_numpy_gd(Xs, ya, n, d, C=C, max_iter=max_iter)
    return {
        "coef": [[float(v) for v in row] for row in np.asarray(coef).tolist()],
        "intercept": [float(v) for v in np.asarray(intercept).tolist()],
        "classes": list(CLASSES_V2),
        "scaler_mean": [float(v) for v in np.asarray(mean).tolist()],
        "scaler_scale": [float(v) for v in np.asarray(std).tolist()],
        "n_features": int(d),
        "n_samples": int(n),
        "C": float(C),
        "backend": backend,
        "feature_schema": FEATURE_SCHEMA_V2,
        "target_spec": TARGET_SPEC_V2,
        "model_version": MODEL_VERSION_V2,
    }


def predict_proba_v2(model: dict, x: list[float]) -> list[float]:
    """Softmax inference for one v2 feature vector -> [bear, neut, bull]."""
    np = _as_numpy()
    try:
        coef = np.array(model["coef"], dtype=float)
        intercept = np.array(model["intercept"], dtype=float)
    except Exception as e:
        raise ValueError(f"Invalid v2 logistic model (coef/intercept): {e}")
    if coef.shape != (3, len(x)) or intercept.shape != (3,):
        # Fall back to stored width for a precise error message.
        want = model.get("n_features", coef.shape[1] if coef.ndim == 2 else "?")
        raise ValueError(f"Feature width mismatch: got {len(x)}, expected {want}")
    try:
        xv = np.array([float(v) for v in x], dtype=float)
    except Exception as e:
        raise ValueError(f"Non-numeric feature vector: {e}")
    mean = np.array(model.get("scaler_mean", [0.0] * len(x)), dtype=float)
    scale = np.array(model.get("scaler_scale", [1.0] * len(x)), dtype=float)
    scale = np.where(scale < 1e-12, 1.0, scale)
    xs = (xv - mean) / scale
    logits = coef @ xs + intercept
    logits = logits - float(np.max(logits))
    e = np.exp(logits)
    p = e / float(np.sum(e))
    out = [float(min(1.0, max(0.0, v))) for v in p.tolist()]
    s = sum(out)
    if s <= 0:
        return [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]
    out = [v / s for v in out]
    # Final renormalize guards float drift so tests can assert sum==1 tightly.
    return [out[0], out[1], out[2]]


def logistic_artifact_paths(
    model_path: Path | str | None = None, meta_path: Path | str | None = None
) -> tuple[Path, Path]:
    """Resolve (model, meta) JSON paths, defaulting to h60 artifacts."""
    return (
        Path(model_path) if model_path else LOGISTIC_MODEL_PATH,
        Path(meta_path) if meta_path else LOGISTIC_META_PATH,
    )


def save_logistic_v2(
    model: dict,
    dataset_hash: str | None = None,
    training_time: str | None = None,
    n: int | None = None,
    model_path: Path | str | None = None,
    meta_path: Path | str | None = None,
    validation_report_id: str | None = None,
    calibrator_version: str = "none-v0",
) -> dict:
    """Persist model + meta JSON; returns the meta dict."""
    m_path, mt_path = logistic_artifact_paths(model_path, meta_path)
    if not isinstance(model, dict) or "coef" not in model or "intercept" not in model:
        raise ValueError("save_logistic_v2 requires a train_logistic_v2 model dict")
    m_path.parent.mkdir(parents=True, exist_ok=True)
    m_path.write_text(json.dumps(model, indent=2))
    meta = {
        "model_version": MODEL_VERSION_V2,
        "dataset_hash": dataset_hash or model.get("dataset_hash") or "unknown",
        "feature_schema": model.get("feature_schema", FEATURE_SCHEMA_V2),
        "target_spec": model.get("target_spec", TARGET_SPEC_V2),
        "training_time": training_time or datetime.now(timezone.utc).isoformat(),
        "n": int(n if n is not None else model.get("n_samples", 0)),
        "git_sha": _git_sha(),
        "n_features": int(model.get("n_features", len(model.get("coef", [[]])[0] or []))),
        "backend": model.get("backend", "unknown"),
        "horizon_minutes": V2_HORIZON_MINUTES,
        "calibrator_version": calibrator_version,
        "validation_report_id": validation_report_id,
    }
    mt_path.write_text(json.dumps(meta, indent=2))
    return meta


def load_logistic_v2(
    model_path: Path | str | None = None, meta_path: Path | str | None = None
) -> tuple[dict | None, dict | None]:
    """Load (model, meta) or (None, None) when artifacts are absent/invalid."""
    m_path, mt_path = logistic_artifact_paths(model_path, meta_path)
    if not m_path.exists():
        return None, None
    try:
        model = json.loads(m_path.read_text())
        meta: dict | None = None
        if mt_path.exists():
            try:
                meta = json.loads(mt_path.read_text())
            except Exception:
                meta = None
        if not isinstance(model, dict) or "coef" not in model:
            return None, None
        return model, meta
    except Exception:
        return None, None


def validate_logistic_artifact(
    model: dict | None,
    meta: dict | None,
    expected_width: int = EXPECTED_WIDTH_V2,
    expected_spec: str = TARGET_SPEC_V2,
) -> bool:
    """Strict artifact check: width + spec + version must all match."""
    try:
        if not isinstance(model, dict) or not isinstance(meta, dict):
            return False
        if int(model.get("n_features", -1)) != int(expected_width):
            return False
        if len(model.get("coef", [])) != 3:
            return False
        spec = str(meta.get("target_spec", meta.get("target_spec_version", "")))
        if spec != str(expected_spec):
            return False
        if str(meta.get("feature_schema", "")) != FEATURE_SCHEMA_V2:
            return False
        if str(meta.get("model_version", "")) != MODEL_VERSION_V2:
            return False
        return True
    except Exception:
        return False
