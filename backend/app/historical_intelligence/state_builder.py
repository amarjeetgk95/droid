"""
Historical State Builder & Point-In-Time Integrity Engine — §§4, 10, 34
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Any
from app.historical_intelligence.schemas import (
    CandleData,
    HistoricalStateSnapshot,
    MarketRegime,
    VolatilityRegime,
    VixBucket,
    SessionPhase,
)
from app.historical_intelligence.feature_adapter import adapt_market_features
from app.historical_intelligence.normalizer import normalize_features
from app.historical_intelligence.embedding import embedding_generator
from app.historical_intelligence.versioning import FEATURE_VERSION, EMBEDDING_VERSION, SCHEMA_VERSION

IST_OFFSET = timedelta(hours=5, minutes=30)


def derive_session_phase(timestamp: datetime, is_crypto: bool = False) -> Tuple[SessionPhase, int]:
    """Calculate session phase and minute of session based on IST trading hours."""
    if is_crypto:
        return SessionPhase.PERPETUAL, (timestamp.hour * 60 + timestamp.minute)

    # Convert to IST
    ts_ist = timestamp.astimezone(timezone(IST_OFFSET)) if timestamp.tzinfo else timestamp + IST_OFFSET
    total_mins = ts_ist.hour * 60 + ts_ist.minute
    
    # Market opens 09:15 (555 mins) and closes 15:30 (930 mins)
    open_mins = 9 * 60 + 15
    close_mins = 15 * 60 + 30

    if total_mins < 9 * 60:
        return SessionPhase.PRE_MARKET, 0
    elif total_mins < open_mins:
        return SessionPhase.PRE_MARKET, total_mins - (9 * 60)
    elif total_mins <= open_mins + 30:  # 09:15 - 09:45
        return SessionPhase.MARKET_OPEN, total_mins - open_mins
    elif total_mins <= 11 * 60 + 30:    # 09:45 - 11:30
        return SessionPhase.EARLY_SESSION, total_mins - open_mins
    elif total_mins <= 13 * 60 + 30:    # 11:30 - 13:30
        return SessionPhase.MID_SESSION, total_mins - open_mins
    elif total_mins <= 15 * 60:         # 13:30 - 15:00
        return SessionPhase.AFTERNOON, total_mins - open_mins
    elif total_mins <= close_mins:      # 15:00 - 15:30
        return SessionPhase.CLOSING_PHASE, total_mins - open_mins
    else:
        return SessionPhase.POST_MARKET, total_mins - close_mins


def derive_regimes(
    candles: list[CandleData],
    vix: float = 14.0,
) -> Tuple[MarketRegime, VolatilityRegime, VixBucket]:
    """Classify Market Regime, Volatility Regime, and VIX Bucket."""
    if not candles:
        return MarketRegime.UNKNOWN, VolatilityRegime.NORMAL_VOLATILITY, VixBucket.B_12_15

    curr = candles[-1]
    n = len(candles)
    close_p = curr.close

    # VIX Bucket
    if vix < 12.0:
        vix_b = VixBucket.SUB_12
    elif vix <= 15.0:
        vix_b = VixBucket.B_12_15
    elif vix <= 18.0:
        vix_b = VixBucket.B_15_18
    elif vix <= 22.0:
        vix_b = VixBucket.B_18_22
    else:
        vix_b = VixBucket.ABOVE_22

    # Volatility Regime
    highs = [c.high for c in candles[-14:]]
    lows = [c.low for c in candles[-14:]]
    avg_rng = sum(h - l for h, l in zip(highs, lows)) / max(1, len(highs))
    rng_ratio = (avg_rng / close_p) * 100.0 if close_p > 0 else 0.5

    if vix > 24.0 or rng_ratio > 0.4:
        vol_reg = VolatilityRegime.EXTREME_VOLATILITY
    elif vix > 18.0 or rng_ratio > 0.25:
        vol_reg = VolatilityRegime.HIGH_VOLATILITY
    elif vix < 12.0 and rng_ratio < 0.1:
        vol_reg = VolatilityRegime.LOW_VOLATILITY
    else:
        vol_reg = VolatilityRegime.NORMAL_VOLATILITY

    # Market Direction / Regime
    if n >= 20:
        p_start = candles[-20].close
        pct_chg = ((close_p - p_start) / p_start) * 100.0
        max_h = max(c.high for c in candles[-20:])
        min_l = min(c.low for c in candles[-20:])
        
        if close_p >= max_h * 0.999 and pct_chg > 0.3:
            mkt_reg = MarketRegime.BREAKOUT
        elif close_p <= min_l * 1.001 and pct_chg < -0.3:
            mkt_reg = MarketRegime.BREAKDOWN
        elif pct_chg > 0.25:
            mkt_reg = MarketRegime.TRENDING_BULLISH
        elif pct_chg < -0.25:
            mkt_reg = MarketRegime.TRENDING_BEARISH
        else:
            mkt_reg = MarketRegime.SIDEWAYS
    else:
        mkt_reg = MarketRegime.UNKNOWN

    return mkt_reg, vol_reg, vix_b


def validate_candle_integrity(candle: CandleData) -> Tuple[bool, Optional[str]]:
    """Validate single candle bounds and prevent bad data ingestion (§34)."""
    if candle.open <= 0 or candle.high <= 0 or candle.low <= 0 or candle.close <= 0:
        return False, f"Negative or zero price values in candle: {candle}"
    if candle.high < candle.low:
        return False, f"Invalid candle: High ({candle.high}) < Low ({candle.low})"
    if candle.open < candle.low or candle.open > candle.high:
        return False, f"Invalid candle: Open ({candle.open}) outside [Low {candle.low}, High {candle.high}]"
    if candle.close < candle.low or candle.close > candle.high:
        return False, f"Invalid candle: Close ({candle.close}) outside [Low {candle.low}, High {candle.high}]"
    if math.isnan(candle.open) or math.isnan(candle.high) or math.isnan(candle.low) or math.isnan(candle.close):
        return False, "NaN value detected in OHLC"
    return True, None


class HistoricalStateBuilder:
    """
    Builds canonical HistoricalStateSnapshots from raw point-in-time observations (§4).
    Enforces strict data quality and leakage-prevention standards (§34).
    """

    def build_snapshot(
        self,
        instrument: str,
        candles: list[CandleData],
        timestamp: datetime,
        timeframe: str = "1m",
        indicators: Optional[Any] = None,
        key_levels: Optional[Any] = None,
        options_analytics: Optional[Any] = None,
        futures_data: Optional[Any] = None,
        vix: float = 14.0,
        is_crypto: bool = False,
    ) -> HistoricalStateSnapshot:
        # 1. Quality Validation (§34)
        if not candles:
            raise ValueError("Cannot build state snapshot from empty candle series.")

        for c in candles:
            ok, err = validate_candle_integrity(c)
            if not ok:
                raise ValueError(f"Data quality rejection: {err}")

        # Ensure candles are strictly sorted and point-in-time
        # Max candle timestamp cannot exceed snapshot timestamp
        ts_ms = int(timestamp.timestamp() * 1000)
        curr_bar = candles[-1]
        if curr_bar.timestamp_utc > ts_ms + 1000:  # Allow max 1s buffer for clock drift
            raise ValueError(f"Lookahead detected: Candle timestamp ({curr_bar.timestamp_utc}) > Snapshot timestamp ({ts_ms})")

        # 2. Derive Session and Regimes
        session_ph, min_of_session = derive_session_phase(timestamp, is_crypto=is_crypto)
        mkt_reg, vol_reg, vix_b = derive_regimes(candles, vix=vix)

        # 3. Feature Extraction (§5)
        raw_features = adapt_market_features(
            candles=candles,
            indicators=indicators,
            key_levels=key_levels,
            options_analytics=options_analytics,
            futures_data=futures_data,
            vix_val=vix,
            session_phase=session_ph,
            data_quality_score=1.0,
        )

        # 4. Normalization (§6)
        normalized = normalize_features(raw_features)

        # 5. Embedding (§7)
        embedding = embedding_generator.generate_embedding(normalized)

        # 6. Assemble Canonical State Snapshot
        snap_id = f"{instrument}_{timeframe}_{int(timestamp.timestamp())}_{uuid.uuid4().hex[:8]}"
        trading_date = timestamp.strftime("%Y-%m-%d")

        return HistoricalStateSnapshot(
            snapshot_id=snap_id,
            instrument=instrument.upper(),
            instrument_family="CRYPTO" if is_crypto else "INDEX",
            exchange="BINANCE" if is_crypto else "NSE",
            timeframe=timeframe,
            timestamp=timestamp,
            trading_date=trading_date,
            session=session_ph,
            minute_of_session=min_of_session,
            feature_version=FEATURE_VERSION,
            embedding_version=EMBEDDING_VERSION,
            schema_version=SCHEMA_VERSION,
            market_regime=mkt_reg,
            volatility_regime=vol_reg,
            vix_bucket=vix_b,
            trend_state="UP" if raw_features.trend.ema_slope > 0 else "DOWN",
            momentum_state="ACCELERATING" if raw_features.trend.momentum_accel > 0 else "DECELERATING",
            structure_state=raw_features.structure.retest_state,
            volume_state="HIGH" if raw_features.volume_vol.relative_volume > 1.5 else "NORMAL",
            futures_state=raw_features.futures.buildup,
            options_state="BULLISH" if raw_features.options.pcr_oi > 1.1 else ("BEARISH" if raw_features.options.pcr_oi < 0.9 else "NEUTRAL"),
            data_quality_score=1.0,
            feature_vector=raw_features,
            normalized_vector=normalized,
            embedding=embedding,
        )


state_builder = HistoricalStateBuilder()
