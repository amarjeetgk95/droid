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
"""

from datetime import datetime, timezone
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
from app.research.predictions import PredictionService, SnapshotService
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


def _forecast_weights_version() -> str:
    """Weights bundle tag. P0 only ships v1 (rollback = flip env + redeploy)."""
    raw = (os.getenv("FORECAST_WEIGHTS_VERSION", "v1") or "v1").strip() or "v1"
    return f"forecast-{raw}"


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
    is preserved for all existing callers.
    """

    def __init__(self, *args: Any, resampled_tfs: Optional[List[str]] = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.resampled_tfs: List[str] = list(resampled_tfs or [])


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
        """
        import asyncio

        timeframes = timeframes or FORECAST_TIMEFRAMES

        # P3-3 additive cache lookup (instance-scoped; miss == legacy path).
        _mtf_key = None
        try:
            self._last_mtf_cache_hit = False
        except Exception:
            pass
        try:
            from app.research.cache import cache_enabled, make_mtf_key

            if cache_enabled() and getattr(self, "_mtf_cache", None) is not None:
                _mtf_key = make_mtf_key(instrument, list(timeframes))
                _cached = self._mtf_cache.get(_mtf_key)
                if _cached is not None:
                    try:
                        self._last_mtf_cache_hit = True
                    except Exception:
                        pass
                    logger.info(
                        "forecast_mtf_cache_hit",
                        instrument=instrument,
                        cache_hit=True,
                        cache="mtf",
                    )
                    return _cached
        except Exception:
            _mtf_key = None

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
            from app.research.cache import cache_enabled as _ce

            if _ce() and _mtf_key is not None and getattr(self, "_mtf_cache", None) is not None:
                self._mtf_cache.set(_mtf_key, result)
                logger.debug(
                    "forecast_mtf_cache_store",
                    instrument=instrument,
                    cache_hit=False,
                    cache="mtf",
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
        """
        if horizon_minutes is None:
            return None
        _ml_key = None
        try:
            self._last_ml_cache_hit = False
        except Exception:
            pass
        try:
            from app.research.cache import cache_enabled, make_ml_key

            if cache_enabled() and getattr(self, "_ml_cache", None) is not None:
                _ml_key = make_ml_key(instrument, horizon_minutes)
                _hit = self._ml_cache.get(_ml_key)
                if _hit is not None:
                    try:
                        self._last_ml_cache_hit = True
                    except Exception:
                        pass
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
        try:
            ml_response = await self.ml_predictor.predict_probabilities(
                symbol=instrument,
                horizon_minutes=horizon_minutes,
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

                if _ce2() and _ml_key is not None and getattr(self, "_ml_cache", None) is not None:
                    self._ml_cache.set(_ml_key, dict(out))
            except Exception:
                pass
            return out
        except Exception as e:
            logger.warning("forecast_ml_failed", instrument=instrument, error=str(e))
            return None

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

        # Layer 1: MTF alignment score (-100 to +100)
        alignment = mtf_features.get("alignment", {})
        overall_bias = alignment.get("overall_bias", "NEUTRAL")
        alignment_score = float(alignment.get("alignment_score", 0.0))
        mtf_normalized = alignment_score if overall_bias == "BULLISH" else -alignment_score if overall_bias == "BEARISH" else 0.0

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
        # Wall proximity
        if call_wall and call_wall > current_price:
            call_dist_pct = ((call_wall - current_price) / current_price) * 100.0
            if call_dist_pct < 0.4:
                opt_score -= 20.0
        if put_wall and put_wall < current_price:
            put_dist_pct = ((current_price - put_wall) / current_price) * 100.0
            if put_dist_pct < 0.4:
                opt_score += 20.0
        opt_score = max(-100.0, min(100.0, opt_score))

        # Layer 5: Primary-timeframe structure
        per_tf = mtf_features.get("per_timeframe", {})
        feat_primary = (per_tf.get(timeframe, {}) or {}).get("features", {})
        if not feat_primary:
            # Fall back to any available timeframe's features
            for tf_payload in per_tf.values():
                if (tf_payload or {}).get("features"):
                    feat_primary = tf_payload["features"]
                    break
        quant_primary = (feat_primary or {}).get("quant", {})
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

        # Weighted ensemble
        final_score = (
            LAYER_WEIGHTS["mtf_alignment"] * mtf_normalized +
            LAYER_WEIGHTS["indicators"] * ind_score +
            LAYER_WEIGHTS["ml"] * ml_score +
            LAYER_WEIGHTS["options"] * opt_score +
            LAYER_WEIGHTS["structure"] * structure_score
        )
        final_score = round(max(-100.0, min(100.0, final_score)), 2)

        # Composite confidence
        alignment_confidence = alignment_score / 100.0
        confidence_inputs = [alignment_confidence, ind_confidence, ml_confidence]
        confidence = round(sum(confidence_inputs) / len(confidence_inputs), 3)

        # Direction & targets (ATR of the primary timeframe scales naturally)
        if final_score >= 20.0:
            direction = Direction.BULLISH
        elif final_score <= -20.0:
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
        elif direction == Direction.BEARISH:
            target_price = round(current_price - (1.8 * atr_primary), 2)
            invalidation_price = round(current_price + (1.1 * atr_primary), 2)
        else:
            target_price = None
            invalidation_price = None

        result = {
            "instrument": mtf_features.get("instrument"),
            "timeframe": timeframe,
            "forecast_horizon": forecast_horizon.value,
            "horizon_candles": horizon_candles,
            "current_price": round(current_price, 2),
            "direction": direction.value,
            "score": final_score,
            "confidence": confidence,
            "target_price": target_price,
            "invalidation_price": invalidation_price,
            "layer_scores": {
                "mtf_alignment": round(mtf_normalized, 2),
                "indicators": round(ind_score, 2),
                "ml": round(ml_score, 2),
                "options": round(opt_score, 2),
                "structure": round(structure_score, 2),
            },
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
        regime_v2 = self._extract_regime(mtf_features, timeframe)
        session_v2 = self._extract_session(mtf_features, timeframe)
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

                try:
                    em_v2 = _risk_v2.expected_move(
                        current_price,
                        (options_ctx or {}).get("atm_iv"),
                        (options_ctx or {}).get("days_to_expiry"),
                    )
                except Exception:
                    em_v2 = None
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
    ) -> Dict[str, Any]:
        """Generate a directional forecast for the given horizon and optionally persist it."""
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

        logger.info("forecast_start", instrument=instrument, horizon=horizon)

        # 1. Fetch all timeframe candles (MTF cache lives inside
        # fetch_multi_timeframe_candles; hit flag mirrored for completion log).
        mtf_candles = await self.fetch_multi_timeframe_candles(instrument)
        try:
            if bool(getattr(self, "_last_mtf_cache_hit", False)):
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

        # 2. Options context (P3-3: 60s TTL per instrument, additive).
        _opt_key = None
        options_ctx: Dict[str, Any]
        try:
            from app.research.cache import cache_enabled as _ce_o, make_options_key as _mok

            if _ce_o() and getattr(self, "_options_cache", None) is not None:
                _opt_key = _mok(instrument)
                _opt_hit = self._options_cache.get(_opt_key)
                if isinstance(_opt_hit, dict):
                    options_ctx = dict(_opt_hit)
                    _cache_hit["options"] = True
                    logger.info(
                        "forecast_options_cache_hit",
                        instrument=instrument,
                        cache_hit=True,
                        cache="options",
                    )
                else:
                    options_ctx = await ResearchOptionsContext.get_context(instrument)
                    try:
                        self._options_cache.set(_opt_key, dict(options_ctx))
                    except Exception:
                        pass
            else:
                options_ctx = await ResearchOptionsContext.get_context(instrument)
        except Exception:
            # Fallback: never let the cache break the legacy path.
            try:
                options_ctx = await ResearchOptionsContext.get_context(instrument)
            except Exception:
                options_ctx = {"instrument": instrument, "available": False}

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
        try:
            if bool(getattr(self, "_last_ml_cache_hit", False)):
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
        current_price = float(primary_candles[-1]["close"])
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
        # Settleability of the [now, now+60m] window (covers post-14:30 IST,
        # holidays, specials, weekends via the shared NSE calendar rule).
        try:
            from app.ml.sessions import classify_window

            settle = classify_window(instrument, now_utc, 60)
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
        prediction_id: Optional[str] = None
        snapshot_id: Optional[str] = None
        if record:
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
                snapshot_id = await SnapshotService.record_snapshot(snapshot)
            except Exception as e:
                logger.warning("forecast_snapshot_failed", instrument=instrument, error=str(e))
                snapshot_id = None
                if status == "RESEARCH":
                    status = "DEGRADED"
                    result["status"] = status
                if data_quality == "HEALTHY":
                    data_quality = "DEGRADED"
                    result["data_quality"] = data_quality
                limitations.append("snapshot-unavailable")
                result["limitations"] = limitations
            if snapshot_id:
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
                prediction_id = await PredictionService.record_prediction(pred)
        result["prediction_id"] = prediction_id
        result["snapshot_id"] = snapshot_id

        # P0-1 contract validation: log + DEGRADED on failure, never 500.
        # (Missing primary 1h still raises 503 above — never synthetic.)
        try:
            contract_errors = validate_forecast_v2(result, record=record)
        except Exception as e:
            contract_errors = [f"validator-crashed:{e}"]
        if contract_errors:
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
        _idempotent_replay = False
        # Minute-bucket idempotency: same instrument+H+minute+version replays
        # the same prediction_id instead of minting a new uuid. Only on
        # successful record=True persists; record=False and snapshot-failure
        # bypass so gates stay honest.
        if record and prediction_id and snapshot_id:
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


class TrendForecast1H(TrendForecaster):
    """Backwards-compatible 1-hour forecaster (thin wrapper over TrendForecaster)."""

    async def get_ml_1h_forecast(self, instrument: str) -> Optional[Dict[str, Any]]:
        """Get the quantitative ML ensemble forecast for a 60-minute horizon."""
        return await self.get_ml_forecast(instrument, 60)

    async def forecast(
        self,
        instrument: str,
        record: bool = True,
    ) -> Dict[str, Any]:
        """Generate a 1-hour trend forecast and optionally persist it immutably."""
        return await super().forecast(instrument=instrument, horizon="1h", record=record)


# Module-level singletons for convenient import
trend_forecaster = TrendForecaster()
trend_forecast_1h = TrendForecast1H()
