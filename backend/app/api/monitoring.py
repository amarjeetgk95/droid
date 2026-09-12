"""P3-2 forecast monitoring endpoints (fail-open: never 500).

Exports ``router`` ONLY — it is intentionally NOT registered in
``backend/app/main.py``. To enable, add exactly one line in ``create_app()``
next to the other routers::

    app.include_router(monitoring.router)  # backend/app/main.py

Endpoints:

- ``GET /api/v1/monitoring/forecast-health`` — rolling-window forecast
  health: ``{status, degraded, reasons, metrics, thresholds, window,
  timestamp}``. Reads the last ``limit`` predictions via
  ``PredictionService`` (DB best-effort with in-memory fallback) and joins
  outcomes per prediction; every DB touch is guarded so failures degrade to
  ``status=unknown`` (HTTP 200), never 500.
- ``GET /api/v1/monitoring/forecast-config`` — current release bundle
  (code flags, model/calibrator artifacts, feature schema, target spec);
  HTTP 200 even when artifacts are missing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Query

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/monitoring", tags=["Forecast Monitoring"])


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unknown_metrics(window: int) -> Dict[str, Any]:
    return {
        "n": 0,
        "n_scored": 0,
        "hit_rate": None,
        "brier": None,
        "ece": None,
        "freshness": {
            "candle_age_sec_max": None,
            "candle_age_sec_median": None,
            "fno_age_sec_max": None,
            "fno_age_sec_median": None,
        },
        "missing_tf_rate": None,
        "resampled_tf_rate": None,
        "ml_availability": None,
        "artifact_mismatch_count": 0,
        "artifact_mismatch_rate": 0.0,
        "window": window,
    }


def _pred_to_row(pred: Any, outcome: Any) -> Dict[str, Any]:
    """Flatten a ResearchPrediction + optional outcome to a monitoring row.

    Best-effort per field: never raises (returns {} on a hostile input).
    """
    try:
        comp = getattr(pred, "component_values", None) or {}
        if not isinstance(comp, dict):
            comp = {}
        row: Dict[str, Any] = {
            "prediction_id": getattr(pred, "prediction_id", None),
            "timestamp": getattr(pred, "timestamp", None),
            "direction": getattr(
                getattr(pred, "direction", None), "value", getattr(pred, "direction", None)
            ),
            "confidence": getattr(pred, "confidence", None),
            "settleable": comp.get("settleable", True),
            "probabilities": comp.get("probabilities"),
            "limitations": comp.get("limitations", []),
            "target_spec_version": comp.get("target_spec_version"),
            "model_source": comp.get("model_source"),
            "ml_forecast": comp.get("ml_forecast"),
        }
        explain = comp.get("explain")
        if isinstance(explain, dict):
            health = explain.get("data_health")
            if isinstance(health, dict):
                if health.get("missing_timeframes") is not None:
                    row["missing_tfs"] = health.get("missing_timeframes")
                if health.get("resampled_timeframes") is not None:
                    row["resampled_tfs"] = health.get("resampled_timeframes")
                if health.get("ml_available") is not None:
                    row["ml_available"] = health.get("ml_available")
        if outcome is not None:
            try:
                row["is_correct"] = getattr(outcome, "is_correct", None)
                actual = getattr(outcome, "actual_direction", None)
                row["actual_direction"] = getattr(actual, "value", actual)
            except Exception:
                pass
        return row
    except Exception:
        return {}


@router.get("/forecast-health")
async def forecast_health(
    limit: int = Query(default=200, ge=1, le=500),
    instrument: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Rolling forecast health over the last ``limit`` predictions (fail-open)."""
    try:
        from app.research import monitoring as mon
    except Exception as e:
        logger.warning("forecast_health_monitor_import_failed", error=str(e)[:200])
        return {
            "status": "unknown",
            "degraded": True,
            "reasons": ["health-probe-failed:monitoring-unavailable"],
            "metrics": _unknown_metrics(limit),
            "thresholds": {},
            "window": limit,
            "timestamp": _utcnow_iso(),
        }

    try:
        from app.research.predictions import PredictionService

        preds: List[Any] = []
        outcomes: Dict[str, Any] = {}
        try:
            from app.core.database import get_async_session_factory

            factory = get_async_session_factory()
        except Exception:
            factory = None

        if factory is not None:
            try:
                async with factory() as session:
                    preds = await PredictionService.list_predictions(
                        instrument=instrument, limit=limit, session=session
                    )
                    for p in preds:
                        try:
                            pid = getattr(p, "prediction_id", None)
                            if pid:
                                outcomes[pid] = await PredictionService.get_outcome(
                                    pid, session=session
                                )
                        except Exception:
                            continue
            except Exception as e:
                logger.warning("forecast_health_db_failed_fallback_memory", error=str(e)[:200])
                preds, outcomes = [], {}

        if not preds:
            try:
                preds = await PredictionService.list_predictions(
                    instrument=instrument, limit=limit
                )
                for p in preds:
                    try:
                        pid = getattr(p, "prediction_id", None)
                        if pid and pid not in outcomes:
                            outcomes[pid] = await PredictionService.get_outcome(pid)
                    except Exception:
                        continue
            except Exception as e:
                logger.warning("forecast_health_memory_failed", error=str(e)[:200])
                return {
                    "status": "unknown",
                    "degraded": True,
                    "reasons": [f"health-probe-failed:{e}"[:200]],
                    "metrics": _unknown_metrics(limit),
                    "thresholds": dict(mon.DEFAULT_THRESHOLDS),
                    "window": limit,
                    "timestamp": _utcnow_iso(),
                }

        rows = [_pred_to_row(p, outcomes.get(getattr(p, "prediction_id", None))) for p in preds]
        metrics = mon.rolling_window_metrics(rows, window=limit)
        verdict = mon.check_degrade(metrics)
        degraded = bool(verdict.get("degraded", False))
        reasons = list(verdict.get("reasons") or [])
        if metrics.get("n") == 0:
            status = "unknown"
            notes = ["warming-up-no-settled-rows"]
        else:
            status = "degraded" if degraded else "healthy"
            notes = []
        return {
            "status": status,
            "degraded": degraded,
            "reasons": reasons,
            "notes": notes,
            "metrics": metrics,
            "thresholds": dict(mon.DEFAULT_THRESHOLDS),
            "window": limit,
            "timestamp": _utcnow_iso(),
        }
    except Exception as e:
        logger.warning("forecast_health_failed_unknown", error=str(e)[:200])
        try:
            thresholds: Dict[str, Any] = dict(mon.DEFAULT_THRESHOLDS)  # type: ignore[name-defined]
        except Exception:
            thresholds = {}
        return {
            "status": "unknown",
            "degraded": True,
            "reasons": [f"health-probe-failed:{e}"[:200]],
            "metrics": _unknown_metrics(limit),
            "thresholds": thresholds,
            "window": limit,
            "timestamp": _utcnow_iso(),
        }


@router.get("/forecast-config")
async def forecast_config() -> Dict[str, Any]:
    """Current forecast release bundle (code flags + artifacts + schema/spec)."""
    try:
        from app.research import monitoring as mon

        bundle = mon.resolve_release_bundle()
        return {"status": "ok", "bundle": bundle, "timestamp": _utcnow_iso()}
    except Exception as e:
        logger.warning("forecast_config_failed_unknown", error=str(e)[:200])
        return {
            "status": "unknown",
            "bundle": {},
            "error": str(e)[:200],
            "timestamp": _utcnow_iso(),
        }
