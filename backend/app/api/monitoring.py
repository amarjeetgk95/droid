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

P2-3: every health response also carries a ``runtime`` block with the
process-local counters for events that never become prediction rows —
persistence failures, deadline aborts and contract violations — plus the
recent latency ring (p50/p95). A failure inside the last
``RUNTIME_FRESH_WINDOW_S`` marks the health verdict degraded with a reason, so
these silent failures are now visible instead of only appearing in logs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Query

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/monitoring", tags=["Forecast Monitoring"])

# A runtime failure older than this is reported as history, not as a live
# degradation (the counters are process-lifetime, so without a window a single
# old blip would pin the verdict to degraded forever).
RUNTIME_FRESH_WINDOW_S = 15 * 60


# Runtime counters that mean "something silently failed just now", paired with
# the "last_<counter>_at" stamp that trend_forecast writes when it stamps them.
_RUNTIME_FAILURE_KEYS = (
    ("persist_failures", "last_persist_failures_at"),
    ("deadline_exceeded", "last_deadline_exceeded_at"),
    ("contract_invalid", "last_contract_invalid_at"),
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_block() -> Dict[str, Any]:
    """Process-local forecast runtime counters (never raises; {} on failure)."""
    try:
        from app.research.trend_forecast import forecast_runtime_metrics

        return dict(forecast_runtime_metrics() or {})
    except Exception as e:
        logger.warning("forecast_health_runtime_counters_failed", error=str(e)[:200])
        return {}


def _fresh_runtime_failures(runtime: Dict[str, Any]) -> List[str]:
    """Reasons for runtime failures seen inside RUNTIME_FRESH_WINDOW_S."""
    reasons: List[str] = []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=RUNTIME_FRESH_WINDOW_S)
    for count_key, stamp_key in _RUNTIME_FAILURE_KEYS:
        try:
            total = int(runtime.get(count_key) or 0)
        except (TypeError, ValueError):
            total = 0
        if total <= 0:
            continue
        raw = runtime.get(stamp_key)
        fresh = False
        if isinstance(raw, str) and raw:
            try:
                fresh = datetime.fromisoformat(raw) >= cutoff
            except ValueError:
                fresh = False
        reasons.append(f"{count_key}:{total}" + ("" if fresh else "(historical)"))
    return reasons


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
            "runtime": _runtime_block(),
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
                    "runtime": _runtime_block(),
                    "thresholds": dict(mon.DEFAULT_THRESHOLDS),
                    "window": limit,
                    "timestamp": _utcnow_iso(),
                }

        rows = [_pred_to_row(p, outcomes.get(getattr(p, "prediction_id", None))) for p in preds]
        metrics = mon.rolling_window_metrics(rows, window=limit)
        verdict = mon.check_degrade(metrics)
        degraded = bool(verdict.get("degraded", False))
        reasons = list(verdict.get("reasons") or [])
        # P2-3: persistence/deadline/contract failures are runtime events, not
        # rows — surface them here (and let a *fresh* one degrade the verdict).
        runtime = _runtime_block()
        runtime_reasons = _fresh_runtime_failures(runtime)
        fresh_runtime_failure = any(
            not r.endswith("(historical)") for r in runtime_reasons
        )
        if fresh_runtime_failure:
            degraded = True
        reasons.extend(runtime_reasons)
        if metrics.get("n") == 0 and not fresh_runtime_failure:
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
            "runtime": runtime,
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
            "runtime": _runtime_block(),
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
