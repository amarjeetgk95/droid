"""Multi-timeframe trend forecast orchestrator for the Research Laboratory.

Assembles every available mechanics layer in the platform into a single
point-in-time directional forecast for horizons 1m / 5m / 15m / 30m / 1h:
  - Multi-timeframe candle features (1m/5m/15m/30m/1h/4h/1D)
  - Technical analysis suite per timeframe
  - Cross-timeframe alignment
  - Research indicators (RSI, VWAP, MACD, Momentum, OMPI) on the primary timeframe
  - Quantitative ML ensemble (5/15/30/60-minute horizons; 1m degrades gracefully)
  - Options/F&O context (PCR, walls, max pain, IV, theta)

Outputs a normalized ResearchPrediction ready for immutable recording.

P3-3 SLO: p95 < 8s end-to-end (hard 12s per-timeframe fetch timeout kept in
fetch_multi_timeframe_candles via asyncio.wait_for 12.0s). Every forecast()
records result["latency_ms"] (time.monotonic delta) + structlog latency_ms.
How to measure: shadow dual-run v1/v2 logs forecast_complete latency_ms;
aggregate p50/p95 per (horizon, status) over rolling 200 settleable, or run
10 users x 60s poll + manual-refresh burst and compute p95 from logs.
Caches (FORECAST_CACHE=on/off, default on): MTF 30s / options 60s / ML 15s
per (instrument, horizon) via app.research.cache.TTLCache (max 200 keys).
Idempotency: minute-bucket key instrument|H|minute(T)|weights|model ->
replay returns the same prediction_id within the bucket (see _IDEMPOTENCY).

Robustness knobs (P1-2/P1-5/P1-6, all env-tunable and additive):
  * FORECAST_DEADLINE_S (default 20) bounds one forecast() end to end; a timeout
    raises ForecastDeadlineExceeded (never a fabricated verdict) and the API maps
    it to 503. <=0 disables the watchdog.
  * FORECAST_STAGE_TIMEOUT_S (default 3) bounds the auxiliary stages (options
    context, ML predict) so they degrade inside the budget instead of eating it.
  * Concurrent cache misses for the same key are coalesced (single-flight), and
    an all-empty MTF picture is cached only briefly (cache.NEGATIVE_TTL_S).
  * The heavy debug layers (mtf_features / indicator_outputs / options_context)
    are opt-in via include_layers=True; see FORECAST_HEAVY_LAYER_KEYS.
"""

from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import json
import math
import os
import structlog
import time
import uuid

from app.ml.predictor import MLPredictor
from app.ml.targets import TARGET_SPEC_VERSION
from app.ml.targets_v2 import TARGET_SPEC_VERSION_V2
from app.research.cache import IDEMPOTENCY, MinuteBucketReplay
from app.research.enums import Direction, ForecastHorizon
from app.research.features import FeatureLayer, classify_session_ist
from app.research.models import IndicatorContext, IndicatorOutput, ResearchPrediction, ResearchSnapshot
from app.research.options_context import ResearchOptionsContext
from app.research.predictions import PersistenceError, PredictionService, SnapshotService
from app.research.registry import IndicatorRegistry
from app.services.market_service import MarketService

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# P3-3 idempotency: minute-bucket replay map.
# Key: (instrument, horizon, minute_bucket_UTC, weights_version, model_flag).
# Value: (prediction_id, snapshot_id, result_dict_copy).
# Bounded to 500 entries (FIFO evict oldest). Only populated on successful
# record=True persists; record=False and snapshot-failure paths bypass so
# data-quality gates stay honest and unit tests stay hermetic. On a hit the
# stored result (same prediction_id) is replayed instead of minting a new
# uuid, and the duplicate fresh rows are dropped from the in-mem stores.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# P3-3 idempotency: minute-bucket replay lives in app.research.cache
# (MinuteBucketReplay). The key is (instrument, horizon, minute_bucket_UTC,
# weights_version, model_flag); a hit replays the same prediction_id instead
# of minting a new uuid, and the duplicate fresh rows are dropped from the
# in-mem stores.
# ---------------------------------------------------------------------------
_IDEMPOTENCY = IDEMPOTENCY


def clear_forecast_idempotency() -> None:
    """Test helper: clear the minute-bucket replay map."""
    _IDEMPOTENCY.clear()

# Timeframes fetched for a complete multi-timeframe picture
FORECAST_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1D"]

# Indicator IDs to include in the ensemble
ENSEMBLE_INDICATOR_IDS = ["rsi", "vwap", "macd", "momentum", "ompi"]

# Weight each mechanics layer in final score
LAYER_WEIGHTS = {
    "mtf_alignment": 0.30,
    "indicators": 0.30,
    "ml": 0.25,
    "options": 0.10,
    "structure": 0.05,
}

# Horizon-aware base weights (sum == 1.0). Short horizons trust the primary
# timeframe's fast momentum (structure/indicators); long horizons trust the
# cross-TF alignment. "1h" intentionally equals LAYER_WEIGHTS (v1 compat).
HORIZON_LAYER_WEIGHTS: Dict[str, Dict[str, float]] = {
    "1m": {"mtf_alignment": 0.15, "indicators": 0.25, "ml": 0.10, "options": 0.10, "structure": 0.40},
    "5m": {"mtf_alignment": 0.20, "indicators": 0.28, "ml": 0.12, "options": 0.10, "structure": 0.30},
    "15m": {"mtf_alignment": 0.25, "indicators": 0.30, "ml": 0.15, "options": 0.10, "structure": 0.20},
    "30m": {"mtf_alignment": 0.28, "indicators": 0.30, "ml": 0.20, "options": 0.10, "structure": 0.12},
    "1h": {"mtf_alignment": 0.30, "indicators": 0.30, "ml": 0.25, "options": 0.10, "structure": 0.05},
}

# How much of the MTF layer comes from the global cross-TF vote vs the
# primary timeframe alone. 1.0 = legacy global-only (1h compat).
HORIZON_MTF_GLOBAL_BLEND: Dict[str, float] = {
    "1m": 0.25,
    "5m": 0.40,
    "15m": 0.60,
    "30m": 0.75,
    "1h": 1.0,
}

# Short horizons get smaller directional cutoffs (smaller expected moves)
# and trust fast momentum more in the structure layer.
HORIZON_DIRECTION_THRESHOLD: Dict[str, float] = {
    "1m": 10.0,
    "5m": 12.0,
    "15m": 15.0,
    "30m": 18.0,
    "1h": 20.0,
}

# Fast-momentum weight inside the structure layer (rest is legacy
# supertrend+RSI so bullish fixtures stay bullish).
HORIZON_STRUCT_FAST_BLEND: Dict[str, float] = {
    "1m": 0.70,
    "5m": 0.65,
    "15m": 0.55,
    "30m": 0.50,
    "1h": 0.50,
}


def _clamp(x: float, lo: float, hi: float) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return max(lo, min(hi, v))


def _primary_fast_score(feat_primary: Dict[str, Any], current_price: float) -> float:
    """Fast primary-TF momentum in [-100, 100] from already-available data.

    Combines lagging supertrend with fast inputs the old structure layer
    ignored: EMA-9/21 stack, VWAP distance, last-candle returns and
    acceleration (all PIT-safe, all from FeatureLayer.compute_features).
    A fresh 1m dump turns this bearish long before 1h/4h supertrend flips.
    """
    if not isinstance(feat_primary, dict) or not feat_primary:
        return 0.0
    quant = feat_primary.get("quant", {}) if isinstance(feat_primary.get("quant"), dict) else {}
    mom = feat_primary.get("momentum_dynamics", {}) if isinstance(feat_primary.get("momentum_dynamics"), dict) else {}

    def _f(v: Any, default: float = 0.0) -> float:
        try:
            f = float(v)
            return f if math.isfinite(f) else default
        except (TypeError, ValueError):
            return default

    score = 0.0
    # Lagging trend base (kept, but no longer the whole story).
    st_dir = str(quant.get("supertrend_dir", "NEUTRAL")).upper()
    if st_dir == "BULLISH":
        score += 22.0
    elif st_dir == "BEARISH":
        score -= 22.0
    # RSI position.
    score += _clamp((_f(quant.get("rsi_14"), 50.0) - 50.0) * 0.9, -25.0, 25.0)
    # EMA stack: price vs fast averages.
    price = _f(quant.get("current_price"), 0.0) or _f(current_price, 0.0)
    ema_9 = _f(quant.get("ema_9"), 0.0)
    ema_21 = _f(quant.get("ema_21"), 0.0)
    if price > 0 and ema_9 > 0:
        score += 8.0 if price >= ema_9 else -8.0
    if ema_9 > 0 and ema_21 > 0:
        score += 7.0 if ema_9 >= ema_21 else -7.0
    # VWAP: below intraday VWAP is intraday-weak.
    vwap_d = _f(quant.get("vwap_dist_pct"), 0.0)
    score += _clamp(vwap_d * 12.0, -14.0, 14.0)
    # Fresh returns: ATR-normalized so a 1m -0.1% with thin ATR still counts.
    atr = _f(quant.get("atr_14"), 0.0)
    atr_pct = (atr / price * 100.0) if price > 0 and atr > 0 else 0.05
    if atr_pct <= 0:
        atr_pct = 0.05
    ret_1 = _f(mom.get("return_1_pct"), 0.0)
    ret_5 = _f(mom.get("return_5_pct"), 0.0)
    score += _clamp((ret_1 / atr_pct) * 8.0, -22.0, 22.0)
    score += _clamp((ret_5 / max(atr_pct * 2.0, 1e-9)) * 8.0, -18.0, 18.0)
    # Acceleration: expanding down-move pushes further bearish.
    accel = _f(mom.get("acceleration"), 0.0)
    if atr > 0:
        score += _clamp((accel / atr) * 10.0, -10.0, 10.0)
    return _clamp(score, -100.0, 100.0)


def _resolve_horizon_weights(horizon: str, ml_available: bool) -> Dict[str, float]:
    """Horizon base weights with missing-ML weight redistributed.

    When ML is unavailable (today's normal state) its share is dealt back
    to the tradeable layers proportionally instead of being scored as 0 and
    silently shrinking the final score toward neutral-while-MTF-dominates.
    Keeps an explicit ``ml: 0.0`` key so ``layer_weights`` shape is stable.
    """
    base = HORIZON_LAYER_WEIGHTS.get(horizon, LAYER_WEIGHTS)
    w = dict(base)
    if not ml_available and float(w.get("ml", 0.0)) > 0:
        dropped = float(w.get("ml", 0.0))
        w["ml"] = 0.0
        rest = sum(v for k, v in w.items() if k != "ml" and v > 0)
        if rest > 0:
            for k in list(w.keys()):
                if k == "ml":
                    continue
                w[k] = w[k] + dropped * (w[k] / rest)
    total = sum(w.values()) or 1.0
    return {k: v / total for k, v in w.items()}

# Regime-adaptive layer weights for Tactical Horizon Bias:
# - Trending: Trend alignment & ML momentum dominate
# - Ranging / Compressing: Indicators (oscillators/VWAP) & options walls dominate
# - Volatile: Options gamma/IV & structure dominate
REGIME_LAYER_WEIGHTS: Dict[str, Dict[str, float]] = {
    "TRENDING": {
        "mtf_alignment": 0.35,
        "indicators": 0.20,
        "ml": 0.30,
        "options": 0.10,
        "structure": 0.05,
    },
    "RANGING": {
        "mtf_alignment": 0.15,
        "indicators": 0.35,
        "ml": 0.15,
        "options": 0.25,
        "structure": 0.10,
    },
    "COMPRESSING": {
        "mtf_alignment": 0.15,
        "indicators": 0.35,
        "ml": 0.15,
        "options": 0.25,
        "structure": 0.10,
    },
    "VOLATILE": {
        "mtf_alignment": 0.25,
        "indicators": 0.20,
        "ml": 0.20,
        "options": 0.25,
        "structure": 0.10,
    },
    "DEFAULT": dict(LAYER_WEIGHTS),
}


def _is_adaptive_weights_enabled() -> bool:
    raw = (os.getenv("FORECAST_WEIGHTS_VERSION", "v1") or "v1").strip().lower()
    return raw in ("adaptive", "v2", "adaptive-v2") or (
        os.getenv("FORECAST_ADAPTIVE_WEIGHTS", "false") or "false"
    ).strip().lower() in ("true", "1", "yes", "on")


def get_regime_layer_weights(regime: Optional[str] = None, adaptive: Optional[bool] = None) -> Dict[str, float]:
    """Resolve layer weights dynamically conditioned on market regime."""
    is_adaptive = adaptive if adaptive is not None else _is_adaptive_weights_enabled()
    if not is_adaptive:
        return dict(LAYER_WEIGHTS)
    reg = str(regime or "").upper()
    for key, weights in REGIME_LAYER_WEIGHTS.items():
        if key != "DEFAULT" and key in reg:
            return dict(weights)
    return dict(REGIME_LAYER_WEIGHTS["DEFAULT"])


# Supported forecast horizons. ml_minutes=None means the ML predictor has no
# calibrated artifact for that horizon (see app.ml.targets.SUPPORTED_HORIZONS)
# and the ML layer degrades gracefully to neutral.
HORIZON_CONFIG: Dict[str, Dict[str, Any]] = {
    "1m": {
        "timeframe": "1m",
        "minutes": 1,
        "ml_minutes": None,
        "forecast_horizon": ForecastHorizon.HORIZON_1M,
        "horizon_candles": 1,
        "indicator_id": "trend_forecast_1m",
    },
    "5m": {
        "timeframe": "5m",
        "minutes": 5,
        "ml_minutes": 5,
        "forecast_horizon": ForecastHorizon.HORIZON_5M,
        "horizon_candles": 1,
        "indicator_id": "trend_forecast_5m",
    },
    "15m": {
        "timeframe": "15m",
        "minutes": 15,
        "ml_minutes": 15,
        "forecast_horizon": ForecastHorizon.HORIZON_15M,
        "horizon_candles": 1,
        "indicator_id": "trend_forecast_15m",
    },
    "30m": {
        "timeframe": "30m",
        "minutes": 30,
        "ml_minutes": 30,
        "forecast_horizon": ForecastHorizon.HORIZON_30M,
        "horizon_candles": 1,
        "indicator_id": "trend_forecast_30m",
    },
    "1h": {
        "timeframe": "1h",
        "minutes": 60,
        "ml_minutes": 60,
        "forecast_horizon": ForecastHorizon.HORIZON_1H,
        "horizon_candles": 1,
        "indicator_id": "trend_forecast_1h",
    },
}

SUPPORTED_HORIZONS = tuple(HORIZON_CONFIG.keys())

# Horizons rendered as one board (frontend Market Forecast). A board run
# resolves all five off a single shared MTF snapshot + anchor price
# (see TacticalHorizonEngine.forecast_board) so the cards cannot drift
# apart the way five independent point-in-time runs do.
BOARD_HORIZONS = ("1m", "5m", "15m", "30m", "1h")

# ---------------------------------------------------------------------------
# Forecast 1h-v2 (P0) contract constants
# ---------------------------------------------------------------------------
# Interim probability mapping: v1 ensemble score (±100) -> 3-class simplex via
# temperature softmax with T=40. Documented placeholder until the P2 global
# calibrator lands; ALWAYS surfaced with calibrated=false /
# calibrator_version="none-v0" so no consumer mistakes it for calibrated risk.
FORECAST_V2_SOFTMAX_TEMPERATURE = 40.0
# Neutral logit is set to DIRECTION_THRESHOLD/T so that argmax(P) agrees with
# the v1 direction thresholds (|score|>=20 directional, else neutral). At
# score=+20 bull ties neutral; above it bull is the unique max (symmetric bear).
FORECAST_V2_DIRECTION_THRESHOLD = 20.0
FORECAST_V2_CALIBRATOR_VERSION = "none-v0"

# --- P2-4/P2-5 additive flags (defaults preserve the v1 path exactly) ---
# FORECAST_V2_MODEL=v1 (default): interim T=40 softmax, ATR-only targets.
# FORECAST_V2_MODEL=logistic-v2: model_v2 probs (defensive fallback to the
# interim softmax when the parallel model_v2 module is unavailable) +
# CalibratorV1 temperature scaling when a calibrator_h60_{instrument}.json
# artifact exists, abstention gate, and risk_v2 EM-aware targets.
FORECAST_V2_MODEL_DEFAULT = "v1"
FORECAST_V2_MODEL_V2 = "logistic-v2"
# Abstention: pre-registered Cycle-1 candidates 0.55 (base) / 0.60
# (conservative, via param or env). +0.05 in VOLATILE regime / CLOSING
# session. Below threshold -> NEUTRAL/ABSTAIN with reason in limitations.
FORECAST_ABSTAIN_T_DEFAULT = 0.55
FORECAST_ABSTAIN_BUMP = 0.05
FORECAST_V2_CALIBRATOR_VERSION_V1 = "cal-v1"

FORECAST_V2_STATUSES = ("RESEARCH", "MVIG", "DEGRADED", "ABSTAIN")
FORECAST_V2_DATA_QUALITY = ("HEALTHY", "DEGRADED", "HEURISTIC", "UNSETTLEABLE")

# --- P1-2/P1-5/P1-6 additive robustness knobs (defaults preserve behaviour) ---
# P1-2: end-to-end budget for one forecast() call, in seconds. <=0 disables the
# watchdog (legacy unbounded path). On timeout we raise rather than return a
# verdict we could not compute — the module never invents a forecast, and a fast
# labeled failure beats holding the request open until the client's 60s abort.
#
# Kept above the sum of the per-stage bounds (12s primary TF fetch + 3s options +
# 3s ML) on purpose: stage-level degradation must get the chance to win, so a
# single slow timeframe returns a DEGRADED verdict instead of aborting the whole
# request. The watchdog is the last resort, catching anything else (indicators,
# explain, persistence) before the client gives up.
FORECAST_DEADLINE_S_DEFAULT = 20.0
# P1-2: per-stage budget for the auxiliary layers (options context, ML predict).
# A slow stage degrades to unavailable *inside* the budget instead of eating it.
FORECAST_STAGE_TIMEOUT_S_DEFAULT = 3.0
# P1-6: layer payloads that dominate response/replay size (every TF's full
# features incl. ta_suite, the model-dumped indicator outputs, raw F&O context).
FORECAST_HEAVY_LAYER_KEYS = ("mtf_features", "indicator_outputs", "options_context")


class ForecastDeadlineExceeded(RuntimeError):
    """Raised when a forecast exceeds its end-to-end budget (P1-2)."""


# P1-3: per-call cache provenance. A ContextVar (not an instance attribute on the
# shared singleton) so two concurrent requests cannot clobber each other's hit
# flag. The value set inside get_ml_forecast is visible to its direct caller
# because an awaited coroutine shares its caller's task context; a mocked
# forecaster simply never sets it, which reads as "no cache hit".
_ML_CACHE_HIT_FLAG: ContextVar[bool] = ContextVar("forecast_ml_cache_hit", default=False)


# ---------------------------------------------------------------------------
# P2-3: process-local runtime counters for events that never become rows.
# Persistence failures, deadline aborts and contract violations are per-request
# events — they are not persisted predictions, so /monitoring/forecast-health
# could not see them. These counters + the recent-latency ring give ops that
# visibility. Bounded, best-effort, never raises, reset on process restart.
# ---------------------------------------------------------------------------
_RUNTIME_LATENCY_MAX_SAMPLES = 200
_RUNTIME_STATE: Dict[str, Any] = {
    "started_at": None,
    "calls": 0,
    "deadline_exceeded": 0,
    "persist_failures": 0,
    "contract_invalid": 0,
    "degraded": 0,
    "abstain": 0,
    "bucket_replays": 0,
    # "last_<counter>_at" stamps are written on demand by _bump_runtime(stamp=True).
    "latency_ms": [],
}


def _bump_runtime(
    name: Optional[str] = None,
    *,
    stamp: bool = False,
    latency_ms: Any = None,
) -> None:
    """Bump runtime counter ``name`` and/or record a latency sample.

    ``name=None`` records only the latency (nothing to count). Best-effort —
    never raises.
    """
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        if _RUNTIME_STATE.get("started_at") is None:
            _RUNTIME_STATE["started_at"] = now_iso
        if name and name in _RUNTIME_STATE:
            _RUNTIME_STATE[name] = int(_RUNTIME_STATE.get(name) or 0) + 1
            if stamp:
                _RUNTIME_STATE[f"last_{name}_at"] = now_iso
        if latency_ms is not None:
            try:
                _RUNTIME_STATE["latency_ms"].append(float(latency_ms))
                if len(_RUNTIME_STATE["latency_ms"]) > _RUNTIME_LATENCY_MAX_SAMPLES:
                    _RUNTIME_STATE["latency_ms"] = _RUNTIME_STATE["latency_ms"][
                        -_RUNTIME_LATENCY_MAX_SAMPLES:
                    ]
            except (TypeError, ValueError):
                pass
    except Exception:
        pass


def _percentile(samples: List[float], pct: float) -> Optional[float]:
    """Nearest-rank percentile of ``samples`` (None when empty). Pure."""
    try:
        if not samples:
            return None
        ordered = sorted(float(s) for s in samples)
        if len(ordered) == 1:
            return round(ordered[0], 2)
        idx = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
        return round(ordered[idx], 2)
    except Exception:
        return None


def forecast_runtime_metrics() -> Dict[str, Any]:
    """Snapshot of the process-local forecast runtime counters (P2-3).

    Counters are monotonic since process start; only the latency ring is
    bounded, so ``latency_ms_p50/p95`` describe the most recent samples.
    """
    try:
        samples = list(_RUNTIME_STATE.get("latency_ms") or [])
        return {
            "started_at": _RUNTIME_STATE.get("started_at"),
            "calls": int(_RUNTIME_STATE.get("calls") or 0),
            "deadline_exceeded": int(_RUNTIME_STATE.get("deadline_exceeded") or 0),
            "persist_failures": int(_RUNTIME_STATE.get("persist_failures") or 0),
            "contract_invalid": int(_RUNTIME_STATE.get("contract_invalid") or 0),
            "degraded": int(_RUNTIME_STATE.get("degraded") or 0),
            "abstain": int(_RUNTIME_STATE.get("abstain") or 0),
            "bucket_replays": int(_RUNTIME_STATE.get("bucket_replays") or 0),
            "last_deadline_exceeded_at": _RUNTIME_STATE.get("last_deadline_exceeded_at"),
            "last_persist_failures_at": _RUNTIME_STATE.get("last_persist_failures_at"),
            "last_contract_invalid_at": _RUNTIME_STATE.get("last_contract_invalid_at"),
            "latency_samples": len(samples),
            "latency_ms_p50": _percentile(samples, 50),
            "latency_ms_p95": _percentile(samples, 95),
        }
    except Exception:
        return {}


def reset_forecast_runtime_metrics() -> None:
    """Test helper: zero the runtime counters."""
    try:
        for key in list(_RUNTIME_STATE.keys()):
            if key == "latency_ms":
                _RUNTIME_STATE[key] = []
            elif key == "started_at" or key.startswith("last_"):
                _RUNTIME_STATE.pop(key, None)
            elif isinstance(_RUNTIME_STATE[key], int):
                _RUNTIME_STATE[key] = 0
    except Exception:
        pass


def forecast_deadline_s() -> float:
    """End-to-end forecast budget in seconds (<=0 disables the watchdog)."""
    try:
        return float(os.getenv("FORECAST_DEADLINE_S", str(FORECAST_DEADLINE_S_DEFAULT)))
    except (TypeError, ValueError):
        return FORECAST_DEADLINE_S_DEFAULT


def _stage_timeout_s() -> float:
    """Per-stage budget for options/ML (<=0 disables the stage timeout)."""
    try:
        return float(
            os.getenv("FORECAST_STAGE_TIMEOUT_S", str(FORECAST_STAGE_TIMEOUT_S_DEFAULT))
        )
    except (TypeError, ValueError):
        return FORECAST_STAGE_TIMEOUT_S_DEFAULT


def _forecast_weights_version() -> str:
    """Weights bundle tag. P0 only ships v1 (rollback = flip env + redeploy)."""
    raw = (os.getenv("FORECAST_WEIGHTS_VERSION", "v1") or "v1").strip() or "v1"
    return f"forecast-{raw}"


async def _ensure_forecast_indicator_definition(
    session: Any, *, indicator_id: str, horizon: str
) -> None:
    """Idempotently seed this engine's indicator definition row.

    ``research_predictions.indicator_id`` is a FK to
    ``research_indicator_definitions`` and nothing ever seeds the
    ``trend_forecast_*`` ids (``IndicatorRegistry.sync_to_db`` is never
    called), so without this every strict prediction insert fails the FK and
    the run degrades with ``persistence-failed:prediction``. ON CONFLICT DO
    NOTHING keeps this safe to call on every record path; the commit makes the
    row durable even if the prediction insert that follows still fails.
    """
    from sqlalchemy import text as _text

    await session.execute(
        _text("""
            INSERT INTO research_indicator_definitions (
                indicator_id, name, category, description, author,
                lifecycle, current_version, supported_timeframes,
                supported_instruments, formula_summary, parameters_schema,
                updated_at
            ) VALUES (
                :indicator_id, :name, :category, :description, :author,
                :lifecycle, :current_version, CAST(:supported_timeframes AS jsonb),
                CAST(:supported_instruments AS jsonb), :formula_summary,
                CAST(:parameters_schema AS jsonb), NOW()
            )
            ON CONFLICT (indicator_id) DO NOTHING;
        """),
        {
            "indicator_id": indicator_id,
            "name": f"Tactical Horizon Bias {horizon}",
            "category": "PROPRIETARY",
            "description": (
                "Probabilistic tactical horizon bias from the tactical_horizon_engine "
                "ensemble (MTF alignment, research indicators, ML, options context, "
                "structure) with ATR/EM risk targets."
            ),
            "author": "system",
            "lifecycle": "PRODUCTION",
            "current_version": "1.0.0",
            "supported_timeframes": json.dumps(["1m", "5m", "15m", "30m", "1h"]),
            "supported_instruments": json.dumps(["NIFTY 50", "BANKNIFTY", "SENSEX"]),
            "formula_summary": "Regime-weighted layer vote; direction at |score|>=20; ATR14 targets.",
            "parameters_schema": json.dumps({}),
        },
    )
    await session.commit()


def _heuristic_allowed() -> bool:
    """FORECAST_ALLOW_HEURISTIC=false disables the unlabeled heuristic ML path
    (ML layer then reports unavailable + capped confidence instead)."""
    return (os.getenv("FORECAST_ALLOW_HEURISTIC", "true") or "true").strip().lower() not in (
        "false", "0", "no", "off"
    )


def score_to_probabilities_v2(score: float, temperature: float = FORECAST_V2_SOFTMAX_TEMPERATURE) -> Dict[str, float]:
    """Map a v1 ensemble score in [-100, 100] to P0 interim class probabilities.

    Logits: bull=score/T, bear=-score/T, neutral=THRESHOLD/T (THRESHOLD=20, the
    v1 direction cutoff). Softmaxed, rounded to 4dp with the residual folded
    into the max bucket so sum(P)==1 exactly. UNCALIBRATED by construction.
    """
    try:
        s = float(score)
    except (TypeError, ValueError):
        s = 0.0
    s = max(-100.0, min(100.0, s))
    t = float(temperature) if temperature and float(temperature) > 0 else FORECAST_V2_SOFTMAX_TEMPERATURE
    l_bull = s / t
    l_bear = -s / t
    l_neut = FORECAST_V2_DIRECTION_THRESHOLD / t
    m = max(l_bull, l_bear, l_neut)
    e_bull, e_bear, e_neut = math.exp(l_bull - m), math.exp(l_bear - m), math.exp(l_neut - m)
    total = e_bull + e_bear + e_neut
    probs = {
        "bullish": round(e_bull / total, 4),
        "neutral": round(e_neut / total, 4),
        "bearish": round(e_bear / total, 4),
    }
    # Fold rounding residual into the largest bucket -> exact simplex.
    residual = round(1.0 - (probs["bullish"] + probs["neutral"] + probs["bearish"]), 4)
    if residual != 0.0:
        top = max(probs, key=lambda k: probs[k])
        probs[top] = round(probs[top] + residual, 4)
    return probs


# ---------------------------------------------------------------------------
# P2-4/P2-5 helpers: model flag, abstention, defensive model_v2 + calibrator
# ---------------------------------------------------------------------------

def _forecast_v2_model_flag() -> str:
    """Active forecast model line: "v1" (default) or "logistic-v2"."""
    raw = (os.getenv("FORECAST_V2_MODEL", FORECAST_V2_MODEL_DEFAULT)
           or FORECAST_V2_MODEL_DEFAULT)
    return raw.strip().lower() or FORECAST_V2_MODEL_DEFAULT


def _abstain_base_threshold(override: Optional[float] = None) -> float:
    """Base abstain threshold: explicit param wins, else FORECAST_ABSTAIN_T."""
    if override is not None:
        try:
            t = float(override)
        except (TypeError, ValueError):
            t = FORECAST_ABSTAIN_T_DEFAULT
        if 0.0 < t < 1.0:
            return t
        return FORECAST_ABSTAIN_T_DEFAULT
    try:
        t = float(os.getenv("FORECAST_ABSTAIN_T", str(FORECAST_ABSTAIN_T_DEFAULT))
                  or FORECAST_ABSTAIN_T_DEFAULT)
    except (TypeError, ValueError):
        t = FORECAST_ABSTAIN_T_DEFAULT
    if 0.0 < t < 1.0:
        return t
    return FORECAST_ABSTAIN_T_DEFAULT


def get_abstain_threshold(
    regime: Optional[str] = None,
    session_label: Optional[str] = None,
    override: Optional[float] = None,
) -> float:
    """Effective abstention threshold (Cycle-1: 0.55 base / 0.60 conservative).

    +0.05 (once, capped at 0.95) when regime is VOLATILE or the session is
    CLOSING. Pure: reads env only for the base default.
    """
    base = _abstain_base_threshold(override)
    reg = str(regime or "").upper()
    ses = str(session_label or "").upper()
    if "VOLATILE" in reg or ses == "CLOSING":
        return round(min(0.95, base + FORECAST_ABSTAIN_BUMP), 4)
    return round(base, 4)


def should_abstain(confidence: float, threshold: float) -> bool:
    """True when post-calibration confidence is strictly below threshold."""
    try:
        return float(confidence) < float(threshold)
    except (TypeError, ValueError):
        return True


def apply_abstention_v2(
    direction: str,
    confidence: float,
    threshold: float,
) -> Dict[str, Any]:
    """Pure abstention verdict: below threshold -> NEUTRAL/ABSTAIN + reason.

    Returns {"direction", "status", "abstained", "limitation"} where
    limitation is None on pass. Passing verdicts keep the input direction
    with status RESEARCH (downstream DQ gates may still cap/degrade).
    """
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        conf = 0.0
    try:
        thr = float(threshold)
    except (TypeError, ValueError):
        thr = FORECAST_ABSTAIN_T_DEFAULT
    if conf < thr:
        return {
            "direction": Direction.NEUTRAL.value,
            "status": "ABSTAIN",
            "abstained": True,
            "limitation": f"abstain-confidence-{conf:.4f}-below-{thr:.2f}",
        }
    d = str(direction or Direction.NEUTRAL.value).upper()
    if d not in ("BULLISH", "BEARISH", "NEUTRAL"):
        d = Direction.NEUTRAL.value
    return {"direction": d, "status": "RESEARCH", "abstained": False, "limitation": None}


def _round_probs_4dp(prob_dict: Dict[str, float]) -> Dict[str, float]:
    """Round {bullish, neutral, bearish} to 4dp, folding residual into max."""
    out = {
        "bullish": round(float(prob_dict.get("bullish", 0.0)), 4),
        "neutral": round(float(prob_dict.get("neutral", 0.0)), 4),
        "bearish": round(float(prob_dict.get("bearish", 0.0)), 4),
    }
    residual = round(1.0 - (out["bullish"] + out["neutral"] + out["bearish"]), 4)
    if residual != 0.0:
        top = max(out, key=lambda k: out[k])
        out[top] = round(out[top] + residual, 4)
    return out


def _normalize_model_v2_output(out: Any) -> Optional[Dict[str, float]]:
    """Normalize a defensive model_v2 return to {bullish, neutral, bearish}.

    Accepts a dict (bullish/neutral/bearish keys, case-insensitive, with
    bull/neut/bear aliases) or a 3-list assumed in LABEL_MAP order
    [bearish, neutral, bullish]. Returns None when unusable.
    """
    try:
        if isinstance(out, dict):
            low = {str(k).lower(): v for k, v in out.items()}
            bull = low.get("bullish", low.get("bull"))
            neut = low.get("neutral", low.get("neut"))
            bear = low.get("bearish", low.get("bear"))
            if bull is None or neut is None or bear is None:
                return None
            vals = {"bullish": float(bull), "neutral": float(neut), "bearish": float(bear)}
        elif isinstance(out, (list, tuple)) and len(out) == 3:
            vals = {"bearish": float(out[0]), "neutral": float(out[1]), "bullish": float(out[2])}
        else:
            return None
    except (TypeError, ValueError):
        return None
    if any(v != v for v in vals.values()):
        return None
    if any(v < 0.0 for v in vals.values()):
        return None
    s = vals["bullish"] + vals["neutral"] + vals["bearish"]
    if not s > 0:
        return None
    vals = {k: v / s for k, v in vals.items()}
    return _round_probs_4dp(vals)


def _try_model_v2_raw_probs(
    mtf_features: Dict[str, Any],
    indicator_outputs: List[Any],
    ml_forecast: Optional[Dict[str, Any]],
    options_ctx: Dict[str, Any],
    current_price: float,
    horizon: str,
) -> tuple[Optional[Dict[str, float]], Dict[str, Any]]:
    """Defensive model_v2 hook (parallel track may not exist yet). Never raises.

    Returns (probs_or_None, info{limitation, model_version, model_source}).
    Missing module / missing entry point / bad output all degrade to
    (None, {limitation: ...-fallback-v1}) so the interim softmax stays.
    """
    info: Dict[str, Any] = {"limitation": None, "model_version": None, "model_source": None}
    try:
        import importlib

        try:
            m2 = importlib.import_module("app.ml.model_v2")
        except ImportError:
            info["limitation"] = "model-v2-unavailable-fallback-v1"
            return None, info
        ctx = {
            "instrument": (mtf_features or {}).get("instrument"),
            "mtf_features": mtf_features,
            "indicator_scores": [float(getattr(o, "score", 0.0) or 0.0) for o in (indicator_outputs or [])],
            "ml_forecast": ml_forecast,
            "options_ctx": options_ctx,
            "current_price": current_price,
            "horizon": horizon,
        }
        probs: Optional[Dict[str, float]] = None
        for fn_name in ("predict_proba_v2", "predict_proba", "predict"):
            fn = getattr(m2, fn_name, None)
            if not callable(fn):
                continue
            try:
                out = fn(ctx)
            except TypeError:
                try:
                    out = fn(
                        mtf_features=mtf_features,
                        indicator_outputs=indicator_outputs,
                        ml_forecast=ml_forecast,
                        options_ctx=options_ctx,
                        current_price=current_price,
                        horizon=horizon,
                    )
                except Exception:
                    continue
            except Exception:
                continue
            probs = _normalize_model_v2_output(out)
            if probs is not None:
                break
        if probs is None:
            # Precise honesty: module present but no trained h60 artifact.
            try:
                loader = getattr(m2, "load_logistic_v2", None)
                if callable(loader) and loader()[0] is None:
                    info["limitation"] = "model-v2-artifact-missing-fallback-v1"
                    return None, info
            except Exception:
                pass
            info["limitation"] = "model-v2-no-proba-fallback-v1"
            return None, info
        info["model_version"] = (
            getattr(m2, "MODEL_VERSION_V2", None)
            or getattr(m2, "__version__", None)
            or "logistic-v2-h60"
        )
        info["model_source"] = "logistic_v2"
        return probs, info
    except Exception as e:
        info["limitation"] = f"model-v2-failed-fallback-v1:{e}"
        return None, info


def _try_calibrate_probs(
    prob_dict: Dict[str, float],
    instrument: Optional[str],
) -> tuple[Dict[str, float], bool, str, Optional[str]]:
    """Apply the persisted CalibratorV1 when present. Never raises.

    Returns (probs, calibrated, calibrator_version, limitation_or_None).
    Missing artifact -> pass-through + "calibrator-missing-uncalibrated".
    """
    try:
        from app.ml.calibrators import load_calibrator

        cal = load_calibrator(instrument or "UNKNOWN", h=60)
    except Exception:
        cal = None
    if cal is None:
        return (
            dict(prob_dict),
            False,
            FORECAST_V2_CALIBRATOR_VERSION,
            "calibrator-missing-uncalibrated",
        )
    try:
        return (
            _round_probs_4dp(cal.calibrate_dict(prob_dict)),
            True,
            FORECAST_V2_CALIBRATOR_VERSION_V1,
            None,
        )
    except Exception as e:
        return (
            dict(prob_dict),
            False,
            FORECAST_V2_CALIBRATOR_VERSION,
            f"calibrator-failed-uncalibrated:{e}",
        )


def validate_forecast_v2(d: Any, record: Optional[bool] = None) -> List[str]:
    """Pure contract validator for the 1h-v2 response dict.

    Checks: version strings present, probabilities form a valid simplex,
    confidence within [0,1] and never above max(P) (gates only cap down),
    status/data_quality enums, limitations list, and — when the forecast was
    persisted (record=True, or equivalently prediction_id present without a
    snapshot) — that snapshot_id is set. Returns a list of error strings
    (empty == valid). Never raises, never touches I/O.
    """
    errors: List[str] = []
    if not isinstance(d, dict):
        return ["forecast-not-a-dict"]
    fv = d.get("forecast_version")
    if not isinstance(fv, str) or not fv.endswith("-v2"):
        errors.append("missing-or-bad-forecast_version")
    probs = d.get("probabilities")
    probs_ok = False
    if not isinstance(probs, dict):
        errors.append("missing-probabilities")
    else:
        vals: Dict[str, float] = {}
        ok = True
        for k in ("bullish", "neutral", "bearish"):
            v = probs.get(k)
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                errors.append(f"probability-not-numeric:{k}")
                ok = False
            elif not (0.0 <= float(v) <= 1.0) or float(v) != float(v):
                errors.append(f"probability-out-of-range:{k}")
                ok = False
            else:
                vals[k] = float(v)
        if ok:
            if abs(sum(vals.values()) - 1.0) > 1e-6:
                errors.append(f"probabilities-sum-{sum(vals.values()):.6f}-ne-1")
            else:
                probs_ok = True
    conf = d.get("confidence")
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
        errors.append("confidence-out-of-range")
    elif probs_ok and float(conf) - max(probs["bullish"], probs["neutral"], probs["bearish"]) > 1e-6:
        errors.append("confidence-exceeds-max-probability")
    for key in ("model_version", "calibrator_version", "weights_version", "target_spec_version"):
        if not d.get(key) or not isinstance(d.get(key), str):
            errors.append(f"missing-{key}")
    if not isinstance(d.get("calibrated"), bool):
        errors.append("missing-calibrated-flag")
    if not d.get("model_source") or not isinstance(d.get("model_source"), str):
        errors.append("missing-model_source")
    if d.get("status") not in FORECAST_V2_STATUSES:
        errors.append("missing-or-bad-status")
    if d.get("data_quality") not in FORECAST_V2_DATA_QUALITY:
        errors.append("missing-or-bad-data_quality")
    if not isinstance(d.get("limitations"), list):
        errors.append("missing-limitations")
    rec = record
    if rec is None:
        rec = d.get("record", d.get("record_requested", None))
    if rec is None:
        # Derivable fallback: a persisted prediction (id present) implies record.
        rec = d.get("prediction_id") is not None
    if d.get("prediction_id") and not d.get("snapshot_id"):
        errors.append("prediction-without-snapshot")
    if rec and not d.get("snapshot_id"):
        errors.append("missing-snapshot-for-record")
    return errors


class _MTFCandles(dict):
    """Dict of timeframe -> candles that also carries resample provenance.

    fetch_multi_timeframe_candles returns this so forecast() can apply the
    P0-2 "resampled primary timeframe -> DEGRADED" gate. Plain-dict behaviour
    is preserved for all existing callers. ``cache_hit`` is P1-3 per-call
    provenance: it travels with the returned payload instead of living on the
    shared singleton, where concurrent requests clobbered each other's flag.
    """

    def __init__(
        self,
        *args: Any,
        resampled_tfs: Optional[List[str]] = None,
        cache_hit: bool = False,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.resampled_tfs: List[str] = list(resampled_tfs or [])
        self.cache_hit: bool = bool(cache_hit)


def _candle_to_dict(c: Any) -> Dict[str, Any]:
    """Normalize a candle object to a plain dict."""
    if isinstance(c, dict):
        return c
    return {
        "open": float(getattr(c, "open", 0.0)),
        "high": float(getattr(c, "high", 0.0)),
        "low": float(getattr(c, "low", 0.0)),
        "close": float(getattr(c, "close", 0.0)),
        "volume": float(getattr(c, "volume", 0.0) or 0.0),
        "timestamp": (
            getattr(c, "timestamp", datetime.now(timezone.utc)).isoformat()
            if hasattr(getattr(c, "timestamp", None), "isoformat")
            else str(getattr(c, "timestamp", ""))
        ),
    }


class TrendForecaster:
    """Orchestrates a multi-timeframe trend forecast using all platform mechanics."""

    def __init__(self, market_service: Optional[MarketService] = None, ml_predictor: Optional[MLPredictor] = None):
        self.market_service = market_service or MarketService()
        self.ml_predictor = ml_predictor or MLPredictor()
        # P3-3 instance-level TTL caches (same TTLs as cache.py defaults).
        # Instance-scoped so unit tests with fresh forecasters stay hermetic;
        # the production singleton (trend_forecaster) still gets cross-request
        # hits. Module-level caches in app.research.cache remain for pure tests.
        try:
            from app.research.cache import ML_TTL_S, MTF_TTL_S, OPTIONS_TTL_S, TTLCache

            self._mtf_cache = TTLCache(MTF_TTL_S)
            self._options_cache = TTLCache(OPTIONS_TTL_S)
            self._ml_cache = TTLCache(ML_TTL_S)
        except Exception:
            self._mtf_cache = None
            self._options_cache = None
            self._ml_cache = None

    # P1-5: single-flight lock registry. Keyed exactly like the caches (via the
    # same key helpers) and bounded, so a long-lived singleton cannot accumulate
    # locks for retired instruments. Lazy (not created in __init__) so tests that
    # build an instance with __new__ still work.
    _FLIGHT_MAX_LOCKS = 200

    def _flight_lock(self, key: Any) -> Any:
        """Per-key :class:`asyncio.Lock` used to collapse concurrent cache misses."""
        import asyncio

        locks = getattr(self, "_flight_locks", None)
        if locks is None:
            locks = {}
            try:
                self._flight_locks = locks
            except Exception:
                pass
        lock = locks.get(key)
        if lock is None:
            if len(locks) >= self._FLIGHT_MAX_LOCKS:
                # Cheap bound. A holder that already captured its lock still
                # finishes; only brand-new arrivals can briefly miss coalescing.
                locks.clear()
            lock = asyncio.Lock()
            locks[key] = lock
        return lock

    async def fetch_multi_timeframe_candles(
        self,
        instrument: str,
        timeframes: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch candles for all required timeframes concurrently.

        Previously sequential (7 x up-to-6s history calls + rate limiter), so a
        slow backend or cold start could push total latency past the frontend's
        60s timeout and surface as "Forecast unavailable". Concurrent fetch with
        a per-timeframe timeout keeps p95 latency to a single slow call.
        P3-3: MTF 30s TTL per (instrument, timeframes) when FORECAST_CACHE=on
        (default); identical behavior on miss; logs cache_hit.
        P1-5: concurrent misses for the same key are coalesced — the first caller
        fetches and stores, the rest wait on the per-key lock and pick up its
        result instead of firing their own 7-request fan-out.
        """
        timeframes = timeframes or FORECAST_TIMEFRAMES

        # P3-3 additive cache lookup (instance-scoped; miss == legacy path).
        _mtf_key = None
        try:
            from app.research.cache import cache_enabled, make_mtf_key

            if cache_enabled() and getattr(self, "_mtf_cache", None) is not None:
                _mtf_key = make_mtf_key(instrument, list(timeframes))
                _cached = self._mtf_cache.get(_mtf_key)
                if _cached is not None:
                    logger.info(
                        "forecast_mtf_cache_hit",
                        instrument=instrument,
                        cache_hit=True,
                        cache="mtf",
                    )
                    return self._as_cache_hit(_cached)
        except Exception:
            _mtf_key = None

        if _mtf_key is None:
            # Caching off: there is no shared store for waiters to observe, so a
            # lock would only serialize work without saving a single call.
            return await self._fetch_mtf_payload(instrument, list(timeframes), None)

        # P1-5 single-flight: re-check under a per-key lock so concurrent misses
        # for the same (instrument, timeframes) collapse into one provider fetch —
        # the winner stores its result before releasing the lock, so waiters find
        # it and never touch the broker.
        async with self._flight_lock(_mtf_key):
            try:
                _coalesced = self._mtf_cache.get(_mtf_key)
            except Exception:
                _coalesced = None
            if _coalesced is not None:
                logger.info(
                    "forecast_mtf_cache_hit",
                    instrument=instrument,
                    cache_hit=True,
                    cache="mtf",
                    coalesced=True,
                )
                return self._as_cache_hit(_coalesced)
            return await self._fetch_mtf_payload(instrument, list(timeframes), _mtf_key)

    @staticmethod
    def _as_cache_hit(payload: Any) -> Any:
        """Return a cache-hit view of a stored MTF payload (P1-3). Never raises.

        A shallow copy keeps each caller's ``cache_hit`` flag its own (mutating
        the stored object would make an earlier caller read as a hit too) and
        stops callers from mutating the cached value. The candle lists
        themselves stay shared and must be treated as read-only.
        """
        try:
            if isinstance(payload, _MTFCandles):
                return _MTFCandles(
                    payload,
                    resampled_tfs=list(payload.resampled_tfs),
                    cache_hit=True,
                )
            return payload
        except Exception:
            return payload

    async def _fetch_mtf_payload(
        self,
        instrument: str,
        timeframes: List[str],
        mtf_key: Any,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch, resample and cache the MTF candle payload for one instrument.

        Split out of :meth:`fetch_multi_timeframe_candles` so the cache/coalescing
        wrapper above stays readable. Behaviour is unchanged: same per-timeframe
        12s timeout, same 1m→higher-TF resample fallback, same skip-empty store.
        """
        import asyncio

        async def _fetch_one(tf: str) -> tuple[str, List[Dict[str, Any]]]:
            try:
                raw = await asyncio.wait_for(
                    self.market_service.get_candles(instrument, timeframe=tf),
                    timeout=12.0,
                )
                return tf, [_candle_to_dict(c) for c in raw] if raw else []
            except Exception as e:
                logger.warning("forecast_candle_fetch_failed", instrument=instrument, timeframe=tf, error=str(e))
                return tf, []

        results = await asyncio.gather(*[_fetch_one(tf) for tf in timeframes])
        result = _MTFCandles(dict(results))

        # Fallback: if the primary timeframe came back empty (transient history
        # miss / rate limit) but 1m is available, resample locally so we return
        # a degraded forecast instead of a hard 503 "Insufficient ... data".
        # Resampling map covers every supported horizon.
        # P0-2: every TF filled this way is recorded on result.resampled_tfs so
        # forecast() can downgrade (resampled primary -> DEGRADED) and the
        # explain bundle can disclose it. Never silent.
        _resample_minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1D": 1440}
        base_1m = result.get("1m") or []
        if base_1m:
            for tf in timeframes:
                if not result.get(tf) and tf in _resample_minutes and tf != "1m":
                    try:
                        resampled = self._resample_dict_candles(base_1m, _resample_minutes[tf])
                        if resampled:
                            result[tf] = resampled
                            if tf not in result.resampled_tfs:
                                result.resampled_tfs.append(tf)
                            logger.info(
                                "forecast_candle_resampled_fallback",
                                instrument=instrument,
                                timeframe=tf,
                                source_candles=len(base_1m),
                                resampled=len(resampled),
                            )
                    except Exception as e:
                        logger.warning(
                            "forecast_resample_fallback_failed",
                            instrument=instrument,
                            timeframe=tf,
                            error=str(e),
                        )
        # P3-3 store on miss (best-effort; never changes the returned payload).
        try:
            from app.research.cache import NEGATIVE_TTL_S, cache_enabled as _ce

            if _ce() and mtf_key is not None and getattr(self, "_mtf_cache", None) is not None:
                # P1-4: an all-empty picture must never inherit the full 30s read
                # TTL — a transient broker/rate-limit blip would otherwise serve
                # instant "Insufficient candles" long after the operator re-auths
                # and hits Retry. It is still stored briefly (NEGATIVE_TTL_S) so
                # concurrent callers coalesce here instead of queueing up behind
                # the flight lock to re-run the whole fan-out against a dead feed.
                if any(result.values()):
                    self._mtf_cache.set(mtf_key, result)
                    logger.debug(
                        "forecast_mtf_cache_store",
                        instrument=instrument,
                        cache_hit=False,
                        cache="mtf",
                    )
                else:
                    self._mtf_cache.set(mtf_key, result, ttl_seconds=NEGATIVE_TTL_S)
                    logger.info(
                        "forecast_mtf_cache_negative_store",
                        instrument=instrument,
                        cache="mtf",
                        ttl_s=NEGATIVE_TTL_S,
                    )
        except Exception:
            pass
        return result

    @staticmethod
    def _resample_dict_candles(candles_1m: List[Dict[str, Any]], minutes: int) -> List[Dict[str, Any]]:
        """Aggregate 1m dict-candles into a higher timeframe (OHLCV)."""
        if not candles_1m or minutes <= 1:
            return list(candles_1m)
        from datetime import datetime as _dt

        def _parse_ts(v: Any) -> Optional[_dt]:
            if isinstance(v, _dt):
                return v
            if isinstance(v, str):
                try:
                    return _dt.fromisoformat(v.replace("Z", "+00:00"))
                except Exception:
                    return None
            return None

        buckets: Dict[str, List[Dict[str, Any]]] = {}
        order: List[str] = []
        for c in candles_1m:
            ts = _parse_ts(c.get("timestamp"))
            if ts is None:
                continue
            bucket_start = ts.replace(
                minute=(ts.minute // minutes) * minutes if minutes < 60 else 0,
                second=0,
                microsecond=0,
            )
            # For multi-hour buckets, also floor the hour.
            if minutes >= 60:
                bucket_start = bucket_start.replace(hour=(ts.hour // (minutes // 60)) * (minutes // 60))
            key = bucket_start.isoformat()
            if key not in buckets:
                buckets[key] = []
                order.append(key)
            buckets[key].append(c)

        out: List[Dict[str, Any]] = []
        for key in order:
            bucket = buckets[key]
            if not bucket:
                continue
            try:
                out.append(
                    {
                        "open": float(bucket[0]["open"]),
                        "high": float(max(float(x["high"]) for x in bucket)),
                        "low": float(min(float(x["low"]) for x in bucket)),
                        "close": float(bucket[-1]["close"]),
                        "volume": float(sum(float(x.get("volume", 0.0) or 0.0) for x in bucket)),
                        "timestamp": key,
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        return out

    async def run_research_indicators(
        self,
        instrument: str,
        candles: List[Dict[str, Any]],
        options_ctx: Dict[str, Any],
        timeframe: str = "1h",
        forecast_horizon: ForecastHorizon = ForecastHorizon.HORIZON_1H,
        horizon_candles: int = 1,
    ) -> List[IndicatorOutput]:
        """Run all registered research indicators on the primary candle series."""
        outputs: List[IndicatorOutput] = []
        if not candles:
            return outputs

        current_price = float(candles[-1]["close"])

        for ind_id in ENSEMBLE_INDICATOR_IDS:
            indicator = IndicatorRegistry.get(ind_id)
            if indicator is None:
                continue
            try:
                ctx = IndicatorContext(
                    instrument=instrument,
                    timeframe=timeframe,
                    timestamp=datetime.now(timezone.utc),
                    candles=candles,
                    current_price=current_price,
                    options_context=options_ctx,
                    parameters={"horizon": forecast_horizon.value},
                )
                output = await indicator.calculate(ctx)
                # Force the output horizon metadata for downstream consistency
                output.horizon = forecast_horizon
                output.horizon_candles = horizon_candles
                outputs.append(output)
            except Exception as e:
                logger.warning("forecast_indicator_failed", indicator_id=ind_id, error=str(e))
        return outputs

    async def get_ml_forecast(self, instrument: str, horizon_minutes: Optional[int]) -> Optional[Dict[str, Any]]:
        """Get the quantitative ML ensemble forecast for a horizon in minutes.

        Returns None when the horizon has no calibrated ML artifact (e.g. 1m)
        so the ensemble can degrade gracefully instead of failing.
        P3-3: ML 15s TTL per (instrument, horizon_minutes) when
        FORECAST_CACHE=on; identical on miss; logs cache_hit.
        P1-5: concurrent misses for the same key share one model call.
        """
        if horizon_minutes is None:
            return None
        _ml_key = None
        _ML_CACHE_HIT_FLAG.set(False)
        try:
            from app.research.cache import cache_enabled, make_ml_key

            if cache_enabled() and getattr(self, "_ml_cache", None) is not None:
                _ml_key = make_ml_key(instrument, horizon_minutes)
                _hit = self._ml_cache.get(_ml_key)
                if _hit is not None:
                    _ML_CACHE_HIT_FLAG.set(True)
                    logger.info(
                        "forecast_ml_cache_hit",
                        instrument=instrument,
                        horizon_minutes=horizon_minutes,
                        cache_hit=True,
                        cache="ml",
                    )
                    return dict(_hit) if isinstance(_hit, dict) else _hit
        except Exception:
            _ml_key = None

        if _ml_key is None:
            return await self._fetch_ml_payload(instrument, horizon_minutes, None)

        # P1-5 single-flight: concurrent misses for the same (instrument, horizon)
        # share one model call instead of stacking them on the predictor.
        async with self._flight_lock(_ml_key):
            try:
                _coalesced = self._ml_cache.get(_ml_key)
            except Exception:
                _coalesced = None
            if _coalesced is not None:
                _ML_CACHE_HIT_FLAG.set(True)
                logger.info(
                    "forecast_ml_cache_hit",
                    instrument=instrument,
                    horizon_minutes=horizon_minutes,
                    cache_hit=True,
                    cache="ml",
                    coalesced=True,
                )
                return dict(_coalesced) if isinstance(_coalesced, dict) else _coalesced
            return await self._fetch_ml_payload(instrument, horizon_minutes, _ml_key)

    async def _fetch_ml_payload(
        self,
        instrument: str,
        horizon_minutes: Optional[int],
        ml_key: Any,
    ) -> Optional[Dict[str, Any]]:
        """Call the ML predictor (bounded) and cache the normalized response.

        P1-2: the model call is bounded by FORECAST_STAGE_TIMEOUT_S so a hung
        predictor degrades the ML layer to unavailable (confidence capped) rather
        than consuming the whole forecast budget. Returns None on any failure.
        """
        import asyncio

        _timeout = _stage_timeout_s()
        try:
            _call = self.ml_predictor.predict_probabilities(
                symbol=instrument,
                horizon_minutes=horizon_minutes,
            )
            ml_response = (
                await asyncio.wait_for(_call, timeout=_timeout) if _timeout > 0 else await _call
            )
            # Coerce defensively: test doubles (MagicMock) auto-create attrs.
            _mv = getattr(ml_response, "model_version", None)
            _hm = getattr(ml_response, "horizon_minutes", None)
            _ts = getattr(ml_response, "target_spec_version", None)
            out = {
                "bullish_pct": ml_response.bullish_pct,
                "neutral_pct": ml_response.neutral_pct,
                "bearish_pct": ml_response.bearish_pct,
                "predicted_bias": ml_response.predicted_bias,
                "trend_strength": ml_response.trend_strength,
                "confidence_score": ml_response.confidence_score,
                "model_source": ml_response.model_source,
                "calibrated": ml_response.calibrated,
                "model_version": _mv if isinstance(_mv, str) and _mv else None,
                "horizon_minutes": _hm if isinstance(_hm, int) and not isinstance(_hm, bool) else None,
                "target_spec_version": _ts if isinstance(_ts, str) and _ts else None,
            }
            try:
                from app.research.cache import cache_enabled as _ce2

                if _ce2() and ml_key is not None and getattr(self, "_ml_cache", None) is not None:
                    self._ml_cache.set(ml_key, dict(out))
            except Exception:
                pass
            return out
        except asyncio.TimeoutError:
            logger.warning(
                "forecast_ml_timeout",
                instrument=instrument,
                horizon_minutes=horizon_minutes,
                timeout_s=_timeout,
            )
            return None
        except Exception as e:
            logger.warning("forecast_ml_failed", instrument=instrument, error=str(e))
            return None

    async def _get_options_context(self, instrument: str) -> tuple[Dict[str, Any], bool]:
        """Options context with cache, single-flight and a bounded fetch.

        P3-3: 60s TTL per instrument (additive; miss == legacy path).
        P1-2: the fetch is bounded by FORECAST_STAGE_TIMEOUT_S, so a hung F&O
        provider degrades to an unavailable context (the existing
        options-degraded gate + ATR-only targets) instead of eating the whole
        forecast budget.
        P1-5: concurrent misses for the same instrument share one fetch.
        Returns ``(context, cache_hit)``; never raises.
        """
        import asyncio

        _opt_key = None
        try:
            from app.research.cache import cache_enabled, make_options_key

            if cache_enabled() and getattr(self, "_options_cache", None) is not None:
                _opt_key = make_options_key(instrument)
                _hit = self._options_cache.get(_opt_key)
                if isinstance(_hit, dict):
                    logger.info(
                        "forecast_options_cache_hit",
                        instrument=instrument,
                        cache_hit=True,
                        cache="options",
                    )
                    return dict(_hit), True
        except Exception:
            _opt_key = None

        async def _load() -> Dict[str, Any]:
            _timeout = _stage_timeout_s()
            try:
                if _timeout > 0:
                    return await asyncio.wait_for(
                        ResearchOptionsContext.get_context(instrument), timeout=_timeout
                    )
                return await ResearchOptionsContext.get_context(instrument)
            except asyncio.TimeoutError:
                logger.warning(
                    "forecast_options_timeout",
                    instrument=instrument,
                    timeout_s=_timeout,
                )
                return {
                    "instrument": instrument,
                    "available": False,
                    "data_quality": "FAILED",
                    "timeout": True,
                }
            except Exception as e:
                logger.warning("forecast_options_failed", instrument=instrument, error=str(e))
                return {"instrument": instrument, "available": False}

        if _opt_key is None:
            return await _load(), False

        async with self._flight_lock(_opt_key):
            try:
                _coalesced = self._options_cache.get(_opt_key)
            except Exception:
                _coalesced = None
            if isinstance(_coalesced, dict):
                logger.info(
                    "forecast_options_cache_hit",
                    instrument=instrument,
                    cache_hit=True,
                    cache="options",
                    coalesced=True,
                )
                return dict(_coalesced), True
            ctx = await _load()
            try:
                self._options_cache.set(_opt_key, dict(ctx))
            except Exception:
                pass
            return ctx, False

    @staticmethod
    def validate_ml_artifact(
        horizon_minutes: Optional[int],
        ml_forecast: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """P0-4 artifact/spec guard for the ML layer.

        Verifies the response claiming to serve horizon H is really backed by
        the H artifact triple (xgb/lgb/meta suffixed _h{H}):
          meta.horizon_minutes == H, meta.target_spec_version == current spec,
          len(meta.feature_names) == caller feature width.
        On mismatch returns a limitation string (caller must drop the ML layer
        to None + cap confidence) — NEVER silently serve an h15 fallback model
        as h60. The heuristic path (model_source != ensemble) is not an
        artifact mismatch; it is labeled separately via model_source +
        FORECAST_ALLOW_HEURISTIC. Pure except for the meta.json read.

        Bundle doc (rollback): a forecast release = this code +
        backend/app/ml/artifacts/{xgb,lgb,meta}[_h{H}] + TARGET_SPEC_VERSION +
        FEATURE_SCHEMA (trainer.FEATURE_NAMES) + FORECAST_WEIGHTS_VERSION.
        Rollback = redeploy prior code + restore prior artifact triple;
        flipping FORECAST_ALLOW_HEURISTIC=false additionally forces
        heuristic-free (capped) output without a redeploy of artifacts.
        """
        if horizon_minutes is None or ml_forecast is None:
            return None
        if ml_forecast.get("model_source") != "xgboost_lightgbm_ensemble":
            return None
        h = horizon_minutes
        if ml_forecast.get("horizon_minutes") is not None and ml_forecast.get("horizon_minutes") != h:
            return f"artifact-mismatch-h{h}: response horizon {ml_forecast.get('horizon_minutes')} != requested {h}"
        if ml_forecast.get("target_spec_version") not in (None, TARGET_SPEC_VERSION):
            return (
                f"artifact-mismatch-h{h}: response target_spec "
                f"{ml_forecast.get('target_spec_version')} != {TARGET_SPEC_VERSION}"
            )
        try:
            from app.ml.targets import DEFAULT_HORIZON_MINUTES
            from app.ml.trainer import FEATURE_NAMES, artifact_paths

            _, _, meta_path = artifact_paths(h)
            if not meta_path.exists():
                return (
                    f"artifact-mismatch-h{h}: missing h{h} artifact meta "
                    f"({meta_path.name}); refused silent h{DEFAULT_HORIZON_MINUTES} fallback"
                )
            meta = json.loads(meta_path.read_text())
            if meta.get("horizon_minutes") != h:
                return f"artifact-mismatch-h{h}: meta horizon {meta.get('horizon_minutes')} != {h}"
            if meta.get("target_spec_version") != TARGET_SPEC_VERSION:
                return (
                    f"artifact-mismatch-h{h}: meta target_spec "
                    f"{meta.get('target_spec_version')} != {TARGET_SPEC_VERSION}"
                )
            if len(meta.get("feature_names") or []) != len(FEATURE_NAMES):
                return (
                    f"artifact-mismatch-h{h}: meta feature len "
                    f"{len(meta.get('feature_names') or [])} != {len(FEATURE_NAMES)}"
                )
        except ValueError as e:
            return f"artifact-mismatch-h{h}: invalid horizon ({e})"
        except Exception as e:
            return f"artifact-mismatch-h{h}: meta-unreadable ({e})"
        return None

    @staticmethod
    def _direction_to_score(direction: Direction) -> float:
        if direction == Direction.BULLISH:
            return 1.0
        if direction == Direction.BEARISH:
            return -1.0
        return 0.0

    @staticmethod
    def _extract_regime(mtf_features: Dict[str, Any], timeframe: str) -> str:
        """Best-effort regime label: primary TF first, then any TF, else UNKNOWN."""
        try:
            per_tf = (mtf_features or {}).get("per_timeframe", {}) or {}
            for tf in [timeframe, *per_tf.keys()]:
                feats = ((per_tf.get(tf) or {}).get("features") or {})
                regime = feats.get("regime")
                if isinstance(regime, str) and regime:
                    return regime
        except Exception:
            pass
        return "UNKNOWN"

    @staticmethod
    def _extract_session(mtf_features: Dict[str, Any], timeframe: str) -> str:
        """Best-effort session label from per-TF feature payloads (ensemble-level).

        forecast() refines this from the primary candle timestamp directly.
        """
        try:
            per_tf = (mtf_features or {}).get("per_timeframe", {}) or {}
            for tf in [timeframe, *per_tf.keys()]:
                feats = ((per_tf.get(tf) or {}).get("features") or {})
                session = feats.get("session")
                if isinstance(session, str) and session:
                    return session
        except Exception:
            pass
        return "UNKNOWN"

    @staticmethod
    def _parse_candle_ts(value: Any) -> Optional[datetime]:
        """Parse a candle timestamp (iso string or datetime) to aware UTC."""
        try:
            if isinstance(value, datetime):
                ts = value
            elif isinstance(value, str) and value:
                ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
            else:
                return None
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts.astimezone(timezone.utc)
        except Exception:
            return None

    @staticmethod
    def _trim_mtf_features_for_snapshot(mtf_features: Dict[str, Any]) -> Dict[str, Any]:
        """Trim the MTF feature payload for snapshot persistence.

        Keeps alignment + per-TF evidence (quant/momentum/volume/regime/
        session/price) and drops heavy blobs (ta_suite full output, options
        detail) so snapshots stay reconstructable without ballooning storage.
        """
        try:
            per_tf = ((mtf_features or {}).get("per_timeframe") or {})
            trimmed: Dict[str, Any] = {}
            for tf, payload in per_tf.items():
                feats = ((payload or {}).get("features") or {})
                if not isinstance(feats, dict):
                    continue
                trimmed[tf] = {
                    k: feats[k]
                    for k in (
                        "instrument", "timeframe", "timestamp", "session",
                        "current_price", "regime", "quant",
                        "momentum_dynamics", "volume_dynamics", "data_quality",
                    )
                    if k in feats
                }
            out = {
                "instrument": (mtf_features or {}).get("instrument"),
                "alignment": ((mtf_features or {}).get("alignment") or {}),
                "per_timeframe": trimmed,
            }
            for k in ("missing_timeframes", "resampled_timeframes"):
                if isinstance((mtf_features or {}).get(k), list):
                    out[k] = list((mtf_features or {})[k])
            return out
        except Exception:
            return {"instrument": (mtf_features or {}).get("instrument")}

    def ensemble_forecast(
        self,
        mtf_features: Dict[str, Any],
        indicator_outputs: List[IndicatorOutput],
        ml_forecast: Optional[Dict[str, Any]],
        options_ctx: Dict[str, Any],
        current_price: float,
        horizon: str = "1h",
        abstain_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Combine all mechanics layers into a single directional forecast.

        ``abstain_threshold`` overrides the FORECAST_ABSTAIN_T env default
        (Cycle-1 second candidate 0.60 passes explicitly); it only takes
        effect on the flag-gated logistic-v2 path.
        """
        cfg = HORIZON_CONFIG.get(horizon, HORIZON_CONFIG["1h"])
        timeframe: str = cfg["timeframe"]
        forecast_horizon: ForecastHorizon = cfg["forecast_horizon"]
        horizon_candles: int = cfg["horizon_candles"]

        # Layer 1: MTF alignment score (-100 to +100), horizon-blended.
        # Legacy bug: every horizon (even 1m) used the same unanimous global
        # vote, so a 1m dump could never flip while 1h/4h stayed bullish.
        # Now short horizons blend in their own primary-TF fast momentum.
        alignment = mtf_features.get("alignment", {}) if isinstance(mtf_features.get("alignment", {}), dict) else {}
        overall_bias = alignment.get("overall_bias", "NEUTRAL")
        try:
            alignment_score = float(alignment.get("alignment_score", 0.0))
        except (TypeError, ValueError):
            alignment_score = 0.0
        mtf_global = alignment_score if overall_bias == "BULLISH" else -alignment_score if overall_bias == "BEARISH" else 0.0

        # Layer 5 (early): need primary features for both the MTF blend and
        # the fast structure layer — all from already-available data.
        per_tf = mtf_features.get("per_timeframe", {}) if isinstance(mtf_features.get("per_timeframe", {}), dict) else {}
        feat_primary = (per_tf.get(timeframe, {}) or {}).get("features", {})
        if not feat_primary:
            # Fall back to any available timeframe's features
            for tf_payload in per_tf.values():
                if (tf_payload or {}).get("features"):
                    feat_primary = tf_payload["features"]
                    break
        if not isinstance(feat_primary, dict):
            feat_primary = {}
        _primary_fast = _primary_fast_score(feat_primary, current_price)
        try:
            _blend = float(HORIZON_MTF_GLOBAL_BLEND.get(horizon, 1.0))
        except (TypeError, ValueError):
            _blend = 1.0
        _blend = max(0.0, min(1.0, _blend))
        mtf_normalized = _clamp(_blend * mtf_global + (1.0 - _blend) * _primary_fast, -100.0, 100.0)

        # Layer 2: Research indicators average
        ind_score = 0.0
        ind_confidence = 0.0
        ind_count = 0
        for out in indicator_outputs:
            ind_score += out.score
            ind_confidence += out.confidence
            ind_count += 1
        if ind_count > 0:
            ind_score = ind_score / ind_count
            ind_confidence = ind_confidence / ind_count

        # Layer 3: ML ensemble
        ml_score = 0.0
        ml_confidence = 0.0
        if ml_forecast:
            bullish = ml_forecast.get("bullish_pct", 33.3)
            bearish = ml_forecast.get("bearish_pct", 33.3)
            neutral = ml_forecast.get("neutral_pct", 33.4)
            ml_score = ((bullish - bearish) / 100.0) * 100.0
            ml_confidence = max(bullish, bearish, neutral) / 100.0

        # Layer 4: Options context
        opt_score = 0.0
        pcr_oi = float(options_ctx.get("pcr_oi", 1.0) or 1.0)
        call_wall = options_ctx.get("call_wall")
        put_wall = options_ctx.get("put_wall")
        max_pain = options_ctx.get("max_pain")
        # PCR > 1 suggests put writing / bullish positioning
        opt_score += max(-30.0, min(30.0, (pcr_oi - 1.0) * 80.0))
        # Gravitational pull toward max pain
        if max_pain and max_pain > 0:
            pain_dist_pct = ((max_pain - current_price) / current_price) * 100.0
            opt_score += max(-20.0, min(20.0, pain_dist_pct * 15.0))
        # Wall proximity: continuous exponential decay instead of binary cliff
        if call_wall and call_wall > current_price:
            call_dist_pct = ((call_wall - current_price) / current_price) * 100.0
            if call_dist_pct < 0.4:
                opt_score -= 20.0
            else:
                prox = math.exp(-(((call_dist_pct - 0.4) / 0.5) ** 2))
                opt_score -= round(20.0 * prox, 2)
        if put_wall and put_wall < current_price:
            put_dist_pct = ((current_price - put_wall) / current_price) * 100.0
            if put_dist_pct < 0.4:
                opt_score += 20.0
            else:
                prox = math.exp(-(((put_dist_pct - 0.4) / 0.5) ** 2))
                opt_score += round(20.0 * prox, 2)
        opt_score = max(-100.0, min(100.0, opt_score))

        # Layer 5: Primary-timeframe structure (fast momentum-aware).
        # Old: supertrend (±30) + RSI (±20) only — too slow for 1m/5m.
        # New: same base + EMA stack / VWAP / ATR-normalized ret_1/ret_5 /
        # acceleration via _primary_fast_score, horizon-blended so 1h
        # fixtures stay bullish while 1m dumps flip fast.
        quant_primary = (feat_primary or {}).get("quant", {})
        if not isinstance(quant_primary, dict):
            quant_primary = {}
        structure_score = 0.0
        st_dir = quant_primary.get("supertrend_dir", "NEUTRAL")
        if st_dir == "BULLISH":
            structure_score += 30.0
        elif st_dir == "BEARISH":
            structure_score -= 30.0
        rsi_primary = quant_primary.get("rsi_14", 50.0)
        try:
            rsi_primary = float(rsi_primary)
        except (TypeError, ValueError):
            rsi_primary = 50.0
        structure_score += max(-20.0, min(20.0, (rsi_primary - 50.0) * 0.8))
        structure_score = max(-100.0, min(100.0, structure_score))
        # Blend with fast momentum (no-op when no momentum data present).
        try:
            _sf = float(HORIZON_STRUCT_FAST_BLEND.get(horizon, 0.5))
        except (TypeError, ValueError):
            _sf = 0.5
        _sf = max(0.0, min(1.0, _sf))
        try:
            structure_score = _clamp((1.0 - _sf) * float(structure_score) + _sf * float(_primary_fast), -100.0, 100.0)
        except (TypeError, ValueError):
            pass

        # Extract regime and session for regime-adaptive weighting
        regime_v2 = self._extract_regime(mtf_features, timeframe)
        session_v2 = self._extract_session(mtf_features, timeframe)
        # Horizon-aware weights (redistributes missing-ML share). 1h equals
        # the legacy LAYER_WEIGHTS path so v1 contract tests are unaffected.
        if horizon in HORIZON_LAYER_WEIGHTS:
            weights = _resolve_horizon_weights(horizon, ml_available=bool(ml_forecast))
        else:
            weights = get_regime_layer_weights(regime_v2)
            if not ml_forecast and float(weights.get("ml", 0.0)) > 0:
                weights = _resolve_horizon_weights("1h", ml_available=False)

        # Weighted ensemble using horizon-aware weights
        final_score = (
            float(weights.get("mtf_alignment", 0.0)) * mtf_normalized +
            float(weights.get("indicators", 0.0)) * ind_score +
            float(weights.get("ml", 0.0)) * ml_score +
            float(weights.get("options", 0.0)) * opt_score +
            float(weights.get("structure", 0.0)) * structure_score
        )
        final_score = round(max(-100.0, min(100.0, final_score)), 2)

        # Composite confidence
        alignment_confidence = alignment_score / 100.0
        confidence_inputs = [alignment_confidence, ind_confidence, ml_confidence]
        confidence = round(sum(confidence_inputs) / len(confidence_inputs), 3)

        # Direction & targets (ATR of the primary timeframe scales naturally).
        # Horizon-specific cutoffs: 1m needs only ±10 to call a scalp move,
        # 1h keeps the legacy ±20 so v1 contract tests are unaffected.
        try:
            _dir_th = float(HORIZON_DIRECTION_THRESHOLD.get(horizon, 20.0))
        except (TypeError, ValueError):
            _dir_th = 20.0
        if final_score >= _dir_th:
            direction = Direction.BULLISH
        elif final_score <= -_dir_th:
            direction = Direction.BEARISH
        else:
            direction = Direction.NEUTRAL

        atr_primary = quant_primary.get("atr_14", current_price * 0.005)
        try:
            atr_primary = float(atr_primary)
        except (TypeError, ValueError):
            atr_primary = current_price * 0.005
        if not atr_primary or atr_primary <= 0:
            atr_primary = current_price * 0.005
        if direction == Direction.BULLISH:
            target_price = round(current_price + (1.8 * atr_primary), 2)
            invalidation_price = round(current_price - (1.1 * atr_primary), 2)
            expected_range_default = None
        elif direction == Direction.BEARISH:
            target_price = round(current_price - (1.8 * atr_primary), 2)
            invalidation_price = round(current_price + (1.1 * atr_primary), 2)
            expected_range_default = None
        else:
            target_price = None
            invalidation_price = None
            half_band = round(atr_primary * 0.75, 2)
            expected_range_default = {
                "lower": round(current_price - half_band, 2),
                "mid": round(current_price, 2),
                "upper": round(current_price + half_band, 2),
            }

        result = {
            "instrument": mtf_features.get("instrument"),
            "timeframe": timeframe,
            "forecast_horizon": forecast_horizon.value,
            "horizon_candles": horizon_candles,
            "current_price": round(current_price, 2),
            "direction": direction.value,
            "tactical_bias": direction.value,
            "engine": "tactical_horizon_bias",
            "score": final_score,
            "confidence": confidence,
            "target_price": target_price,
            "invalidation_price": invalidation_price,
            # Neutral verdicts carry the expected band here (directional
            # verdicts carry target/invalidation prices with expected_range
            # None — see risk_v2.compute_targets for the v2 path).
            "expected_range": expected_range_default,
            "layer_scores": {
                "mtf_alignment": round(mtf_normalized, 2),
                "indicators": round(ind_score, 2),
                "ml": round(ml_score, 2),
                "options": round(opt_score, 2),
                "structure": round(structure_score, 2),
            },
            "layer_weights": weights,
            "ml_forecast": ml_forecast,
            "indicator_outputs": [out.model_dump() for out in indicator_outputs],
            "mtf_features": mtf_features,
            "options_context": options_ctx,
        }

        # --- Forecast 1h-v2 base contract (P0-1) alongside v1 keys ---
        # v1 keys above (direction/score/layer_scores/target/invalidation) are
        # intentionally untouched for frontend compat. Gates in forecast() may
        # narrow confidence / override status+direction afterwards.
        probabilities = score_to_probabilities_v2(final_score)
        raw_confidence = round(max(probabilities.values()), 4)
        ml_source = (ml_forecast or {}).get("model_source") or "unavailable"
        ml_model_version = (ml_forecast or {}).get("model_version") or None
        result.update(
            {
                "forecast_version": f"{horizon}-v2",
                "status": "RESEARCH",
                "probabilities": probabilities,
                "confidence": raw_confidence,
                "raw_confidence": raw_confidence,
                "regime": regime_v2,
                "session": session_v2,
                "settleable": True,
                "settle_reason": "pending-forecast-gate",
                "data_quality": "HEALTHY",
                "model_source": ml_source,
                "calibrated": False,
                "model_version": ml_model_version or "trend-forecast-v1",
                "calibrator_version": FORECAST_V2_CALIBRATOR_VERSION,
                "weights_version": _forecast_weights_version(),
                # P1-1: v2 contract labels settle under v2-atr-em-session
                # (ATR14_1h, EM risk-only). v1 ensemble keys above untouched;
                # ML artifact guard (validate_ml_artifact) still pins v1.
                "target_spec_version": TARGET_SPEC_VERSION_V2,
                "prediction_id": None,
                "snapshot_id": None,
                "limitations": [],
            }
        )

        # --- P2-4/P2-5 additive branch: logistic-v2 + calibrator + risk_v2 ---
        # Flag-gated (FORECAST_V2_MODEL=logistic-v2) and 1h-only. Default v1
        # output above is byte-identical when the flag is unset. Never raises:
        # any v2 failure degrades to the v1 base with a limitation.
        if horizon == "1h" and _forecast_v2_model_flag() == FORECAST_V2_MODEL_V2:
            try:
                v2_limitations: List[str] = []
                instrument_v2 = mtf_features.get("instrument") or "UNKNOWN"

                # 1. Raw probs: model_v2 when available, else interim softmax.
                p_raw = dict(probabilities)
                m2_probs, m2_info = _try_model_v2_raw_probs(
                    mtf_features, indicator_outputs, ml_forecast,
                    options_ctx, current_price, horizon,
                )
                if m2_probs is not None:
                    p_raw = m2_probs
                    if m2_info.get("model_version"):
                        ml_model_version = m2_info["model_version"]
                    if m2_info.get("model_source"):
                        ml_source = m2_info["model_source"]
                if m2_info.get("limitation"):
                    v2_limitations.append(m2_info["limitation"])
                # 1b. Stacker v1 (flag-gated, artifact-gated): learned blend over
                # layer scores + regime/session/dte/iv. Missing artifact or
                # FORECAST_STACKER!=on -> keep p_raw untouched (honest fallback).
                try:
                    import os as _os

                    if (_os.getenv("FORECAST_STACKER", "off") or "off").strip().lower() in ("on", "true", "1", "yes"):
                        from app.ml.stacker_v1 import build_stacker_row, predict_stacker

                        _row = build_stacker_row(
                            {"mtf": mtf_normalized, "indicators": ind_score, "ml": ml_score,
                             "options": opt_score, "structure": structure_score},
                            regime=regime_v2, session=session_v2,
                            dte_days=(options_ctx or {}).get("days_to_expiry"),
                            iv_rank=None, missing_count=0,
                        )
                        _sp = predict_stacker(_row)
                        if _sp is not None:
                            p_raw = {"bullish": _sp["bullish"], "neutral": _sp["neutral"], "bearish": _sp["bearish"]}
                            ml_source = "stacker_v1"
                            ml_model_version = "stacker-v1"
                        else:
                            v2_limitations.append("stacker-missing-fallback-layers")
                except Exception as _se:
                    v2_limitations.append(f"stacker-failed-fallback-layers:{str(_se)[:80]}")
                raw_conf_v2 = round(max(p_raw.values()), 4)

                # 2. Calibrate (persisted CalibratorV1 when present).
                p_cal, calibrated_v2, cal_ver_v2, cal_lim = _try_calibrate_probs(
                    p_raw, instrument_v2
                )
                if cal_lim:
                    v2_limitations.append(cal_lim)
                conf_v2 = round(max(p_cal.values()), 4)

                # 3. Risk v2: EM-aware targets, ATR-only fallback + limitation.
                from app.research import risk_v2 as _risk_v2

                # P1-1: EM is only real when the F&O snapshot is. options_context
                # returns synthetic defaults (atm_iv 15.0 / dte 1.0) with
                # available=False and data_quality EMPTY/FAILED, so sizing targets
                # from those would publish EM-backed levels derived from data we
                # already know is absent. Synthetic -> ATR-only + limitation.
                em_v2 = None
                _opt_ctx = dict(options_ctx or {})
                _opt_is_live = bool(_opt_ctx.get("available", True)) and (
                    str(_opt_ctx.get("data_quality", "LIVE") or "LIVE").upper() == "LIVE"
                )
                if _opt_is_live:
                    try:
                        em_v2 = _risk_v2.expected_move(
                            current_price,
                            _opt_ctx.get("atm_iv"),
                            _opt_ctx.get("days_to_expiry"),
                        )
                    except Exception:
                        em_v2 = None
                else:
                    v2_limitations.append("em-unavailable-synthetic-options")
                try:
                    ttc_v2 = (feat_primary or {}).get("minutes_to_close")
                except Exception:
                    ttc_v2 = None

                # 4. Abstention gate (volatile/closing bump included).
                thr_v2 = get_abstain_threshold(regime_v2, session_v2,
                                               override=abstain_threshold)
                verdict = apply_abstention_v2(direction.value, conf_v2, thr_v2)
                dir_v2 = verdict["direction"]
                if verdict["limitation"]:
                    v2_limitations.append(verdict["limitation"])

                # Direction-aware structural barrier (distance, not price):
                # bullish invalidation sits below -> put-wall distance;
                # bearish invalidation sits above -> call-wall distance.
                barrier_v2 = None
                try:
                    cw_v2 = (options_ctx or {}).get("call_wall")
                    pw_v2 = (options_ctx or {}).get("put_wall")
                    if dir_v2 == Direction.BULLISH.value and pw_v2 is not None:
                        barrier_v2 = float(current_price) - float(pw_v2)
                        if not barrier_v2 > 0:
                            barrier_v2 = None
                    elif dir_v2 == Direction.BEARISH.value and cw_v2 is not None:
                        barrier_v2 = float(cw_v2) - float(current_price)
                        if not barrier_v2 > 0:
                            barrier_v2 = None
                except (TypeError, ValueError):
                    barrier_v2 = None

                targets_v2 = _risk_v2.compute_targets(
                    dir_v2, current_price, atr_primary, em_v2,
                    barrier=barrier_v2, time_to_close_min=ttc_v2, H=60.0,
                )
                basis_v2 = targets_v2.get("basis") or "ATR-only"
                if basis_v2 == "ATR-only":
                    v2_limitations.append("target_basis=ATR-only")

                result["probabilities"] = p_cal
                result["confidence"] = conf_v2
                result["raw_confidence"] = raw_conf_v2
                result["direction"] = dir_v2
                result["status"] = verdict["status"]
                result["target_price"] = targets_v2.get("target_price")
                result["invalidation_price"] = targets_v2.get("invalidation_price")
                result["expected_range"] = targets_v2.get("expected_range")
                result["target_basis"] = basis_v2
                result["abstain_threshold"] = round(thr_v2, 4)
                result["calibrated"] = calibrated_v2
                result["calibrator_version"] = cal_ver_v2
                result["model_source"] = ml_source
                result["model_version"] = ml_model_version or "trend-forecast-v1"
                result["limitations"] = list(result.get("limitations") or []) + v2_limitations
            except Exception as e:
                logger.debug("forecast_v2_branch_skipped", error=str(e))

        # Immutable explain bundle (pure, never throws — local import avoids cycle)
        try:
            from app.signals.explain import build_forecast_explain

            result["explain"] = build_forecast_explain(
                result, mtf_features, indicator_outputs, ml_forecast, options_ctx, current_price
            )
        except Exception as e:
            logger.debug("forecast_explain_build_skipped", error=str(e))
            result["explain"] = None
        return result

    async def forecast(
        self,
        instrument: str,
        horizon: str = "1h",
        record: bool = True,
        session: Any = None,
        include_layers: bool = False,
        include_explain: bool = True,
        mtf_candles: Optional[Any] = None,
        anchor_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Generate a directional forecast for the given horizon and optionally persist it.

        ``session`` (optional AsyncSession) is the durable store of record: when
        supplied, the snapshot + immutable prediction are written through it with
        strict failure semantics and ``result["persisted"]`` reports whether a
        complete record exists. Without it, behaviour is unchanged (bounded
        in-memory fallback; ``persisted`` stays False).

        ``mtf_candles`` / ``anchor_price`` are board-run injection points (see
        :meth:`TacticalHorizonEngine.forecast_board`): a shared MTF snapshot to
        read instead of fetching, and a shared spot to anchor
        target/invalidation off instead of this horizon's own last candle
        close. Both default to None, which preserves the standalone
        point-in-time behaviour exactly.

        P1-2: the whole orchestration runs under a ``FORECAST_DEADLINE_S``
        watchdog. A timeout raises :class:`ForecastDeadlineExceeded` instead of
        returning a verdict that could not be computed (this module never
        fabricates a forecast), so a stuck stage becomes a fast, labeled failure
        rather than a request that outlives the client's own timeout.
        ``include_layers=True`` re-attaches the heavy debug layers (P1-6), while
        ``include_explain=False`` drops the explain bundle from the response
        (P1-7: the query param clients already sent is now honoured; recordings
        keep the bundle either way, so auditability is unaffected).
        """
        import asyncio

        budget = forecast_deadline_s()
        if budget <= 0:
            return await self._forecast_inner(
                instrument,
                horizon,
                record=record,
                session=session,
                include_layers=include_layers,
                include_explain=include_explain,
                mtf_candles=mtf_candles,
                anchor_price=anchor_price,
            )
        _deadline_start = time.monotonic()
        try:
            return await asyncio.wait_for(
                self._forecast_inner(
                    instrument,
                    horizon,
                    record=record,
                    session=session,
                    include_layers=include_layers,
                    include_explain=include_explain,
                    mtf_candles=mtf_candles,
                    anchor_price=anchor_price,
                ),
                timeout=budget,
            )
        except asyncio.TimeoutError:
            _elapsed_ms = round((time.monotonic() - _deadline_start) * 1000.0, 2)
            _bump_runtime("deadline_exceeded", stamp=True)
            logger.warning(
                "forecast_deadline_exceeded",
                instrument=instrument,
                horizon=horizon,
                budget_s=budget,
                elapsed_ms=_elapsed_ms,
            )
            raise ForecastDeadlineExceeded(
                f"Forecast for {instrument} {horizon} exceeded its {budget:g}s budget "
                f"({_elapsed_ms:.0f}ms elapsed). Retry shortly or raise "
                f"FORECAST_DEADLINE_S."
            ) from None

    async def _forecast_inner(
        self,
        instrument: str,
        horizon: str = "1h",
        record: bool = True,
        session: Any = None,
        include_layers: bool = False,
        include_explain: bool = True,
        mtf_candles: Optional[Any] = None,
        anchor_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Compute one forecast — see :meth:`forecast` for the public contract."""
        cfg = HORIZON_CONFIG.get(horizon)
        if cfg is None:
            raise ValueError(f"Unsupported forecast horizon '{horizon}'. Supported: {sorted(HORIZON_CONFIG)}")
        timeframe: str = cfg["timeframe"]
        forecast_horizon: ForecastHorizon = cfg["forecast_horizon"]
        horizon_candles: int = cfg["horizon_candles"]
        indicator_id: str = cfg["indicator_id"]

        # P3-3 SLO clock (time.monotonic; recorded as latency_ms + structlog).
        _t_start = time.monotonic()
        _cache_hit = {"mtf": False, "options": False, "ml": False}

        _bump_runtime("calls")
        logger.info("forecast_start", instrument=instrument, horizon=horizon)

        # 1. Fetch all timeframe candles (MTF cache lives inside
        # fetch_multi_timeframe_candles; hit flag mirrored for completion log).
        # A board run injects one shared snapshot so every horizon resolves
        # the same candles (see TacticalHorizonEngine.forecast_board).
        if mtf_candles is None:
            mtf_candles = await self.fetch_multi_timeframe_candles(instrument)
        # P1-3: provenance travels with the payload (see _MTFCandles.cache_hit).
        try:
            if bool(getattr(mtf_candles, "cache_hit", False)):
                _cache_hit["mtf"] = True
        except Exception:
            pass
        primary_candles = mtf_candles.get(timeframe, [])
        if not primary_candles:
            available = sorted([tf for tf, cs in mtf_candles.items() if cs])
            raise ValueError(
                f"Insufficient {timeframe} candle data for {instrument} "
                f"(available: {available or 'none'}). The broker history API returned "
                f"no candles — re-auth FYERS if the daily token expired, then Retry."
            )

        # 2. Options context (P3-3 60s TTL; P1-2 bounded; P1-5 coalesced).
        options_ctx, _opt_cache_hit = await self._get_options_context(instrument)
        if _opt_cache_hit:
            _cache_hit["options"] = True

        # 3. Multi-timeframe features
        mtf_features = FeatureLayer.compute_multi_timeframe_features(
            instrument=instrument,
            timeframe_candles=mtf_candles,
            options_ctx=options_ctx,
        )

        # 4. Research indicators on the primary timeframe
        indicator_outputs = await self.run_research_indicators(
            instrument=instrument,
            candles=primary_candles,
            options_ctx=options_ctx,
            timeframe=timeframe,
            forecast_horizon=forecast_horizon,
            horizon_candles=horizon_candles,
        )

        # 5. ML forecast for this horizon (None for horizons without artifacts)
        ml_forecast = await self.get_ml_forecast(instrument, cfg["ml_minutes"])
        # P1-3: provenance from the ContextVar set inside get_ml_forecast (per
        # task), never from a shared instance attribute.
        try:
            if bool(_ML_CACHE_HIT_FLAG.get()):
                _cache_hit["ml"] = True
        except Exception:
            pass
        ml_limitations: List[str] = []

        # P0-4: artifact/spec guard — drop wrong-horizon models, never remap.
        artifact_limitation = self.validate_ml_artifact(cfg["ml_minutes"], ml_forecast)
        if artifact_limitation:
            logger.warning(
                "forecast_ml_artifact_mismatch",
                instrument=instrument,
                horizon=horizon,
                limitation=artifact_limitation,
            )
            ml_limitations.append(artifact_limitation)
            ml_forecast = None
        if ml_forecast and ml_forecast.get("model_source") == "heuristic_ensemble" and not _heuristic_allowed():
            ml_limitations.append("heuristic-disabled-by-FORECAST_ALLOW_HEURISTIC")
            ml_forecast = None

        # 6. Ensemble (adds the v2 base contract: probabilities, versions, ...)
        # A board run injects one shared anchor so every horizon's target /
        # invalidation is computed off the same print; standalone runs keep
        # the horizon's own last candle close.
        current_price = float(primary_candles[-1]["close"])
        if anchor_price is not None:
            try:
                _anchor = float(anchor_price)
            except (TypeError, ValueError):
                _anchor = 0.0
            if _anchor > 0:
                current_price = _anchor
                logger.info(
                    "forecast_anchor_override",
                    instrument=instrument,
                    horizon=horizon,
                    anchor_price=_anchor,
                )
        # Provenance for the P0-2 gates + explain bundle (explain reads these
        # keys to report missing/resampled timeframes).
        missing_tfs = [tf for tf in FORECAST_TIMEFRAMES if not (mtf_candles.get(tf) or [])]
        resampled_tfs = list(getattr(mtf_candles, "resampled_tfs", []) or [])
        result = self.ensemble_forecast(
            mtf_features=mtf_features,
            indicator_outputs=indicator_outputs,
            ml_forecast=ml_forecast,
            options_ctx=options_ctx,
            current_price=current_price,
            horizon=horizon,
        )
        try:
            mtf_features["missing_timeframes"] = missing_tfs
            mtf_features["resampled_timeframes"] = resampled_tfs
        except Exception:
            pass

        # --- P0-2 data-quality + settleability + late-session gates ---
        now_utc = datetime.now(timezone.utc)
        ml_available = ml_forecast is not None
        options_available = bool(options_ctx.get("available", True))
        options_dq = str(options_ctx.get("data_quality", "LIVE") or "LIVE")
        options_degraded = (not options_available) or options_dq.upper() in (
            "DEGRADED", "STALE", "FAILED", "EMPTY",
        )
        # Session from the primary candle timestamp (point-in-time, not wall clock).
        primary_ts = self._parse_candle_ts((primary_candles[-1] or {}).get("timestamp")) or now_utc
        try:
            session_label = classify_session_ist(primary_ts).value
        except Exception:
            session_label = result.get("session") or "UNKNOWN"
        # Settleability of the [now, now+H] window (covers post-14:30 IST,
        # holidays, specials, weekends via the shared NSE calendar rule).
        # H is the forecast's own horizon (HORIZON_CONFIG minutes) — a fixed
        # 60m window wrongly abstains sub-hour forecasts in the last hour
        # (e.g. a 1m call at 14:34 settles 14:35, long before the close).
        # Floored at 5m: validate_horizon's minimum supported ML horizon.
        try:
            from app.ml.sessions import classify_window

            try:
                _settle_minutes = int((cfg or {}).get("minutes") or 60)
            except (TypeError, ValueError):
                _settle_minutes = 60
            _settle_minutes = max(5, _settle_minutes)
            settle = classify_window(instrument, now_utc, _settle_minutes)
            settleable = bool(settle.get("settleable", False))
            settle_reason = str(settle.get("reason", "unknown") or "unknown")
        except Exception as e:
            settleable = False
            settle_reason = f"settle-check-failed:{e}"

        limitations: List[str] = list(result.get("limitations") or [])
        limitations.extend(ml_limitations)
        if ml_forecast is not None and ml_forecast.get("model_source") == "heuristic_ensemble":
            limitations.append("model-source-heuristic-uncalibrated")
        # Standing P0 honesty note: interim softmax, no calibrator yet.
        # Skipped only once a real calibrator has scaled the probabilities
        # (P2-4: calibrated=true on the logistic-v2 path).
        if not bool(result.get("calibrated")):
            limitations.append("interim-softmax-T40-uncalibrated")

        # P2-5: preserve a v2 abstention verdict from ensemble_forecast
        # (v1 ensembles always report RESEARCH here, so this is a no-op off-flag).
        _ensemble_status = result.get("status")
        status = _ensemble_status if _ensemble_status in FORECAST_V2_STATUSES else "RESEARCH"
        data_quality = "HEALTHY"
        confidence_cap = 1.0
        raw_confidence = float(result.get("raw_confidence") or result.get("confidence") or 0.0)

        if len(missing_tfs) >= 2 or timeframe in resampled_tfs:
            # ABSTAIN stays ABSTAIN (already the most conservative verdict);
            # data-quality still records DEGRADED + reasons.
            if status != "ABSTAIN":
                status = "DEGRADED"
            data_quality = "DEGRADED"
            if len(missing_tfs) >= 2:
                limitations.append(f"missing-timeframes:{sorted(missing_tfs)}")
            if timeframe in resampled_tfs:
                limitations.append(f"resampled-{timeframe}-from-1m")
        if not ml_available:
            confidence_cap = min(confidence_cap, 0.55)
            limitations.append("ml-unavailable-confidence-capped-0.55")
        if options_degraded:
            if status == "RESEARCH":
                status = "DEGRADED"
            if data_quality == "HEALTHY":
                data_quality = "DEGRADED"
            limitations.append(
                "options-unavailable-degraded" if not options_available else f"options-degraded:{options_dq}"
            )
        if not settleable:
            confidence_cap = min(confidence_cap, 0.45)
            data_quality = "UNSETTLEABLE"
            limitations.append(f"crosses-session-close — excluded from accuracy ({settle_reason})")
            if abs(float(result.get("score") or 0.0)) < 35:
                # Weak signal crossing the close: abstain rather than invent
                # conviction. Score/probabilities are preserved for audit; the
                # direction verdict is forced to NEUTRAL.
                result["direction"] = Direction.NEUTRAL.value
                result["target_price"] = None
                result["invalidation_price"] = None
                status = "ABSTAIN"
                limitations.append("late-session-forced-neutral:|score|<35")
            elif status == "RESEARCH":
                status = "DEGRADED"
        if data_quality == "HEALTHY" and (result.get("model_source") == "heuristic_ensemble"):
            data_quality = "HEURISTIC"

        result["status"] = status
        result["data_quality"] = data_quality
        result["limitations"] = limitations
        result["settleable"] = settleable
        result["settle_reason"] = settle_reason
        result["session"] = session_label
        result["confidence"] = round(min(raw_confidence, confidence_cap), 4)
        result["raw_confidence"] = round(raw_confidence, 4)

        # Propagate gate outcomes into the explain bundle (rebuilt against the
        # final verdict so data_health/penalties match what the API returns).
        # Done BEFORE persistence so the recorded prediction carries the gated
        # explain, not the pre-gate ensemble draft.
        try:
            from app.signals.explain import build_forecast_explain

            result["explain"] = build_forecast_explain(
                result, mtf_features, indicator_outputs, ml_forecast, options_ctx, current_price
            )
        except Exception as e:
            logger.debug("forecast_explain_build_skipped", error=str(e))
        try:
            explain = result.get("explain")
            if isinstance(explain, dict):
                health = dict(explain.get("data_health") or {})
                health.update(
                    {
                        "missing_timeframes": missing_tfs,
                        "resampled_timeframes": resampled_tfs,
                        "degraded": bool(missing_tfs or resampled_tfs or not ml_available or options_degraded or not settleable),
                        "ml_available": ml_available,
                        "options_available": options_available,
                        "options_data_quality": options_dq,
                        "settleable": settleable,
                        "settle_reason": settle_reason,
                        "data_quality": result.get("data_quality"),
                        "status": result.get("status"),
                    }
                )
                explain["data_health"] = health
                penalties = list(explain.get("penalties") or [])
                for lim in result.get("limitations") or []:
                    if lim not in penalties:
                        penalties.append(lim)
                explain["penalties"] = penalties
                explain["limitations"] = list(result.get("limitations") or [])
                explain["status"] = result.get("status")
        except Exception as e:
            logger.debug("forecast_explain_enrich_skipped", error=str(e))

        # 7. Snapshot + immutable prediction (P0-3). Never persist a prediction
        # without its snapshot: snapshot failure degrades to record=false
        # behaviour (no prediction row, prediction_id stays None).
        #
        # P0-1/P0-2 (durable store): when the caller supplies a session, both
        # writes go through it with strict=True, so a failed insert raises
        # PersistenceError instead of returning an id for a row that was never
        # written. Without a session the legacy bounded in-memory fallback is
        # used and result["persisted"] stays False.
        #
        # P0-3 (cross-process idempotency): before inserting, ask the DB whether
        # this (instrument, indicator, minute bucket) was already recorded (e.g.
        # by another worker). If so, reuse its ids and write nothing — the
        # in-memory replay map cannot see other processes, so without this guard
        # the same logical forecast would be inserted twice.
        prediction_id: Optional[str] = None
        snapshot_id: Optional[str] = None
        _bucket_start = now_utc.replace(second=0, microsecond=0)
        existing_bucket = None
        if record and session is not None:
            existing_bucket = await PredictionService.find_in_minute_bucket(
                session,
                instrument=instrument,
                indicator_id=indicator_id,
                bucket_start=_bucket_start,
                bucket_end=_bucket_start + timedelta(minutes=1),
            )
        if record and existing_bucket:
            prediction_id = existing_bucket.get("prediction_id")
            snapshot_id = existing_bucket.get("snapshot_id")
            if snapshot_id:
                _bump_runtime("bucket_replays")
                logger.info(
                    "forecast_bucket_already_recorded",
                    instrument=instrument,
                    horizon=horizon,
                    prediction_id=prediction_id,
                )
            else:
                # Row predates snapshot enforcement: reuse the prediction id but
                # report it as not fully persisted, and never write a duplicate.
                logger.warning(
                    "forecast_bucket_row_without_snapshot",
                    instrument=instrument,
                    horizon=horizon,
                    prediction_id=prediction_id,
                )
        elif record:
            try:
                from app.research.enums import DataQualityStatus as _DQ

                snap_features = self._trim_mtf_features_for_snapshot(mtf_features)
                # Keep the full v2 verdict reconstructable from the snapshot.
                snap_features["v2"] = {
                    "forecast_version": result.get("forecast_version"),
                    "status": result.get("status"),
                    "data_quality": result.get("data_quality"),
                    "settleable": settleable,
                    "settle_reason": settle_reason,
                    "session": session_label,
                    "regime": result.get("regime"),
                    "limitations": list(limitations),
                    "model_source": result.get("model_source"),
                    "weights_version": result.get("weights_version"),
                    "target_spec_version": result.get("target_spec_version"),
                    # P2-4/P2-5 audit extras (present only on the v2 path).
                    "calibrated": result.get("calibrated"),
                    "calibrator_version": result.get("calibrator_version"),
                    "target_basis": result.get("target_basis"),
                    "abstain_threshold": result.get("abstain_threshold"),
                    "expected_range": result.get("expected_range"),
                }
                data_degraded = bool(
                    len(missing_tfs) >= 2 or timeframe in resampled_tfs or options_degraded
                )
                snapshot = ResearchSnapshot(
                    snapshot_id=f"snap_{uuid.uuid4().hex[:12]}",
                    instrument=instrument,
                    timeframe=timeframe,
                    timestamp=now_utc,
                    price=result["current_price"],
                    regime=result.get("regime"),
                    session=session_label,
                    features=snap_features,
                    options_context=options_ctx,
                    data_quality=_DQ.DEGRADED if data_degraded else _DQ.LIVE,
                    created_at=now_utc,
                )
                snapshot_id = await SnapshotService.record_snapshot(
                    snapshot, session=session, strict=session is not None
                )
            except Exception as e:
                logger.warning("forecast_persist_failed", instrument=instrument, error=str(e))
                prediction_id = None
                if status == "RESEARCH":
                    status = "DEGRADED"
                    result["status"] = status
                if data_quality == "HEALTHY":
                    data_quality = "DEGRADED"
                    result["data_quality"] = data_quality
                if isinstance(e, PersistenceError):
                    # DB write rejected/rolled back: say which stage, never claim
                    # a record. A written snapshot is kept for audit when only
                    # the prediction insert failed.
                    _stage = "snapshot" if "snapshot" in str(e) else "prediction"
                    _bump_runtime("persist_failures", stamp=True)
                    limitations.append(f"persistence-failed:{_stage}")
                elif snapshot_id:
                    # Snapshot recorded, prediction not: keep the snapshot id.
                    limitations.append("prediction-unavailable")
                else:
                    snapshot_id = None
                    limitations.append("snapshot-unavailable")
                result["limitations"] = limitations
            if snapshot_id:
                if session is not None:
                    # Self-healing FK guard: the trend_forecast_* indicator ids
                    # are never seeded, so without this the strict prediction
                    # insert below always fails the FK. A failure here only
                    # logs — the insert stays honest about its own outcome.
                    try:
                        await _ensure_forecast_indicator_definition(
                            session, indicator_id=indicator_id, horizon=horizon
                        )
                    except Exception as e:
                        logger.warning(
                            "forecast_indicator_definition_ensure_failed",
                            instrument=instrument, indicator_id=indicator_id,
                            error=str(e),
                        )
                pred = ResearchPrediction(
                    prediction_id=f"forecast_{horizon}_{uuid.uuid4().hex[:12]}",
                    indicator_id=indicator_id,
                    indicator_version="1.0.0",
                    instrument=instrument,
                    timeframe=timeframe,
                    timestamp=now_utc,
                    current_price=result["current_price"],
                    direction=Direction(result["direction"]),
                    score=result["score"],
                    confidence=result["confidence"],
                    component_values={
                        "layer_scores": result["layer_scores"],
                        "ml_forecast": ml_forecast,
                        "indicator_ids": [out.indicator_id for out in indicator_outputs],
                        "explain": result.get("explain"),
                        "forecast_version": result.get("forecast_version"),
                        "probabilities": result.get("probabilities"),
                        "status": result.get("status"),
                        "data_quality": result.get("data_quality"),
                        "settleable": settleable,
                        "settle_reason": settle_reason,
                        "limitations": limitations,
                        "snapshot_id": snapshot_id,
                        "weights_version": result.get("weights_version"),
                        "target_spec_version": result.get("target_spec_version"),
                        # P2-4/P2-5 audit extras (None off-flag; harmless).
                        "raw_confidence": result.get("raw_confidence"),
                        "calibrated": result.get("calibrated"),
                        "calibrator_version": result.get("calibrator_version"),
                        "target_basis": result.get("target_basis"),
                        "abstain_threshold": result.get("abstain_threshold"),
                        "expected_range": result.get("expected_range"),
                    },
                    forecast_horizon=forecast_horizon,
                    horizon_candles=horizon_candles,
                    target_price=result["target_price"],
                    invalidation_price=result["invalidation_price"],
                    snapshot_id=snapshot_id,
                )
                try:
                    prediction_id = await PredictionService.record_prediction(
                        pred, session=session, strict=session is not None
                    )
                except Exception as e:
                    # Never claim a prediction that was not written: degrade
                    # honestly and keep the (already recorded) snapshot id for
                    # audit. Without this the insert error would escape the
                    # snapshot handler and 500 the request.
                    logger.warning(
                        "forecast_prediction_record_failed",
                        instrument=instrument,
                        error=str(e),
                    )
                    prediction_id = None
                    if status == "RESEARCH":
                        status = "DEGRADED"
                        result["status"] = status
                    if data_quality == "HEALTHY":
                        data_quality = "DEGRADED"
                        result["data_quality"] = data_quality
                    if isinstance(e, PersistenceError):
                        _bump_runtime("persist_failures", stamp=True)
                        limitations.append("persistence-failed:prediction")
                    else:
                        limitations.append("prediction-unavailable")
                    result["limitations"] = limitations
        recorded_now = bool(prediction_id and snapshot_id and not existing_bucket)
        # Durable truth: ids alone (memory fallback, or a session that was never
        # supplied) must never read as "recorded in the database".
        persisted = bool(session is not None and prediction_id and snapshot_id)
        result["prediction_id"] = prediction_id
        result["snapshot_id"] = snapshot_id
        # P0-1/P0-2: the durable-storage truth. Consumers must read this instead
        # of inferring "recorded" from a non-null prediction_id.
        result["persisted"] = persisted

        # P1-6: the heavy layer payloads are opt-in. They dominated the response
        # (every TF's full features incl. ta_suite, the dumped indicator outputs,
        # the raw F&O context), were deep-copied into the replay cache, and are
        # read by no consumer — the explain bundle carries the curated evidence.
        if not include_layers:
            for _heavy_key in FORECAST_HEAVY_LAYER_KEYS:
                result.pop(_heavy_key, None)

        # P1-7: the explain bundle is client-controllable. The persisted snapshot
        # and prediction above always carry it, so dropping it here only trims the
        # HTTP payload (a caller polling for the verdict can opt out).
        if not include_explain:
            result.pop("explain", None)

        # P0-1 contract validation: log + DEGRADED on failure, never 500.
        # (Missing primary 1h still raises 503 above — never synthetic.)
        # Validate against the *recorded* fact: a failed/unavailable persistence
        # already appends its own limitation, so don't also emit
        # "missing-snapshot-for-record" for a response that honestly reports
        # persisted=false.
        try:
            contract_errors = validate_forecast_v2(
                result, record=bool(record and persisted)
            )
        except Exception as e:
            contract_errors = [f"validator-crashed:{e}"]
        if contract_errors:
            _bump_runtime("contract_invalid", stamp=True)
            logger.warning(
                "forecast_v2_contract_invalid",
                instrument=instrument,
                horizon=horizon,
                errors=contract_errors,
            )
            if result.get("status") == "RESEARCH":
                result["status"] = "DEGRADED"
            if result.get("data_quality") == "HEALTHY":
                result["data_quality"] = "DEGRADED"
            result["limitations"] = list(result.get("limitations") or []) + [
                f"contract-validation:{';'.join(contract_errors)}"
            ]
            try:
                explain = result.get("explain")
                if isinstance(explain, dict):
                    explain["limitations"] = list(result.get("limitations") or [])
                    explain["status"] = result.get("status")
                    explain_penalties = list(explain.get("penalties") or [])
                    for lim in result.get("limitations") or []:
                        if lim not in explain_penalties:
                            explain_penalties.append(lim)
                    explain["penalties"] = explain_penalties
            except Exception:
                pass

        # P3-3 SLO + idempotency finalize (additive; never changes verdict).
        try:
            _latency_ms = round((time.monotonic() - _t_start) * 1000.0, 2)
        except Exception:
            _latency_ms = 0.0
        result["latency_ms"] = _latency_ms
        try:
            result["cache_hit"] = dict(_cache_hit)
        except Exception:
            result["cache_hit"] = {"mtf": False, "options": False, "ml": False}
        # P2-3: runtime counters surfaced by /monitoring/forecast-health. These
        # events never become prediction rows, so the rolling DB metrics could
        # not see them.
        try:
            _bump_runtime(None, latency_ms=_latency_ms)
            _final_status = str(result.get("status") or "")
            if _final_status == "DEGRADED":
                _bump_runtime("degraded")
            elif _final_status == "ABSTAIN":
                _bump_runtime("abstain")
        except Exception:
            pass
        # A call that found the bucket already recorded did not mint a new row;
        # report it as a replay (it is idempotent by construction).
        _idempotent_replay = bool(existing_bucket)
        # Minute-bucket idempotency: same instrument+H+minute+version replays
        # the same prediction_id instead of minting a new uuid. Only on
        # successful record=True persists by *this* call; record=False, a
        # bucket already recorded by another worker, and snapshot-failure
        # bypass so gates stay honest and no duplicate row is ever claimed.
        if recorded_now and prediction_id and snapshot_id:
            try:
                _wv = str(result.get("weights_version") or _forecast_weights_version())
                _mf = _forecast_v2_model_flag()
                _ikey = MinuteBucketReplay.make_key(instrument, horizon, now_utc, _wv, _mf)
                _old = _IDEMPOTENCY.get(_ikey)
                if _old is not None:
                    _old_pid, _old_sid, _old_res = _old
                    try:
                        _mem_has = _old_pid in getattr(PredictionService, "_memory_predictions", {})
                    except Exception:
                        _mem_has = False
                    if _mem_has and isinstance(_old_res, dict):
                        # Drop the duplicate fresh rows; replay the original.
                        try:
                            PredictionService._memory_predictions.pop(prediction_id, None)
                        except Exception:
                            pass
                        try:
                            SnapshotService._memory_snapshots.pop(snapshot_id, None)
                        except Exception:
                            pass
                        import copy as _copy

                        try:
                            _replay = _copy.deepcopy(_old_res)
                        except Exception:
                            _replay = dict(_old_res)
                        # Fresh SLO timing for this call; ids stay stable.
                        _replay["latency_ms"] = _latency_ms
                        try:
                            _replay["cache_hit"] = dict(_cache_hit)
                        except Exception:
                            pass
                        _replay["idempotent_replay"] = True
                        _replay["prediction_id"] = _old_pid
                        _replay["snapshot_id"] = _old_sid
                        logger.info(
                            "forecast_idempotent_replay",
                            instrument=instrument,
                            horizon=horizon,
                            prediction_id=_old_pid,
                            cache_hit=_cache_hit,
                            latency_ms=_latency_ms,
                        )
                        result = _replay
                        _idempotent_replay = True
                        prediction_id = _old_pid
                        snapshot_id = _old_sid
                if not _idempotent_replay:
                    # Store final (post-gate, post-validation) result for replay.
                    try:
                        import copy as _copy2

                        try:
                            _store_res = _copy2.deepcopy(result)
                        except Exception:
                            _store_res = dict(result)
                        # P1-6: never retain the heavy layers in the replay map,
                        # even for an include_layers=True caller (the replay is a
                        # cached reply; debug layers are not replayed).
                        for _heavy_key in FORECAST_HEAVY_LAYER_KEYS:
                            _store_res.pop(_heavy_key, None)
                        _store_res["idempotent_replay"] = False
                        _IDEMPOTENCY.put(_ikey, prediction_id, snapshot_id, _store_res)
                    except Exception:
                        pass
            except Exception:
                pass
        try:
            result.setdefault("idempotent_replay", _idempotent_replay)
        except Exception:
            pass

        logger.info(
            "forecast_complete",
            instrument=instrument,
            horizon=horizon,
            direction=result["direction"],
            score=result["score"],
            confidence=result["confidence"],
            status=result.get("status"),
            data_quality=result.get("data_quality"),
            settleable=settleable,
            settle_reason=settle_reason,
            model_source=result.get("model_source"),
            weights_version=result.get("weights_version"),
            target_spec_version=result.get("target_spec_version"),
            calibrated=result.get("calibrated"),
            latency_ms=result.get("latency_ms"),
            cache_hit=result.get("cache_hit"),
            idempotent_replay=result.get("idempotent_replay", False),
        )
        return result


class TacticalHorizonEngine(TrendForecaster):
    """Institutional Tactical Horizon Bias engine.

    Provides probabilistic directional bias, expected range, and risk invalidation
    across multi-timeframe horizons (1m / 5m / 15m / 30m / 60m), replacing rigid
    deterministic 'forecast' assumptions with regime-conditioned expected moves.
    """

    async def get_ml_1h_forecast(self, instrument: str) -> Optional[Dict[str, Any]]:
        """Get the quantitative ML ensemble forecast for a 60-minute horizon."""
        return await self.get_ml_forecast(instrument, 60)

    async def get_tactical_bias(
        self,
        instrument: str,
        horizon: str = "1h",
        record: bool = True,
        session: Any = None,
    ) -> Dict[str, Any]:
        """Generate a tactical horizon bias and optionally persist it immutably."""
        return await self.forecast(
            instrument=instrument, horizon=horizon, record=record, session=session
        )

    async def _resolve_board_anchor(
        self, instrument: str, mtf_candles: Any
    ) -> Tuple[float, str, Optional[str]]:
        """Resolve one shared spot for a board run: live LTP first, 1m close fallback.

        Returns ``(price, source, ts_iso)``. Never fabricates: raises
        ValueError when neither a usable quote nor any candle exists.
        """
        try:
            quote = await self.market_service.get_quote(instrument)
            ltp = float(getattr(quote, "ltp", 0.0) or 0.0)
            if ltp > 0:
                status = getattr(getattr(quote, "status", None), "value", None) or str(
                    getattr(quote, "status", "UNKNOWN")
                )
                ts = getattr(quote, "timestamp", None)
                ts_iso = (
                    ts.isoformat()
                    if hasattr(ts, "isoformat")
                    else (str(ts) if ts else None)
                )
                return ltp, f"quote:{status}", ts_iso
        except Exception as e:
            logger.debug(
                "board_anchor_quote_failed", instrument=instrument, error=str(e)[:120]
            )
        try:
            tf_map = mtf_candles if isinstance(mtf_candles, dict) else {}
            for tf in ("1m", "5m", "15m", "30m", "1h"):
                candles = tf_map.get(tf) or []
                if not candles:
                    continue
                last = candles[-1] or {}
                if isinstance(last, dict):
                    price = float(last.get("close") or 0.0)
                    ts = last.get("timestamp")
                else:
                    price = float(getattr(last, "close", 0.0) or 0.0)
                    ts = getattr(last, "timestamp", None)
                if price > 0:
                    ts_iso = (
                        ts.isoformat()
                        if hasattr(ts, "isoformat")
                        else (str(ts) if ts else None)
                    )
                    return price, f"{tf}-close", ts_iso
        except Exception as e:
            logger.debug(
                "board_anchor_candle_failed", instrument=instrument, error=str(e)[:120]
            )
        raise ValueError(
            f"No usable anchor price for {instrument} (quote + all candles empty)"
        )

    async def forecast_board(
        self,
        instrument: str,
        record: bool = True,
        session_factory: Any = None,
        include_layers: bool = False,
        include_explain: bool = True,
    ) -> Dict[str, Any]:
        """Run every BOARD_HORIZONS forecast off ONE shared MTF snapshot + anchor.

        Five independent point-in-time runs resolve five different spots (each
        card reads its own horizon's last candle close at its own fetch
        instant, plus per-horizon cache ages) — the board then renders them as
        if they were one snapshot. This fans the horizons out concurrently
        from a single ``fetch_multi_timeframe_candles`` payload and a single
        anchor print, and stamps every card with the same ``generated_at``.

        ``session_factory`` (optional) is a zero-arg callable returning an
        async-context-manager session (see
        ``app.core.database.get_async_session_factory``). Each horizon gets
        its own session because one AsyncSession cannot be shared across
        concurrent coroutines. With ``record=True`` but no factory, behaviour
        matches the single-horizon endpoint without a DB (in-memory fallback,
        ``persisted`` False).

        A horizon that fails (deadline / insufficient data / unexpected error)
        degrades to ``errors[horizon]`` instead of failing the board; only a
        board with zero successful horizons raises.
        """
        import asyncio
        from datetime import datetime, timezone

        shared_candles = await self.fetch_multi_timeframe_candles(instrument)
        anchor_price, anchor_source, anchor_ts = await self._resolve_board_anchor(
            instrument, shared_candles
        )

        async def _one(horizon: str) -> Tuple[str, Dict[str, Any]]:
            try:
                if record and session_factory is not None:
                    async with session_factory() as sess:
                        res = await self.forecast(
                            instrument,
                            horizon,
                            record=True,
                            session=sess,
                            include_layers=include_layers,
                            include_explain=include_explain,
                            mtf_candles=shared_candles,
                            anchor_price=anchor_price,
                        )
                else:
                    res = await self.forecast(
                        instrument,
                        horizon,
                        record=record,
                        session=None,
                        include_layers=include_layers,
                        include_explain=include_explain,
                        mtf_candles=shared_candles,
                        anchor_price=anchor_price,
                    )
                return horizon, res
            except ForecastDeadlineExceeded as e:
                logger.warning(
                    "board_horizon_deadline",
                    instrument=instrument,
                    horizon=horizon,
                    error=str(e)[:150],
                )
                return horizon, {"error": f"deadline_exceeded: {e}"}
            except ValueError as e:
                logger.warning(
                    "board_horizon_insufficient_data",
                    instrument=instrument,
                    horizon=horizon,
                    error=str(e)[:150],
                )
                return horizon, {"error": str(e)}
            except Exception as e:
                logger.warning(
                    "board_horizon_failed",
                    instrument=instrument,
                    horizon=horizon,
                    error=str(e)[:150],
                )
                return horizon, {"error": f"board horizon failed: {e}"}

        pairs = await asyncio.gather(*[_one(h) for h in BOARD_HORIZONS])
        board_ts = datetime.now(timezone.utc).isoformat()
        horizons: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        for horizon, payload in pairs:
            if isinstance(payload, dict) and "error" not in payload:
                payload["generated_at"] = board_ts
                payload["anchor_price"] = anchor_price
                payload["anchor_source"] = anchor_source
                horizons[horizon] = payload
            else:
                try:
                    errors[horizon] = str((payload or {}).get("error") or "unknown error")
                except Exception:
                    errors[horizon] = "unknown error"
        if not horizons:
            raise ValueError(errors.get(BOARD_HORIZONS[0], "board run produced no horizons"))
        persisted = all(bool((h or {}).get("persisted")) for h in horizons.values())
        return {
            "instrument": instrument,
            "generated_at": board_ts,
            "anchor_price": anchor_price,
            "anchor_source": anchor_source,
            "anchor_ts": anchor_ts,
            "persisted": persisted,
            "horizons": horizons,
            "errors": errors,
        }


# Backward-compatible class alias
TrendForecast1H = TacticalHorizonEngine

# Module-level singletons for convenient import
tactical_horizon_engine = TacticalHorizonEngine()
trend_forecaster = tactical_horizon_engine
trend_forecast_1h = tactical_horizon_engine

