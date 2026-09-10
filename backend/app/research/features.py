"""Unified feature extraction layer for the Research Laboratory (§12).

Computes point-in-time technical, statistical, structural, and options
features once to be reused across all indicators and validation runs.
"""

from datetime import datetime, timezone, timedelta
import math
from typing import Any, Dict, List, Optional
import structlog

from app.quant.indicators import (
    calculate_adx,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_rsi,
    calculate_sma,
    calculate_supertrend,
)
from app.research.enums import DataQualityStatus, MarketRegime, MarketSession
from app.technical_analysis.analyzer import analyze_timeframe

logger = structlog.get_logger(__name__)


def classify_session_ist(dt: datetime) -> MarketSession:
    """Classify candle timestamp into Indian market sessions (IST: UTC + 5:30)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ist_time = dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
    total_minutes = ist_time.hour * 60 + ist_time.minute

    # 09:15 = 555, 09:45 = 585, 11:30 = 690, 13:30 = 810, 15:00 = 900, 15:30 = 930
    if total_minutes < 555 or total_minutes >= 930:
        return MarketSession.CLOSED
    if total_minutes < 585:
        return MarketSession.OPENING
    if total_minutes < 690:
        return MarketSession.EARLY
    if total_minutes < 810:
        return MarketSession.MID
    if total_minutes < 900:
        return MarketSession.LATE
    return MarketSession.CLOSING


def calculate_intraday_vwap(candles: List[Dict[str, Any]]) -> Optional[float]:
    """Calculate cumulative VWAP from intraday candles."""
    if not candles:
        return None
    cum_pv = 0.0
    cum_vol = 0.0
    for c in candles:
        typical = (c.get("high", 0.0) + c.get("low", 0.0) + c.get("close", 0.0)) / 3.0
        vol = float(c.get("volume", 0.0) or 0.0)
        cum_pv += typical * vol
        cum_vol += vol
    if cum_vol > 0:
        return round(cum_pv / cum_vol, 2)
    return round(candles[-1]["close"], 2)


def determine_market_regime(
    closes: List[float],
    highs: List[float],
    lows: List[float],
    current_price: float,
) -> MarketRegime:
    """Determine market regime based on ADX, Bollinger Bandwidth, and ATR."""
    if len(closes) < 14 or len(highs) < 14 or len(lows) < 14:
        return MarketRegime.RANGING

    plus_di, minus_di, adx = calculate_adx(highs, lows, closes, 14)
    _, _, _, bb_bandwidth, _ = calculate_bollinger_bands(closes, 20, 2.0) if len(closes) >= 20 else (0, 0, 0, 2.0, 0)
    atr_14 = calculate_atr(highs, lows, closes, 14)

    if adx >= 25.0:
        return MarketRegime.TRENDING_UP if plus_di > minus_di else MarketRegime.TRENDING_DOWN
    elif bb_bandwidth < 1.0:
        return MarketRegime.COMPRESSING
    elif atr_14 > (current_price * 0.008):
        return MarketRegime.VOLATILE
    else:
        return MarketRegime.RANGING


class FeatureLayer:
    """Unified feature computer for research."""

    @classmethod
    def compute_features(
        cls,
        instrument: str,
        timeframe: str,
        candles: List[Dict[str, Any]],
        options_ctx: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Extract comprehensive feature set strictly from historical candles up to the last one.
        
        Guarantees Point-in-Time integrity:
        Uses ONLY information contained within or prior to candles[-1].
        """
        if not candles or len(candles) < 2:
            return {"error": "Insufficient candles"}

        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        opens = [float(c["open"]) for c in candles]
        volumes = [float(c.get("volume", 0.0) or 0.0) for c in candles]

        current_price = closes[-1]
        last_candle = candles[-1]
        raw_ts = last_candle.get("timestamp")
        if isinstance(raw_ts, str):
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.now(timezone.utc)
        elif isinstance(raw_ts, datetime):
            ts = raw_ts
        else:
            ts = datetime.now(timezone.utc)

        session = classify_session_ist(ts)

        # 1. Quant Indicators
        rsi_14 = calculate_rsi(closes, 14)
        atr_14 = calculate_atr(highs, lows, closes, 14)
        plus_di, minus_di, adx = calculate_adx(highs, lows, closes, 14)
        bb_upper, bb_mid, bb_lower, bb_bandwidth, bb_pct_b = calculate_bollinger_bands(closes, 20, 2.0)
        supertrend_val, supertrend_dir = calculate_supertrend(highs, lows, closes, 10, 3.0)

        ema_9 = calculate_ema(closes, 9)
        ema_21 = calculate_ema(closes, 21)
        ema_50 = calculate_ema(closes, 50)
        ema_200 = calculate_ema(closes, 200)

        vwap = calculate_intraday_vwap(candles)
        vwap_dist_pct = round(((current_price - vwap) / vwap) * 100.0, 3) if vwap else 0.0

        # 2. Price Returns & Momentum Dynamics
        ret_1 = round(((closes[-1] - closes[-2]) / closes[-2]) * 100.0, 3) if len(closes) >= 2 else 0.0
        ret_5 = round(((closes[-1] - closes[-6]) / closes[-6]) * 100.0, 3) if len(closes) >= 6 else ret_1
        ret_15 = round(((closes[-1] - closes[-16]) / closes[-16]) * 100.0, 3) if len(closes) >= 16 else ret_5

        # Acceleration: rate of change in 3-period momentum
        mom_now = closes[-1] - closes[-4] if len(closes) >= 4 else 0.0
        mom_prev = closes[-2] - closes[-5] if len(closes) >= 5 else 0.0
        acceleration = round(mom_now - mom_prev, 2)

        # Realized Volatility (annualized proxy from 20-period log returns)
        realized_vol = 0.0
        if len(closes) >= 20:
            returns = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - 19, len(closes))]
            mean_ret = sum(returns) / len(returns)
            variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
            realized_vol = round(math.sqrt(variance) * 100.0, 3)

        # 3. Volume Dynamics
        vol_len = min(len(volumes), 20)
        vol_subset = volumes[-vol_len:]
        avg_volume = sum(vol_subset) / vol_len if vol_len > 0 else 1.0
        current_vol = volumes[-1]
        rel_volume = round(current_vol / avg_volume, 2) if avg_volume > 0 else 1.0
        vol_surge = rel_volume >= 1.8

        # 4. Technical Analysis Suite Integration
        try:
            ta_analysis = analyze_timeframe(
                candles=candles,
                symbol=instrument,
                timeframe=timeframe,
                fno_levels=options_ctx.get("raw_fno") if options_ctx else None,
                vix=options_ctx.get("atm_iv") if options_ctx else None,
            )
        except Exception as e:
            logger.warning("ta_analysis_submodule_fallback", error=str(e))
            ta_analysis = {}

        # 5. Market Regime Determination
        regime = determine_market_regime(closes, highs, lows, current_price)

        # 6. Options Features
        opt_features = {}
        if options_ctx and options_ctx.get("available", False):
            call_wall = options_ctx.get("call_wall")
            put_wall = options_ctx.get("put_wall")
            cw_dist = round(((call_wall - current_price) / current_price) * 100.0, 2) if call_wall else None
            pw_dist = round(((current_price - put_wall) / current_price) * 100.0, 2) if put_wall else None

            opt_features = {
                "pcr_oi": options_ctx.get("pcr_oi", 1.0),
                "pcr_vol": options_ctx.get("pcr_vol", 1.0),
                "atm_iv": options_ctx.get("atm_iv", 15.0),
                "call_wall": call_wall,
                "put_wall": put_wall,
                "max_pain": options_ctx.get("max_pain"),
                "call_wall_distance_pct": cw_dist,
                "put_wall_distance_pct": pw_dist,
                "days_to_expiry": options_ctx.get("days_to_expiry", 1.0),
                "atm_theta": options_ctx.get("atm_theta", -10.0),
            }

        return {
            "instrument": instrument,
            "timeframe": timeframe,
            "timestamp": ts.isoformat(),
            "session": session.value,
            "current_price": current_price,
            "regime": regime.value,
            "quant": {
                "rsi_14": rsi_14,
                "atr_14": atr_14,
                "adx": adx,
                "plus_di": plus_di,
                "minus_di": minus_di,
                "bb_upper": bb_upper,
                "bb_mid": bb_mid,
                "bb_lower": bb_lower,
                "bb_bandwidth": bb_bandwidth,
                "bb_pct_b": bb_pct_b,
                "supertrend_val": supertrend_val,
                "supertrend_dir": supertrend_dir,
                "ema_9": ema_9,
                "ema_21": ema_21,
                "ema_50": ema_50,
                "ema_200": ema_200,
                "vwap": vwap,
                "vwap_dist_pct": vwap_dist_pct,
            },
            "momentum_dynamics": {
                "return_1_pct": ret_1,
                "return_5_pct": ret_5,
                "return_15_pct": ret_15,
                "acceleration": acceleration,
                "realized_vol_pct": realized_vol,
            },
            "volume_dynamics": {
                "current_volume": current_vol,
                "avg_volume_20": round(avg_volume, 1),
                "relative_volume": rel_volume,
                "is_volume_surge": vol_surge,
            },
            "ta_suite": ta_analysis,
            "options": opt_features,
            "data_quality": DataQualityStatus.LIVE.value,
        }

    @classmethod
    def compute_multi_timeframe_features(
        cls,
        instrument: str,
        timeframe_candles: Dict[str, List[Dict[str, Any]]],
        options_ctx: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compute per-timeframe features plus a cross-timeframe alignment summary.

        Each timeframe with >= 2 candles gets a full ``compute_features`` payload
        under ``per_timeframe``. Alignment votes come from each TF's
        supertrend direction + RSI position — no forward-looking data.
        """
        per_timeframe: Dict[str, Any] = {}
        for tf, candles in (timeframe_candles or {}).items():
            try:
                feats = cls.compute_features(
                    instrument=instrument,
                    timeframe=tf,
                    candles=candles,
                    options_ctx=options_ctx,
                )
            except Exception as e:
                logger.warning("mtf_tf_features_failed", instrument=instrument, timeframe=tf, error=str(e))
                continue
            if isinstance(feats, dict) and "error" not in feats:
                per_timeframe[tf] = {"features": feats}

        bull_votes = 0
        bear_votes = 0
        total_votes = 0
        for tf_payload in per_timeframe.values():
            quant = (tf_payload.get("features") or {}).get("quant", {})
            st_dir = str(quant.get("supertrend_dir", "NEUTRAL")).upper()
            try:
                rsi = float(quant.get("rsi_14", 50.0))
            except (TypeError, ValueError):
                rsi = 50.0
            vote: Optional[str] = None
            if st_dir == "BULLISH" and rsi >= 50.0:
                vote = "BULLISH"
            elif st_dir == "BEARISH" and rsi < 50.0:
                vote = "BEARISH"
            if vote == "BULLISH":
                bull_votes += 1
                total_votes += 1
            elif vote == "BEARISH":
                bear_votes += 1
                total_votes += 1

        if total_votes > 0:
            if bull_votes > bear_votes:
                overall_bias = "BULLISH"
            elif bear_votes > bull_votes:
                overall_bias = "BEARISH"
            else:
                overall_bias = "NEUTRAL"
            alignment_score = round(abs(bull_votes - bear_votes) / total_votes * 100.0, 2)
        else:
            overall_bias = "NEUTRAL"
            alignment_score = 0.0

        return {
            "instrument": instrument,
            "per_timeframe": per_timeframe,
            "alignment": {
                "overall_bias": overall_bias,
                "alignment_score": alignment_score,
                "bull_votes": bull_votes,
                "bear_votes": bear_votes,
                "total_votes": total_votes,
            },
        }
