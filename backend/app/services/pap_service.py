"""Price Action Prediction (PAP) live service â€” shadow/advisory only.

Computes the multi-horizon (3m/5m/10m) UP/NEUTRAL/DOWN distribution from REAL
market data on every call. No caching of predictions, no fabricated values:

- Quotes and 1m/5m candles come from ``MarketService`` (broker-backed).
- Indicator math (ADX/DMI, Bollinger, Fisher, LR slope, session VWAP) is
  deterministic over those real candles; insufficient data yields ``None``
  (surfaced as unavailable), never a synthetic number.
- The 5m horizon reuses the trained XGBoost/LightGBM ensemble when its
  artifact triple exists (currently the shared h15 snapshot serves it with
  ``calibrated=false``); 3m/10m have no trained artifact yet and are served
  by the honest heuristic fallback path (``model_source=heuristic_ensemble``,
  ``calibrated=false``) computed from the same real feature vector.
- DROID alignment is a READ-ONLY look at the signal FSM's active rows for
  display. This module never creates/cancels/modifies orders, positions,
  risk limits, gates, FSM state, or broker sessions.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal

import structlog

from app.ml.feature_extractor import extract_ml_feature_vector
from app.market_core.indicators import calculate_adx, calculate_bollinger_bands
from app.services.market_service import MarketService
from app.services.regime_service import regime_service

logger = structlog.get_logger()

PAP_INSTRUMENTS = ("NIFTY", "BANKNIFTY", "SENSEX")
PAP_HORIZONS = (3, 5, 10)

PAP_MODEL_NAME = "XGBoost"
PAP_FEATURE_SCHEMA = "f10-v1"
PAP_MODEL_FAMILY = "XGBoost-LightGBM-Ensemble"

# Freshness windows for the live header (seconds).
PAP_LIVE_MAX_S = 10.0
PAP_DELAYED_MAX_S = 30.0


class PapUnavailable(Exception):
    """Raised when no honest PAP payload can be produced."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# Deterministic market-state math (pure functions over real candles)
# ---------------------------------------------------------------------------

def fisher_transform(closes: List[float], period: int = 9) -> float | None:
    """Fisher Transform of price over ``period`` bars.

    Returns None when fewer than ``period + 1`` closes exist. Bounded to
    [-4, +4] for display stability.
    """
    if len(closes) < period + 1:
        return None
    window = closes[-(period + 1):]
    hi = max(window)
    lo = min(window)
    if hi <= lo:
        return 0.0
    # Normalized position of the latest close in the window.
    value = 2.0 * ((window[-1] - lo) / (hi - lo)) - 1.0
    value = max(-0.999, min(0.999, value))
    try:
        fish = 0.5 * math.log((1.0 + value) / (1.0 - value))
    except ValueError:
        return 0.0
    return round(max(-4.0, min(4.0, fish)), 4)


def linreg_slope(closes: List[float], lookback: int = 20) -> float | None:
    """Least-squares slope (points per bar) over the last ``lookback`` closes."""
    if len(closes) < lookback or lookback < 2:
        return None
    window = closes[-lookback:]
    n = len(window)
    mean_x = (n - 1) / 2.0
    mean_y = sum(window) / n
    denom = sum((i - mean_x) ** 2 for i in range(n))
    if denom == 0:
        return 0.0
    slope = sum((i - mean_x) * (p - mean_y) for i, p in enumerate(window)) / denom
    return round(slope, 6)


def session_vwap(candles: List[Any]) -> float | None:
    """Cumulative session VWAP from 1m candles (typical price x volume)."""
    num = 0.0
    den = 0.0
    for c in candles:
        try:
            tp = (float(c.high) + float(c.low) + float(c.close)) / 3.0
            v = float(c.volume or 0.0)
        except Exception:
            continue
        if v <= 0:
            continue
        num += tp * v
        den += v
    if den <= 0:
        return None
    return round(num / den, 2)


def heuristic_probs_from_features(features) -> tuple[float, float, float]:
    """Honest heuristic fallback (NOT a trained prediction).

    Mirrors ``MLPredictor`` fallback math so PAP 3m/10m (no trained artifact
    yet) stay consistent with the predictor's degraded path. Callers MUST
    label the result ``model_source=heuristic_ensemble`` + ``calibrated=False``.
    """
    w_st = 0.25 * features.supertrend_signal
    w_rsi = 0.20 * features.rsi_norm
    w_pcr = 0.15 * features.pcr_oi_deviation
    w_basis = 0.15 * (1.0 if features.futures_basis_pct > 0 else -1.0) * min(
        1.0, abs(features.futures_basis_pct) * 200
    )
    w_ema = 0.15 * min(1.0, max(-1.0, features.price_above_ema20 * 100))
    w_pivot = 0.10 * features.pivot_position
    raw = w_st + w_rsi + w_pcr + w_basis + w_ema + w_pivot
    adx_factor = features.adx_strength
    if raw > 0:
        bull_logit = 1.0 + (raw * 2.5) * (0.5 + 0.5 * adx_factor)
        bear_logit = 1.0 - (raw * 1.5)
        neut_logit = 1.0 + (1.0 - adx_factor) * 1.2
    else:
        bull_logit = 1.0 + (raw * 1.5)
        bear_logit = 1.0 - (raw * 2.5) * (0.5 + 0.5 * adx_factor)
        neut_logit = 1.0 + (1.0 - adx_factor) * 1.2
    exp_bull = math.exp(max(-5.0, min(5.0, bull_logit)))
    exp_bear = math.exp(max(-5.0, min(5.0, bear_logit)))
    exp_neut = math.exp(max(-5.0, min(5.0, neut_logit)))
    total = exp_bull + exp_bear + exp_neut
    bull = round((exp_bull / total) * 100.0, 1)
    bear = round((exp_bear / total) * 100.0, 1)
    neut = round(100.0 - bull - bear, 1)
    return bear, neut, bull


# ---------------------------------------------------------------------------
# Live payload
# ---------------------------------------------------------------------------

def _prediction_label(up: float, down: float) -> str:
    if up >= down and up >= 34.0 and up > down:
        return "UP"
    if down > up and down >= 34.0:
        return "DOWN"
    # Plurality fallback with honest thresholds.
    if up > down and up >= down:
        return "UP" if up >= 40.0 else "NEUTRAL"
    if down > up:
        return "DOWN" if down >= 40.0 else "NEUTRAL"
    return "NEUTRAL"


def _freshness_status(age_s: float | None) -> str:
    if age_s is None:
        return "OFFLINE"
    if age_s < PAP_LIVE_MAX_S:
        return "LIVE"
    if age_s <= PAP_DELAYED_MAX_S:
        return "DELAYED"
    return "STALE"


def _droid_direction_token(direction: str) -> Literal["LONG", "SHORT", "UNKNOWN"]:
    d = (direction or "").upper()
    if any(k in d for k in ("PUT", "BEAR", "SHORT", "SELL")):
        return "SHORT"
    if any(k in d for k in ("CALL", "BULL", "LONG", "BUY")):
        return "LONG"
    return "UNKNOWN"


def _read_droid_signal(instrument: str) -> Dict[str, Any]:
    """Read-only peek at the active DROID book for alignment display."""
    try:
        from app.signals.fsm import signal_fsm

        rows = signal_fsm.list_active(underlying=instrument)
    except Exception as exc:  # alignment degrades, never breaks PAP
        logger.warning("pap_alignment_read_failed", instrument=instrument, error=str(exc))
        return {"signal": None, "direction": None, "state": "UNKNOWN", "strategy": None}
    live = [r for r in rows if getattr(r, "state", "") not in ("CLOSED",)]
    if not live:
        return {"signal": None, "direction": None, "state": "NONE", "strategy": None}
    row = live[0]
    direction = _droid_direction_token(str(getattr(row, "direction", "") or ""))
    return {
        "signal": str(getattr(row, "id", "") or getattr(row, "signal_id", "") or ""),
        "direction": direction if direction != "UNKNOWN" else None,
        "state": str(getattr(row, "state", "") or "UNKNOWN"),
        "strategy": str(getattr(row, "strategy", "") or "") or None,
    }


def _alignment(pap_primary: str | None, droid_direction: str | None) -> str:
    if pap_primary is None:
        return "PAP_UNAVAILABLE"
    if not droid_direction:
        return "NO_DROID_SIGNAL"
    mapping = {"UP": "LONG", "DOWN": "SHORT", "NEUTRAL": None}
    droid_equiv = mapping.get(pap_primary)
    if droid_equiv is None:
        return "NEUTRAL"
    return "ALIGNED" if droid_equiv == droid_direction else "CONFLICT"


def _consensus(preds: Dict[str, str]) -> str:
    ups = sum(1 for v in preds.values() if v == "UP")
    downs = sum(1 for v in preds.values() if v == "DOWN")
    if ups == 3:
        return "SHORT-TERM BULLISH"
    if downs == 3:
        return "SHORT-TERM BEARISH"
    if ups >= 1 and downs >= 1:
        return "HORIZON CONFLICT"
    if ups >= 2:
        return "SHORT-TERM BULLISH"
    if downs >= 2:
        return "SHORT-TERM BEARISH"
    if all(v == "NEUTRAL" for v in preds.values()):
        return "NEUTRAL"
    return "MIXED"


async def get_pap_live(instrument: str) -> Dict[str, Any]:
    """Build the live PAP payload for one instrument from real market data."""
    underlying = (instrument or "").upper().replace(" 50", "")
    if underlying not in PAP_INSTRUMENTS:
        raise PapUnavailable("UNKNOWN_INSTRUMENT", f"PAP supports {list(PAP_INSTRUMENTS)}; got '{instrument}'.")

    market = MarketService()
    try:
        quote = await market.get_quote(underlying)
    except Exception as exc:
        raise PapUnavailable("NO_MARKET_DATA", f"Market quote unavailable for {underlying}: {exc}")
    if not quote or not getattr(quote, "ltp", 0) or quote.ltp <= 0:
        raise PapUnavailable("NO_MARKET_DATA", f"Market quote unavailable for {underlying}.")

    now = datetime.now(timezone.utc)
    quote_ts = getattr(quote, "timestamp", None)
    age_s: float | None = None
    if quote_ts is not None:
        try:
            age_s = max(0.0, (now - quote_ts).total_seconds())
        except Exception:
            age_s = None
    data_status = _freshness_status(age_s)

    candles_1m = await market.get_candles(underlying, timeframe="1m")
    closes_1m = [float(c.close) for c in (candles_1m or []) if getattr(c, "close", 0) > 0]
    if len(closes_1m) < 21:
        raise PapUnavailable(
            "INSUFFICIENT_HISTORICAL_DATA",
            f"Need >=21 1m closes for PAP market state; got {len(closes_1m)} for {underlying}.",
        )

    try:
        indicators = await regime_service.get_technical_indicators(underlying)
        key_levels = await regime_service.get_key_levels(underlying)
    except Exception as exc:
        raise PapUnavailable("FEATURE_CALCULATION_ERROR", f"Indicator computation failed for {underlying}: {exc}")

    # --- PAP market-state families (deterministic, real inputs only) ---
    fisher = fisher_transform(closes_1m)
    lr = linreg_slope(closes_1m)
    vwap = session_vwap(candles_1m or [])
    price = float(quote.ltp)
    price_vs_vwap_pct = round((price - vwap) / vwap * 100.0, 4) if vwap else None
    highs_1m = [float(c.high) for c in (candles_1m or [])]
    lows_1m = [float(c.low) for c in (candles_1m or [])]
    try:
        _pdi, _mdi, _adx_1m = calculate_adx(highs_1m, lows_1m, closes_1m, period=14)
    except Exception:
        _pdi, _mdi, _adx_1m = None, None, None
    try:
        _u, _m, _l, bb_bandwidth, _pctb = calculate_bollinger_bands(closes_1m, period=20)
    except Exception:
        bb_bandwidth = None
    bb_width_pct = round(float(bb_bandwidth), 4) if bb_bandwidth is not None else None

    adx = float(getattr(indicators, "adx_14", 0.0) or 0.0)
    plus_di = float(getattr(indicators, "plus_di", 0.0) or 0.0)
    minus_di = float(getattr(indicators, "minus_di", 0.0) or 0.0)

    # Deterministic descriptive labels (backend-owned, not invented frontend-side).
    if price_vs_vwap_pct is None:
        vwap_position: str | None = None
    elif price_vs_vwap_pct > 0.02:
        vwap_position = "ABOVE"
    elif price_vs_vwap_pct < -0.02:
        vwap_position = "BELOW"
    else:
        vwap_position = "AT"
    if lr is None or plus_di is None or minus_di is None:
        trend: str | None = None
    elif lr > 0 and plus_di > minus_di:
        trend = "BULLISH"
    elif lr < 0 and minus_di > plus_di:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"
    if bb_width_pct is None:
        volatility: str | None = None
    elif bb_width_pct >= 4.5:
        volatility = "HIGH"
    elif bb_width_pct <= 2.2:
        volatility = "LOW"
    else:
        volatility = "NORMAL"

    market_state: Dict[str, Any] = {
        "fisher": fisher,
        "price_vs_vwap_pct": price_vs_vwap_pct,
        "vwap": vwap,
        "adx": round(adx, 2),
        "plus_di": round(plus_di, 2),
        "minus_di": round(minus_di, 2),
        "lr_slope": lr,
        "bb_width_pct": bb_width_pct,
        "trend": trend,
        "volatility": volatility,
        "vwap_position": vwap_position,
    }

    # --- Shared snapshot feature vector (same extractor the predictor uses) ---
    chain_data = None
    max_pain = None
    try:
        from app.services.options_service import options_service

        chain_data = await options_service.get_option_chain_matrix(underlying)
        max_pain = chain_data.max_pain
    except Exception:
        chain_data, max_pain = None, None
    features = extract_ml_feature_vector(
        spot_price=price,
        indicators=indicators,
        key_levels=key_levels,
        options_analytics=chain_data.analytics if chain_data else None,
        max_pain=max_pain,
    )
    feature_vec = [
        features.rsi_norm,
        features.adx_strength,
        features.supertrend_signal,
        features.bollinger_pct_b,
        features.pcr_oi_deviation,
        features.max_pain_distance_pct,
        features.futures_basis_pct,
        features.price_above_ema20,
        features.price_above_sma200,
        features.pivot_position,
    ]

    # --- Per-horizon distributions ---
    from app.ml.targets import SUPPORTED_HORIZONS

    horizons: Dict[str, Any] = {}
    for h in PAP_HORIZONS:
        key = f"{h}m"
        if h in SUPPORTED_HORIZONS:
            ensemble_result = None
            ensemble_meta: Dict[str, Any] = {}
            try:
                from app.ml.trainer import ensemble_predict_proba, load_ensemble

                ensemble_result = ensemble_predict_proba(feature_vec, horizon_minutes=h)
                if ensemble_result is not None:
                    _, _, ensemble_meta = load_ensemble(horizon_minutes=h)
            except Exception as exc:
                logger.info("pap_ensemble_not_available", horizon=h, error=str(exc))
                ensemble_result = None
            if ensemble_result is not None:
                bear, neut, bull = ensemble_result
                from app.ml.targets import TARGET_SPEC_VERSION as _SPEC

                calibrated = (
                    ensemble_meta.get("horizon_minutes") == h
                    and ensemble_meta.get("target_spec_version", "") == _SPEC
                )
                model_source = "xgboost_lightgbm_ensemble"
                artifact_horizon: int | None = int(ensemble_meta.get("horizon_minutes", 15)) if ensemble_meta.get("horizon_minutes") else None
                model_version = str(ensemble_meta.get("model_version", f"{PAP_MODEL_FAMILY}-v2.0"))
            else:
                bear, neut, bull = heuristic_probs_from_features(features)
                calibrated = False
                model_source = "heuristic_ensemble"
                artifact_horizon = None
                model_version = f"{PAP_MODEL_FAMILY}-v1.0-heuristic"
        else:
            # No trained artifact exists for this PAP horizon yet: honest
            # heuristic from the real feature vector, never a fake ensemble.
            bear, neut, bull = heuristic_probs_from_features(features)
            calibrated = False
            model_source = "heuristic_ensemble"
            artifact_horizon = None
            model_version = f"{PAP_MODEL_FAMILY}-v1.0-heuristic"

        up = round(float(bull), 1)
        neutral = round(float(neut), 1)
        down = round(float(bear), 1)
        label = _prediction_label(up, down)
        horizons[key] = {
            "up": up,
            "neutral": neutral,
            "down": down,
            "prediction": label,
            # Probability of the predicted class (always defined).
            "probability": max(up, neutral, down),
            # Confidence is ONLY defined when calibrated; else null so the UI
            # cannot render false precision.
            "confidence": max(up, neutral, down) if calibrated else None,
            "prediction_state": "ACTIVE" if data_status in ("LIVE", "DELAYED") else "STALE",
            "model_source": model_source,
            "calibrated": bool(calibrated),
            "artifact_horizon_minutes": artifact_horizon,
            "model_version": model_version,
        }

    # --- Evidence (explanatory only â€” never a vote that overrides the model) ---
    evidence: List[Dict[str, str]] = []
    if price_vs_vwap_pct is not None:
        evidence.append({
            "label": "Price above VWAP" if price_vs_vwap_pct > 0 else ("Price below VWAP" if price_vs_vwap_pct < 0 else "Price at VWAP"),
            "state": "supportive" if abs(price_vs_vwap_pct) > 0.02 else "neutral",
            "detail": f"{price_vs_vwap_pct:+.2f}% vs session VWAP",
        })
    if lr is not None:
        evidence.append({
            "label": "Positive LR slope" if lr > 0 else ("Negative LR slope" if lr < 0 else "Flat LR slope"),
            "state": "supportive" if lr != 0 else "neutral",
            "detail": f"slope {lr:+.6f} pts/bar (20-bar)",
        })
    evidence.append({
        "label": "+DI > -DI" if plus_di > minus_di else ("-DI > +DI" if minus_di > plus_di else "+DI â‰ˆ -DI"),
        "state": "supportive" if plus_di != minus_di else "neutral",
        "detail": f"+DI {plus_di:.1f} / -DI {minus_di:.1f}",
    })
    if fisher is not None:
        evidence.append({
            "label": "Fisher positive" if fisher > 0 else ("Fisher negative" if fisher < 0 else "Fisher neutral"),
            "state": "supportive" if abs(fisher) >= 0.5 else "neutral",
            "detail": f"Fisher {fisher:+.2f}",
        })
    evidence.append({
        "label": "Strong ADX trend" if adx >= 25 else ("Moderate ADX" if adx >= 20 else "Weak ADX"),
        "state": "supportive" if adx >= 25 else ("caution" if adx < 20 else "neutral"),
        "detail": f"ADX {adx:.1f}",
    })
    if volatility is not None:
        evidence.append({
            "label": f"{volatility.capitalize()} volatility",
            "state": "neutral" if volatility == "NORMAL" else "caution",
            "detail": f"BB width {bb_width_pct:.2f}%" if bb_width_pct is not None else "BB width unavailable",
        })

    droid = _read_droid_signal(underlying)
    primary = horizons.get("5m", {}).get("prediction")
    alignment_state = _alignment(primary, droid.get("direction"))
    consensus = _consensus({k: v["prediction"] for k, v in horizons.items()})

    any_calibrated = any(v.get("calibrated") for v in horizons.values())
    model_versions = sorted({str(v.get("model_version", "")) for v in horizons.values() if v.get("model_version")})
    payload: Dict[str, Any] = {
        "instrument": underlying,
        "timeframe": "1 MIN",
        "timestamp": now.isoformat(),
        "price": round(price, 2),
        "data_status": data_status,
        "data_age_s": round(age_s, 1) if age_s is not None else None,
        "available": True,
        "mode": "SHADOW",
        "execution": "DISABLED",
        "horizons": horizons,
        "features": {
            "fisher": fisher,
            "price_vs_vwap_pct": price_vs_vwap_pct,
            "adx": round(adx, 2),
            "plus_di": round(plus_di, 2),
            "minus_di": round(minus_di, 2),
            "lr_slope": lr,
            "bb_width_pct": bb_width_pct,
        },
        "market_state": market_state,
        "evidence": evidence,
        "evidence_note": "Explanatory only: the ML model is the source of the prediction; features are inputs, not votes.",
        "droid_alignment": {
            "droid_signal": droid.get("direction"),
            "droid_state": droid.get("state"),
            "droid_strategy": droid.get("strategy"),
            "pap_primary": primary,
            "pap_primary_horizon": "5m",
            "alignment": alignment_state,
            "advisory_only": True,
        },
        "horizon_consensus": {
            "consensus": consensus,
            "predictions": {k: v["prediction"] for k, v in horizons.items()},
        },
        "model": {
            "name": PAP_MODEL_NAME,
            "versions": model_versions,
            "feature_schema": PAP_FEATURE_SCHEMA,
            "calibration": "CALIBRATED" if any_calibrated else "NOT_CALIBRATED",
            "data_quality": "GOOD" if data_status == "LIVE" else ("WARNING" if data_status == "DELAYED" else "BAD"),
            "prediction_age_s": round(age_s, 1) if age_s is not None else None,
            "status": "VALID" if data_status in ("LIVE", "DELAYED") else "STALE",
            "shadow_mode": "ACTIVE",
            "execution": "DISABLED",
        },
        "calibration": {
            "status": "CALIBRATED" if any_calibrated else "NOT_CALIBRATED",
            "note": "Per-horizon calibrated flags come from artifact triples; heuristic horizons are never calibrated.",
        },
    }
    logger.info(
        "pap_live",
        instrument=underlying,
        price=round(price, 2),
        data_status=data_status,
        primary=primary,
        alignment=alignment_state,
    )
    return payload


def unavailable_payload(instrument: str, code: str, detail: str) -> Dict[str, Any]:
    """Honest unavailable shape: nulls, never zeros masquerading as data."""
    return {
        "instrument": (instrument or "").upper(),
        "timeframe": "1 MIN",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "price": None,
        "data_status": "OFFLINE",
        "data_age_s": None,
        "available": False,
        "unavailable_code": code,
        "unavailable_reason": detail,
        "mode": "SHADOW",
        "execution": "DISABLED",
        "horizons": None,
        "features": None,
        "market_state": None,
        "evidence": [],
        "droid_alignment": {
            "droid_signal": None,
            "pap_primary": None,
            "alignment": "PAP_UNAVAILABLE",
            "advisory_only": True,
        },
        "horizon_consensus": {"consensus": "UNAVAILABLE", "predictions": None},
        "model": {
            "name": PAP_MODEL_NAME,
            "versions": [],
            "feature_schema": PAP_FEATURE_SCHEMA,
            "calibration": "UNAVAILABLE",
            "data_quality": "BAD",
            "prediction_age_s": None,
            "status": "DISABLED",
            "shadow_mode": "ACTIVE",
            "execution": "DISABLED",
        },
        "calibration": {"status": "UNAVAILABLE", "note": detail},
    }
