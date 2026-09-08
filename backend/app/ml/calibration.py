"""
Prediction Calibration — Phase 0

Answers "was the predictor right?" per (symbol, horizon, predicted bias).

A prediction is settled by labeling the realized forward move with the SAME
target spec used for training (app.ml.targets). Aggregation is a pure
function over settled rows so it is unit-testable without a database.
"""
from __future__ import annotations

from app.ml.targets import INV_LABEL, TARGET_SPEC_VERSION, label_forward_return


def settle_prediction(
    spot_at_t: float,
    spot_at_t_plus_h: float,
    atr_at_t: float,
) -> dict:
    """Compute the realized outcome label for one prediction.

    Returns {"outcome_label": 0|1|2, "outcome_name": str}.
    Raises ValueError on missing inputs — unsettled stays unsettled.
    """
    outcome = label_forward_return(spot_at_t, spot_at_t_plus_h, atr_at_t)
    return {"outcome_label": outcome, "outcome_name": INV_LABEL[outcome]}


def summarize_calibration(rows: list[dict]) -> dict:
    """Aggregate settled prediction rows.

    Each row: {"symbol", "horizon_minutes", "predicted_bias",
    "outcome_name" (or None if unsettled), "confidence_score",
    "target_spec_version"}.
    Rows from other spec versions are excluded and counted separately —
    mixing label definitions would corrupt hit-rates.
    """
    per_key: dict[tuple, dict] = {}
    excluded_other_spec = 0

    for r in rows:
        if r.get("outcome_name") is None:
            continue
        if r.get("target_spec_version", TARGET_SPEC_VERSION) != TARGET_SPEC_VERSION:
            excluded_other_spec += 1
            continue
        key = (r.get("symbol"), r.get("horizon_minutes"), r.get("predicted_bias"))
        cell = per_key.setdefault(key, {"n": 0, "hits": 0, "conf_sum": 0.0})
        cell["n"] += 1
        cell["conf_sum"] += float(r.get("confidence_score") or 0.0)
        if r["outcome_name"] == r.get("predicted_bias"):
            # BULLISH/BEARISH exact hits; NEUTRAL predictions hit on NEUTRAL.
            cell["hits"] += 1

    cells = []
    for (symbol, horizon_minutes, predicted_bias), cell in sorted(per_key.items()):
        n, hits = cell["n"], cell["hits"]
        cells.append(
            {
                "symbol": symbol,
                "horizon_minutes": horizon_minutes,
                "predicted_bias": predicted_bias,
                "n": n,
                "hits": hits,
                "hit_rate": round(hits / n, 4) if n else 0.0,
                "avg_confidence": round(cell["conf_sum"] / n, 1) if n else 0.0,
            }
        )

    total_n = sum(c["n"] for c in cells)
    total_hits = sum(c["hits"] for c in cells)
    return {
        "target_spec_version": TARGET_SPEC_VERSION,
        "cells": cells,
        "overall": {
            "n": total_n,
            "hits": total_hits,
            "hit_rate": round(total_hits / total_n, 4) if total_n else 0.0,
        },
        "excluded_other_spec_versions": excluded_other_spec,
    }
