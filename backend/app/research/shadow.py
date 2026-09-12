"""Shadow deployment pair-runner for 1H forecast v2.3 (P3-1).

Runs the v1 baseline (``FORECAST_V2_MODEL=v1``) and the v2 candidate
(``logistic-v2``) on the SAME trigger via ``TrendForecaster`` and returns
both payloads plus a ``same_inputs_hash`` proving the shared trigger.

No-global-mutation rule: this module NEVER writes ``os.environ``. The model
line is selected per-call — an explicit forecaster param when the injected
forecaster supports one (``model_override`` / ``forecast_v2_model`` /
``model`` / ``v2_model`` or ``**kwargs``), otherwise a scoped
``ContextVar`` + short-lived patch of
``app.research.trend_forecast._forecast_v2_model_flag`` that is ALWAYS
restored. Concurrent shadow pairs should be serialized (the hourly
scheduler runs a single worker); the patch window covers one awaited
``forecast()`` call at a time.

Persistence: both legs are computed with ``record=False`` (no side
effects), then — when ``record=True`` — each is persisted with its DISTINCT
``indicator_id`` (``trend_forecast_1h`` vs ``trend_forecast_1h_v2``) via the
same snapshot+prediction path ``forecast()`` uses (P0-3: never a prediction
without its snapshot). Pure orchestration otherwise; the forecaster is
injectable so tests run with deterministic mocks and no network.

P3-1 evidence rule (see plan): minimum ``2 weeks OR 250 settleable``,
whichever is stronger evidence — enforced as a warning in
``backend/scripts/shadow_compare.py``, not here.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import inspect
import json
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)

# Distinct indicator_ids: v1 baseline vs v2 shadow candidate.
SHADOW_INDICATOR_ID_V1 = "trend_forecast_1h"
SHADOW_INDICATOR_ID_V2 = "trend_forecast_1h_v2"

SHADOW_MODEL_V1 = "v1"
SHADOW_MODEL_V2 = "logistic-v2"

# Explicit model-override kwarg names accepted from injectable forecasters
# (first hit wins; a **kwargs forecaster gets "model_override").
_MODEL_KWARGS = ("model_override", "forecast_v2_model", "model", "v2_model")

# Per-task model selection. Read by the scoped patch below; never global.
_SHADOW_MODEL_OVERRIDE: ContextVar[Optional[str]] = ContextVar(
    "shadow_model_override", default=None
)


@contextlib.contextmanager
def _shadow_model_scope(model: str):
    """Scope ``model`` to one awaited ``forecast()`` call.

    Patches ``trend_forecast._forecast_v2_model_flag`` with a wrapper that
    prefers the ContextVar and falls back to the original reader, then
    restores the original unconditionally. No ``os.environ`` writes.
    """
    token = _SHADOW_MODEL_OVERRIDE.set(model)
    try:
        import app.research.trend_forecast as tf

        original = tf._forecast_v2_model_flag

        def _patched() -> str:
            override = _SHADOW_MODEL_OVERRIDE.get()
            if override is not None:
                return str(override).strip().lower()
            return original()

        tf._forecast_v2_model_flag = _patched  # type: ignore[assignment]
        try:
            yield
        finally:
            tf._forecast_v2_model_flag = original  # type: ignore[assignment]
    finally:
        _SHADOW_MODEL_OVERRIDE.reset(token)


def _model_kwarg_for(forecast_fn: Any) -> Optional[str]:
    """Explicit model kwarg the forecaster accepts, or None.

    Pure introspection — never calls the forecaster.
    """
    try:
        sig = inspect.signature(forecast_fn)
    except (TypeError, ValueError):
        return None
    params = sig.parameters
    for name in _MODEL_KWARGS:
        if name in params:
            return name
    for p in params.values():
        if p.kind == inspect.Parameter.VAR_KEYWORD:
            return _MODEL_KWARGS[0]
    return None


async def _call_forecast(
    forecaster: Any,
    *,
    instrument: str,
    horizon: str,
    model: str,
) -> Dict[str, Any]:
    """Call ``forecaster.forecast`` with ``record=False`` under ``model``.

    Prefers an explicit model kwarg when supported; otherwise relies on the
    scoped ContextVar patch. Always ``record=False`` — persistence (with the
    correct distinct ``indicator_id``) is handled by ``run_shadow_pair``.
    """
    kwarg = _model_kwarg_for(getattr(forecaster, "forecast"))
    with _shadow_model_scope(model):
        try:
            if kwarg:
                return await forecaster.forecast(
                    instrument=instrument,
                    horizon=horizon,
                    record=False,
                    **{kwarg: model},
                )
            return await forecaster.forecast(
                instrument=instrument, horizon=horizon, record=False
            )
        except TypeError:
            # Rigid mock signature (positional-only lambda etc.): retry
            # positionally, with and without the model kwarg.
            try:
                return await forecaster.forecast(instrument, horizon, False)
            except TypeError:
                if kwarg:
                    return await forecaster.forecast(
                        instrument, horizon, False, **{kwarg: model}
                    )
                raise


def _minute_bucket(now_utc: datetime) -> datetime:
    try:
        ts = now_utc
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc).replace(second=0, microsecond=0)
    except Exception:
        return datetime.now(timezone.utc).replace(second=0, microsecond=0)


def compute_same_inputs_hash(
    instrument: str,
    horizon: str,
    v1: Dict[str, Any],
    v2: Dict[str, Any],
    bucket: datetime,
) -> str:
    """Stable sha256 over the shared trigger identity + both legs' price.

    Both legs must observe the same ``current_price`` for ``same_inputs`` to
    hold; the prices are part of the hash so a mismatch is detectable from
    the hash inputs logged alongside the pair.
    """
    payload = {
        "bucket": bucket.isoformat(),
        "horizon": horizon,
        "instrument": instrument,
        "v1_current_price": (v1 or {}).get("current_price"),
        "v2_current_price": (v2 or {}).get("current_price"),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _record_shadow_result(
    result: Dict[str, Any],
    *,
    indicator_id: str,
    shadow_model: str,
    horizon: str,
    bucket: datetime,
    same_inputs_hash: str,
    now_utc: datetime,
    session: Any = None,
) -> Dict[str, str]:
    """Persist one shadow leg (snapshot + immutable prediction). Never raises.

    Mirrors ``TrendForecaster.forecast`` P0-3: snapshot first; the prediction
    is only written when the snapshot succeeded. Returns
    ``{"prediction_id", "snapshot_id"}`` (empty strings on failure, with a
    ``shadow-record-failed`` limitation appended to the result).
    """
    from app.research.enums import DataQualityStatus as _DQ
    from app.research.enums import Direction, ForecastHorizon
    from app.research.predictions import PredictionService, SnapshotService
    from app.research.models import ResearchPrediction, ResearchSnapshot

    horizon_map = {
        "1m": ForecastHorizon.HORIZON_1M,
        "5m": ForecastHorizon.HORIZON_5M,
        "15m": ForecastHorizon.HORIZON_15M,
        "30m": ForecastHorizon.HORIZON_30M,
        "1h": ForecastHorizon.HORIZON_1H,
    }
    forecast_horizon = horizon_map.get(horizon, ForecastHorizon.HORIZON_1H)
    try:
        horizon_candles = int(result.get("horizon_candles") or 1)
    except (TypeError, ValueError):
        horizon_candles = 1

    try:
        direction = Direction(str(result.get("direction") or "NEUTRAL").upper())
    except Exception:
        direction = Direction.NEUTRAL
    try:
        score = float(result.get("score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    try:
        confidence = float(result.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(1.0, max(0.0, confidence))
    try:
        current_price = float(result.get("current_price") or 0.0)
    except (TypeError, ValueError):
        current_price = 0.0

    dq_raw = str(result.get("data_quality") or "HEALTHY").upper()
    snapshot_dq = _DQ.DEGRADED if dq_raw in ("DEGRADED", "HEURISTIC", "UNSETTLEABLE") else _DQ.LIVE

    snapshot_id = ""
    prediction_id = ""
    try:
        snapshot = ResearchSnapshot(
            snapshot_id=f"snap_{uuid.uuid4().hex[:12]}",
            instrument=result.get("instrument") or "",
            timeframe=result.get("timeframe") or horizon,
            timestamp=now_utc,
            price=current_price,
            regime=result.get("regime"),
            session=result.get("session"),
            features={
                "shadow_pair": {
                    "indicator_id": indicator_id,
                    "shadow_model": shadow_model,
                    "minute_bucket": bucket.isoformat(),
                    "same_inputs_hash": same_inputs_hash,
                },
                "v2": {
                    "forecast_version": result.get("forecast_version"),
                    "status": result.get("status"),
                    "data_quality": result.get("data_quality"),
                    "settleable": result.get("settleable"),
                    "settle_reason": result.get("settle_reason"),
                    "session": result.get("session"),
                    "regime": result.get("regime"),
                    "limitations": list(result.get("limitations") or []),
                    "model_source": result.get("model_source"),
                    "weights_version": result.get("weights_version"),
                    "target_spec_version": result.get("target_spec_version"),
                    "calibrated": result.get("calibrated"),
                    "calibrator_version": result.get("calibrator_version"),
                },
            },
            options_context=result.get("options_context"),
            data_quality=snapshot_dq,
            created_at=now_utc,
        )
        snapshot_id = await SnapshotService.record_snapshot(snapshot, session=session)
    except Exception as e:
        logger.warning("shadow_snapshot_failed", indicator_id=indicator_id, error=str(e)[:200])
        snapshot_id = ""

    if snapshot_id:
        try:
            component_values = {
                "layer_scores": result.get("layer_scores"),
                "ml_forecast": result.get("ml_forecast"),
                "explain": result.get("explain"),
                "forecast_version": result.get("forecast_version"),
                "probabilities": result.get("probabilities"),
                "status": result.get("status"),
                "data_quality": result.get("data_quality"),
                "settleable": result.get("settleable"),
                "settle_reason": result.get("settle_reason"),
                "limitations": list(result.get("limitations") or []),
                "snapshot_id": snapshot_id,
                "weights_version": result.get("weights_version"),
                "target_spec_version": result.get("target_spec_version"),
                "raw_confidence": result.get("raw_confidence"),
                "calibrated": result.get("calibrated"),
                "calibrator_version": result.get("calibrator_version"),
                "regime": result.get("regime"),
                "session": result.get("session"),
                "shadow_model": shadow_model,
                "shadow_pair_hash": same_inputs_hash,
            }
            pred = ResearchPrediction(
                prediction_id=f"shadow_{horizon}_{uuid.uuid4().hex[:12]}",
                indicator_id=indicator_id,
                indicator_version="1.0.0",
                instrument=result.get("instrument") or "",
                timeframe=result.get("timeframe") or horizon,
                timestamp=now_utc,
                current_price=current_price,
                direction=direction,
                score=min(100.0, max(-100.0, score)),
                confidence=confidence,
                component_values=component_values,
                forecast_horizon=forecast_horizon,
                horizon_candles=horizon_candles,
                target_price=result.get("target_price"),
                invalidation_price=result.get("invalidation_price"),
                snapshot_id=snapshot_id,
                created_at=now_utc,
            )
            prediction_id = await PredictionService.record_prediction(pred, session=session)
        except Exception as e:
            logger.warning("shadow_prediction_failed", indicator_id=indicator_id, error=str(e)[:200])
            prediction_id = ""

    if not snapshot_id or not prediction_id:
        try:
            lims = list(result.get("limitations") or [])
            lims.append("shadow-record-failed")
            result["limitations"] = lims
        except Exception:
            pass
    return {"prediction_id": prediction_id or "", "snapshot_id": snapshot_id or ""}


async def run_shadow_pair(
    instrument: str,
    horizon: str = "1h",
    record: bool = True,
    forecaster: Any = None,
    now_utc: Optional[datetime] = None,
    session: Any = None,
) -> Dict[str, Any]:
    """Run v1 + v2-candidate on the same trigger. Returns the pair.

    Args:
        instrument: e.g. ``"NIFTY 50"``.
        horizon: forecast horizon (shadow is defined for ``"1h"``).
        record: persist both legs with distinct ``indicator_id``s.
        forecaster: injectable object with
            ``async forecast(instrument, horizon, record)``. Defaults to a
            lazily constructed ``TrendForecaster`` (no import-time side
            effects). Mocks may additionally accept a model kwarg
            (``model_override`` et al.) to return per-leg payloads.
        now_utc: trigger clock (defaults to now). Fixes the minute bucket
            and persistence timestamps; pass explicitly in tests.
        session: optional AsyncSession for persistence (None → memory
            stores, same as ``forecast()`` offline behavior).

    Returns:
        ``{"v1", "v2", "same_inputs_hash", "same_inputs", "instrument",
        "horizon", "indicator_ids", "minute_bucket"}``. The leg dicts carry
        ``indicator_id`` + ``shadow_model``; when ``record=True`` they also
        carry the real ``prediction_id`` / ``snapshot_id``.
    """
    now = now_utc
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    bucket = _minute_bucket(now)

    if forecaster is None:
        from app.research.trend_forecast import TrendForecaster

        forecaster = TrendForecaster()

    v1_raw = await _call_forecast(
        forecaster, instrument=instrument, horizon=horizon, model=SHADOW_MODEL_V1
    )
    v2_raw = await _call_forecast(
        forecaster, instrument=instrument, horizon=horizon, model=SHADOW_MODEL_V2
    )

    v1: Dict[str, Any] = copy.deepcopy(dict(v1_raw or {}))
    v2: Dict[str, Any] = copy.deepcopy(dict(v2_raw or {}))

    same_hash = compute_same_inputs_hash(instrument, horizon, v1, v2, bucket)
    try:
        same_inputs = float(v1.get("current_price") or 0.0) == float(v2.get("current_price") or 0.0)
    except (TypeError, ValueError):
        same_inputs = False
    if not same_inputs:
        logger.warning(
            "shadow_inputs_diverged",
            instrument=instrument,
            horizon=horizon,
            v1_price=(v1 or {}).get("current_price"),
            v2_price=(v2 or {}).get("current_price"),
        )

    v1["indicator_id"] = SHADOW_INDICATOR_ID_V1
    v1["shadow_model"] = SHADOW_MODEL_V1
    v2["indicator_id"] = SHADOW_INDICATOR_ID_V2
    v2["shadow_model"] = SHADOW_MODEL_V2

    if record:
        ids_v1 = await _record_shadow_result(
            v1,
            indicator_id=SHADOW_INDICATOR_ID_V1,
            shadow_model=SHADOW_MODEL_V1,
            horizon=horizon,
            bucket=bucket,
            same_inputs_hash=same_hash,
            now_utc=now,
            session=session,
        )
        ids_v2 = await _record_shadow_result(
            v2,
            indicator_id=SHADOW_INDICATOR_ID_V2,
            shadow_model=SHADOW_MODEL_V2,
            horizon=horizon,
            bucket=bucket,
            same_inputs_hash=same_hash,
            now_utc=now,
            session=session,
        )
        v1["prediction_id"] = ids_v1["prediction_id"] or v1.get("prediction_id")
        v1["snapshot_id"] = ids_v1["snapshot_id"] or v1.get("snapshot_id")
        v1["shadow_recorded"] = bool(ids_v1["prediction_id"] and ids_v1["snapshot_id"])
        v2["prediction_id"] = ids_v2["prediction_id"] or v2.get("prediction_id")
        v2["snapshot_id"] = ids_v2["snapshot_id"] or v2.get("snapshot_id")
        v2["shadow_recorded"] = bool(ids_v2["prediction_id"] and ids_v2["snapshot_id"])
        logger.info(
            "shadow_pair_recorded",
            instrument=instrument,
            horizon=horizon,
            same_inputs_hash=same_hash,
            same_inputs=same_inputs,
            v1_prediction=v1.get("prediction_id"),
            v2_prediction=v2.get("prediction_id"),
        )
    else:
        logger.info(
            "shadow_pair_computed",
            instrument=instrument,
            horizon=horizon,
            same_inputs_hash=same_hash,
            same_inputs=same_inputs,
        )

    return {
        "v1": v1,
        "v2": v2,
        "same_inputs_hash": same_hash,
        "same_inputs": same_inputs,
        "instrument": instrument,
        "horizon": horizon,
        "indicator_ids": {"v1": SHADOW_INDICATOR_ID_V1, "v2": SHADOW_INDICATOR_ID_V2},
        "minute_bucket": bucket.isoformat(),
    }
