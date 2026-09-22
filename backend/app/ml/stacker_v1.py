"""Stacked ensemble v1: logistic over layer scores + context (P2, flag-gated).

Inputs (OOS layer scores + context, all PIT-safe):
  [mtf, indicators, ml, options, structure] in [-100,100] +
  regime_onehot(TREND_UP/TREND_DOWN/RANGE/VOLATILE/UNKNOWN=5) +
  session_onehot(OPENING/EARLY/MID/LATE/CLOSING=5) +
  dte_bucket(0/1/2+) + iv_rank(0..1) + missing_count(0..5)

Width: 5+5+5+1+1+1 = 18. Artifact JSON (auditable):
  backend/app/ml/artifacts/stacker_v1.json {coef[3x18], intercept[3], schema, version}
Missing artifact -> caller falls back to fixed LAYER_WEIGHTS (v1 path untouched).
Training helper enforces chronological folds + leakage_gate when pit_records given.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MODEL_DIR = Path(__file__).parent / "artifacts"
STACKER_PATH = MODEL_DIR / "stacker_v1.json"
STACKER_VERSION = "stacker-v1"
STACKER_WIDTH = 18

REGIMES = ["TREND_UP", "TREND_DOWN", "RANGE", "VOLATILE", "UNKNOWN"]
SESSIONS = ["OPENING", "EARLY", "MID", "LATE", "CLOSING"]


def _onehot(val: str, domain: List[str]) -> List[float]:
    v = str(val or "").upper()
    return [1.0 if v == d else 0.0 for d in domain]


def build_stacker_row(
    layer_scores: Dict[str, float],
    regime: str = "UNKNOWN",
    session: str = "MID",
    dte_days: Optional[float] = None,
    iv_rank: Optional[float] = None,
    missing_count: int = 0,
) -> List[float]:
    """Build 18-wide stacker row. Honesty: iv_rank=None -> 0.5 ASSUMPTION and
    dte_days=None -> 2.0 ASSUMPTION, each bumps missing_count so downstream
    knows a placeholder was used. Callers MUST check missing_count/assumptions;
    predict_stacker itself is fail-closed (None when artifact missing).
    """
    layers = [float(layer_scores.get(k, 0.0) or 0.0) / 100.0 for k in ("mtf", "indicators", "ml", "options", "structure")]
    _assumed_missing = 0
    try:
        if dte_days is None:
            dte_b = 2.0  # ASSUMPTION: unknown expiry bucket
            _assumed_missing += 1
        else:
            dte_b = 0.0 if float(dte_days) <= 1.0 else (1.0 if float(dte_days) <= 5 else 2.0)
    except Exception:
        dte_b = 2.0
        _assumed_missing += 1
    try:
        if iv_rank is None:
            ivr = 0.5  # ASSUMPTION: mid-rank placeholder, not measured
            _assumed_missing += 1
        else:
            ivr = min(1.0, max(0.0, float(iv_rank)))
    except Exception:
        ivr = 0.5
        _assumed_missing += 1
    try:
        mc = min(5.0, max(0.0, float(missing_count) + float(_assumed_missing))) / 5.0
    except Exception:
        mc = 0.0
    return layers + _onehot(regime, REGIMES) + _onehot(session, SESSIONS) + [dte_b / 2.0, ivr, mc]


def build_stacker_row_with_meta(
    layer_scores: Dict[str, float],
    regime: str = "UNKNOWN",
    session: str = "MID",
    dte_days: Optional[float] = None,
    iv_rank: Optional[float] = None,
    missing_count: int = 0,
) -> Dict[str, Any]:
    """Row + explicit assumption list for honest callers."""
    assumptions: List[str] = []
    if dte_days is None:
        assumptions.append("dte_days-assumed-2.0-bucket")
    if iv_rank is None:
        assumptions.append("iv_rank-assumed-0.5-mid")
    row = build_stacker_row(layer_scores, regime, session, dte_days, iv_rank, missing_count)
    return {"row": row, "assumptions": assumptions, "missing_count": int(missing_count) + len(assumptions)}


def load_stacker() -> Optional[Dict[str, Any]]:
    try:
        if not STACKER_PATH.exists():
            return None
        m = json.loads(STACKER_PATH.read_text(encoding="utf-8"))
        if m.get("version") != STACKER_VERSION or len((m.get("coef") or [])) != 3:
            return None
        if any(len(r) != STACKER_WIDTH for r in m["coef"]):
            return None
        return m
    except Exception:
        return None


def predict_stacker(row: List[float]) -> Optional[Dict[str, float]]:
    """Softmax over stored coef. None when artifact missing/invalid (fail-closed).

    Unfitted (no artifact) returns None with status unfitted — never 0.5-style
    fake probs. Callers MUST treat None as unavailable, not neutral.
    """
    m = load_stacker()
    if m is None or len(row) != STACKER_WIDTH:
        return None
    try:
        import math

        logits = []
        for k in range(3):
            z = float(m["intercept"][k]) + sum(float(c) * float(x) for c, x in zip(m["coef"][k], row))
            logits.append(z)
        mx = max(logits)
        ex = [math.exp(z - mx) for z in logits]
        s = sum(ex)
        # order BEAR, NEUT, BULL
        return {"bearish": round(ex[0] / s, 4), "neutral": round(ex[1] / s, 4), "bullish": round(ex[2] / s, 4)}
    except Exception:
        return None


def train_stacker(
    rows: List[List[float]],
    labels: List[int],
    pit_records: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Train 3-class logistic (sklearn when present, else numpy GD). Enforces gates."""
    if len(rows) < 200 or len(rows) != len(labels):
        raise ValueError(f"stacker needs >=200 rows with labels (got {len(rows)})")
    if any(len(r) != STACKER_WIDTH for r in rows):
        raise ValueError(f"stacker width must be {STACKER_WIDTH}")
    if pit_records is not None:
        from app.ml.leakage_gate import leakage_gate as _lg

        _lg.assert_no_leakage(pit_records)
    try:
        from sklearn.linear_model import LogisticRegression as _LR  # type: ignore
        import numpy as _np

        X = _np.array(rows, dtype=float)
        y = _np.array(labels, dtype=int)
        # chronological 80/20 (no shuffle) for time-series honesty
        cut = int(len(X) * 0.8)
        # `lbfgs` is multinomial for a multi-class target; the explicit
        # `multi_class` kwarg was removed in scikit-learn 1.7.
        clf = _LR(solver="lbfgs", C=1.0, max_iter=500)
        clf.fit(X[:cut], y[:cut])
        meta = {"backend": "sklearn", "train_n": cut, "test_n": len(X) - cut}
        coef, intercept = clf.coef_.tolist(), clf.intercept_.tolist()
    except ImportError:
        import numpy as _np  # type: ignore

        X = _np.array(rows, dtype=float)
        y = _np.array(labels, dtype=int)
        cut = int(len(X) * 0.8)
        # tiny GD multinomial (auditable fallback)
        rng = _np.random.default_rng(42)
        W = rng.normal(0, 0.01, size=(3, STACKER_WIDTH))
        b = _np.zeros(3)
        lr = 0.5
        for _ in range(300):
            for i in range(cut):
                z = W @ X[i] + b
                z -= z.max()
                p = _np.exp(z)
                p /= p.sum()
                g = p
                g[y[i]] -= 1
                W -= lr * _np.outer(g, X[i]) / cut
                b -= lr * g / cut
        meta = {"backend": "numpy-gd", "train_n": cut, "test_n": len(X) - cut}
        coef, intercept = W.tolist(), b.tolist()
    artifact = {
        "version": STACKER_VERSION,
        "schema": f"stacker-{STACKER_WIDTH}",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n": len(rows),
        "coef": coef,
        "intercept": intercept,
        "classes": [0, 1, 2],
        "meta": meta,
    }
    MODEL_DIR.mkdir(exist_ok=True)
    STACKER_PATH.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact
