"""PAP research aggregations — out-of-sample validation from REAL settled rows.

All metrics derive from the append-only ``ml_predictions`` table (settled via
the versioned ATR-band target spec). No synthetic predictions, no invented
history:

- Empty database  -> ``status: INSUFFICIENT_SAMPLE`` with null metrics.
- Regime/session cells with <30 samples -> ``INSUFFICIENT_SAMPLE``.
- Ablation / tradability have no backend experiment or cost model behind
  them -> ``status: NOT_AVAILABLE`` with an explicit reason (never zeros).
- The walk-forward verdict is evaluated server-side against the
  pre-registered PAP criteria; the frontend only renders it.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.targets import INV_LABEL, TARGET_SPEC_VERSION
from app.models.database import MLPredictionDB

logger = structlog.get_logger()

MIN_SAMPLES = 30
WALK_FOLDS = 5

OUTCOME_TO_PAP = {"BULLISH": "UP", "BEARISH": "DOWN", "NEUTRAL": "NEUTRAL"}
PAP_TO_OUTCOME = {"UP": "BULLISH", "DOWN": "BEARISH", "NEUTRAL": "NEUTRAL"}

SESSION_WINDOWS = [
    ("09:15–10:00", (9, 15), (10, 0)),
    ("10:00–11:00", (10, 0), (11, 0)),
    ("11:00–12:00", (11, 0), (12, 0)),
    ("12:00–13:00", (12, 0), (13, 0)),
    ("13:00–14:00", (13, 0), (14, 0)),
    ("14:00–15:30", (14, 0), (15, 30)),
]

IST = timezone(timedelta(hours=5, minutes=30))


# ---------------------------------------------------------------------------
# Row fetching
# ---------------------------------------------------------------------------

async def fetch_predictions(
    session: AsyncSession,
    instrument: str | None = None,
    horizon: int | None = None,
    settled_only: bool = False,
    limit: int = 500,
) -> List[MLPredictionDB]:
    stmt = select(MLPredictionDB).order_by(MLPredictionDB.timestamp.desc()).limit(limit)
    if instrument:
        stmt = stmt.where(MLPredictionDB.symbol == instrument.upper())
    if horizon is not None:
        stmt = stmt.where(MLPredictionDB.horizon_minutes == horizon)
    if settled_only:
        stmt = stmt.where(MLPredictionDB.outcome_label.is_not(None))
    result = await session.execute(stmt)
    return list(result.scalars().all())


def row_to_dict(r: MLPredictionDB) -> Dict[str, Any]:
    outcome_name = INV_LABEL.get(r.outcome_label) if r.outcome_label is not None else None
    predicted = (r.predicted_bias or "").upper()
    pap_pred = OUTCOME_TO_PAP.get(predicted)
    pap_actual = OUTCOME_TO_PAP.get(outcome_name) if outcome_name else None
    correct = (pap_pred == pap_actual) if (pap_pred and pap_actual) else None
    probs = {
        "up": round(float(r.bullish_pct or 0.0), 1),
        "neutral": round(float(r.neutral_pct or 0.0), 1),
        "down": round(float(r.bearish_pct or 0.0), 1),
    }
    max_prob = max(probs["up"], probs["neutral"], probs["down"]) / 100.0
    price_change_pct = None
    if r.outcome_spot and r.spot_price:
        try:
            price_change_pct = round((float(r.outcome_spot) - float(r.spot_price)) / float(r.spot_price) * 100.0, 4)
        except ZeroDivisionError:
            price_change_pct = None
    ts = r.timestamp
    ts_iso = ts.isoformat() if ts else None
    return {
        "time": ts_iso,
        "instrument": r.symbol,
        "horizon_minutes": r.horizon_minutes,
        "horizon": f"{r.horizon_minutes}m" if r.horizon_minutes else None,
        "p_up": probs["up"],
        "p_neutral": probs["neutral"],
        "p_down": probs["down"],
        "max_prob": round(max_prob, 4),
        "prediction": pap_pred,
        "predicted_bias": predicted,
        "actual": pap_actual,
        "outcome_name": outcome_name,
        "correct": correct,
        "confidence": float(r.confidence_score or 0.0),
        "price_change_pct": price_change_pct,
        # MFE/MAE are not tracked by the prediction ledger — null, never zero.
        "mfe_pct": None,
        "mae_pct": None,
        "spot": float(r.spot_price or 0.0),
        "outcome_spot": float(r.outcome_spot) if r.outcome_spot is not None else None,
        "market_regime": r.market_regime,
        "model_version": r.model_version,
        "target_spec_version": r.target_spec_version,
        "calibrated": bool(getattr(r, "calibrated", False)),
    }


# ---------------------------------------------------------------------------
# Metrics (pure functions over settled dicts)
# ---------------------------------------------------------------------------

def _class_metrics(rows: List[Dict[str, Any]], pred_key: str = "predicted_bias") -> Dict[str, Any]:
    classes = ["BULLISH", "BEARISH", "NEUTRAL"]
    recalls, precisions, f1s = [], [], []
    per_class: Dict[str, Any] = {}
    for c in classes:
        tp = sum(1 for r in rows if r[pred_key] == c and r["outcome_name"] == c)
        fp = sum(1 for r in rows if r[pred_key] == c and r["outcome_name"] != c)
        fn = sum(1 for r in rows if r[pred_key] != c and r["outcome_name"] == c)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        precisions.append(prec)
        recalls.append(rec)
        f1s.append(f1)
        per_class[c] = {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4), "n": tp + fn}
    # Brier score over the 3-class probability vector.
    brier_sum, brier_n = 0.0, 0
    for r in rows:
        outcome = r.get("outcome_name")
        if outcome not in classes:
            continue
        p = {
            "BULLISH": (r.get("p_up") or 0.0) / 100.0,
            "NEUTRAL": (r.get("p_neutral") or 0.0) / 100.0,
            "BEARISH": (r.get("p_down") or 0.0) / 100.0,
        }
        brier_sum += sum(((p[c] - (1.0 if outcome == c else 0.0)) ** 2) for c in classes) / 3.0
        brier_n += 1
    # Expected calibration error (5 buckets on max prob).
    buckets = [(0.0, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    ece_num, ece_den = 0.0, 0
    for lo, hi in buckets:
        cell = [r for r in rows if lo <= float(r.get("max_prob") or 0.0) < hi]
        if not cell:
            continue
        acc = sum(1 for r in cell if r.get("correct") is True) / len(cell)
        conf = sum(float(r.get("max_prob") or 0.0) for r in cell) / len(cell)
        ece_num += abs(conf - acc) * len(cell)
        ece_den += len(cell)
    n = len(rows)
    hits = sum(1 for r in rows if r.get("correct") is True)
    return {
        "n": n,
        "balanced_accuracy": round(sum(recalls) / 3.0, 4) if n else None,
        "macro_f1": round(sum(f1s) / 3.0, 4) if n else None,
        "brier": round(brier_sum / brier_n, 4) if brier_n else None,
        "calibration_error": round(ece_num / ece_den, 4) if ece_den else None,
        "hit_rate": round(hits / n, 4) if n else None,
        "per_class": per_class,
        "up_precision": per_class["BULLISH"]["precision"],
        "down_precision": per_class["BEARISH"]["precision"],
        "neutral_precision": per_class["NEUTRAL"]["precision"],
    }


def _baseline_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """No-skill baseline: always predict the majority outcome (NEUTRAL on ties)."""
    if not rows:
        return []
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["outcome_name"]] = counts.get(r["outcome_name"], 0) + 1
    majority = max(counts.items(), key=lambda kv: (kv[1], kv[0] == "NEUTRAL"))[0]
    return [{**r, "predicted_bias": majority, "p_up": 33.3, "p_neutral": 33.4, "p_down": 33.3, "max_prob": 0.334} for r in rows]


def _walk_forward(rows: List[Dict[str, Any]], folds: int = WALK_FOLDS) -> Dict[str, Any]:
    """Chronological folds; uplift = PAP balanced-accuracy minus baseline."""
    ordered = sorted([r for r in rows if r.get("time")], key=lambda r: str(r["time"]))
    if len(ordered) < MIN_SAMPLES or folds < 2:
        return {"status": "INSUFFICIENT_SAMPLE", "folds": [], "reason": f"Need >={MIN_SAMPLES} settled rows; got {len(ordered)}."}
    k = min(folds, len(ordered))
    size = len(ordered) // k
    fold_rows = [ordered[i * size:(i + 1) * size if i < k - 1 else len(ordered)] for i in range(k)]
    uplifts = []
    fold_out = []
    for i, fr in enumerate(fold_rows):
        if not fr:
            continue
        pap = _class_metrics(fr)
        base = _class_metrics(_baseline_rows(fr))
        up = (pap["balanced_accuracy"] or 0.0) - (base["balanced_accuracy"] or 0.0)
        uplifts.append(round(up, 4))
        fold_out.append({"fold": i + 1, "n": len(fr), "uplift": round(up, 4), "positive": up > 0})
    if not uplifts:
        return {"status": "INSUFFICIENT_SAMPLE", "folds": [], "reason": "No non-empty folds."}
    mean = sum(uplifts) / len(uplifts)
    var = sum((u - mean) ** 2 for u in uplifts) / len(uplifts)
    se = math.sqrt(var) / math.sqrt(len(uplifts)) if len(uplifts) > 1 else 0.0
    ci = [round(mean - 1.96 * se, 4), round(mean + 1.96 * se, 4)]
    positive = sum(1 for u in uplifts if u > 0)
    # Pre-registered gates (magnitude + stability + statistical). The economic
    # cost filter has no backend cost model yet -> reported as unevaluated and
    # caps the verdict at INCONCLUSIVE (never a false PASS).
    magnitude_ok = mean >= 0.03
    stability_ok = positive > len(uplifts) / 2
    statistical_ok = ci[0] > 0
    if magnitude_ok and stability_ok and statistical_ok:
        verdict: Literal["PASS", "FAIL", "INCONCLUSIVE"] = "INCONCLUSIVE"
        reason = "Statistical gates pass but the pre-registered economic cost/tradability filter is unevaluated (no backend cost model) — capped at INCONCLUSIVE."
    elif mean < 0 and ci[1] < 0:
        verdict = "FAIL"
        reason = "Mean uplift negative with 95% CI below zero."
    else:
        verdict = "INCONCLUSIVE"
        reason = "Gates not met for PASS and not decisively negative for FAIL."
    return {
        "status": verdict,
        "folds": fold_out,
        "positive_folds": f"{positive} / {len(uplifts)}",
        "mean_uplift": round(mean, 4),
        "confidence_interval": ci,
        "criteria": {"min_uplift": 0.03, "stability": "majority of folds positive", "statistical": "95% CI excludes zero", "economic": "unevaluated — no backend cost model"},
        "economic_evaluated": False,
        "reason": reason,
    }


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """PAP vs baseline summary with walk-forward verdict."""
    current = [r for r in rows if (r.get("target_spec_version") or TARGET_SPEC_VERSION) == TARGET_SPEC_VERSION]
    excluded = len(rows) - len(current)
    if len(current) < MIN_SAMPLES:
        return {
            "status": "INSUFFICIENT_SAMPLE",
            "n": len(current),
            "reason": f"Need >={MIN_SAMPLES} settled rows on spec {TARGET_SPEC_VERSION}; got {len(current)}.",
            "metrics": None,
            "baseline": None,
            "lift": None,
            "walk_forward": {"status": "INSUFFICIENT_SAMPLE", "folds": [], "reason": "Not enough settled rows."},
            "excluded_other_spec_versions": excluded,
            "target_spec_version": TARGET_SPEC_VERSION,
        }
    pap = _class_metrics(current)
    base = _class_metrics(_baseline_rows(current))
    lift = {
        "balanced_accuracy": round((pap["balanced_accuracy"] or 0.0) - (base["balanced_accuracy"] or 0.0), 4),
        "macro_f1": round((pap["macro_f1"] or 0.0) - (base["macro_f1"] or 0.0), 4),
    }
    return {
        "status": "OK",
        "n": len(current),
        "metrics": pap,
        "baseline": base,
        "lift": lift,
        "walk_forward": _walk_forward(current),
        "excluded_other_spec_versions": excluded,
        "target_spec_version": TARGET_SPEC_VERSION,
    }


def calibration_buckets(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    buckets = [("0.50–0.60", 0.5, 0.6), ("0.60–0.70", 0.6, 0.7), ("0.70–0.80", 0.7, 0.8), ("0.80–0.90", 0.8, 0.9), ("0.90–1.00", 0.9, 1.01)]
    out = []
    for label, lo, hi in buckets:
        cell = [r for r in rows if lo <= float(r.get("max_prob") or 0.0) < hi]
        if not cell:
            out.append({"bucket": label, "n": 0, "predicted": None, "observed": None, "error": None, "status": "INSUFFICIENT_SAMPLE"})
            continue
        pred = sum(float(r.get("max_prob") or 0.0) for r in cell) / len(cell)
        obs = sum(1 for r in cell if r.get("correct") is True) / len(cell)
        out.append({
            "bucket": label,
            "n": len(cell),
            "predicted": round(pred * 100.0, 1),
            "observed": round(obs * 100.0, 1),
            "error": round(abs(pred - obs) * 100.0, 1),
            "status": "OK" if len(cell) >= MIN_SAMPLES else "INSUFFICIENT_SAMPLE",
        })
    return {"buckets": out, "n": len(rows), "target_spec_version": TARGET_SPEC_VERSION}


def _session_of(ts_iso: str | None) -> str | None:
    if not ts_iso:
        return None
    try:
        dt = datetime.fromisoformat(ts_iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ist = dt.astimezone(IST)
    hm = (ist.hour, ist.minute)
    for label, start, end in SESSION_WINDOWS:
        if (start <= hm < end) or (label == "14:00–15:30" and hm >= start and hm < end):
            return label
    return None


def group_by(rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        k = r.get(key) if key != "session" else _session_of(r.get("time"))
        k = k or "UNKNOWN"
        groups.setdefault(str(k), []).append(r)
    out = []
    for name in sorted(groups):
        cell = groups[name]
        m = _class_metrics(cell) if len(cell) >= 1 else None
        out.append({
            "name": name,
            "n": len(cell),
            "balanced_accuracy": m["balanced_accuracy"] if m else None,
            "macro_f1": m["macro_f1"] if m else None,
            "brier": m["brier"] if m else None,
            "up_precision": m["up_precision"] if m else None,
            "down_precision": m["down_precision"] if m else None,
            "status": "OK" if len(cell) >= MIN_SAMPLES else "INSUFFICIENT_SAMPLE",
        })
    return out


async def research_counts(session: AsyncSession) -> Dict[str, int]:
    total = (await session.execute(select(func.count()).select_from(MLPredictionDB))).scalar() or 0
    settled = (await session.execute(select(func.count()).select_from(MLPredictionDB).where(MLPredictionDB.outcome_label.is_not(None)))).scalar() or 0
    return {"total": int(total), "settled": int(settled)}
