"""
Canonical Feature Adapter — §5
Constructs CanonicalFeatureVector from multi-domain market data.
"""
from __future__ import annotations

import math
from typing import Any, Optional
from app.historical_intelligence.schemas import (
    CandleData,
    CanonicalFeatureVector,
    PriceFeatures,
    CandleFeatures,
    StructureFeatures,
    TrendFeatures,
    VolumeVolFeatures,
    FuturesFeatures,
    OptionsFeatures,
    MarketContextFeatures,
    SessionPhase,
)


def adapt_market_features(
    candles: list[CandleData],
    indicators: Optional[Any] = None,
    key_levels: Optional[Any] = None,
    options_analytics: Optional[Any] = None,
    futures_data: Optional[Any] = None,
    vix_val: float = 14.0,
    session_phase: SessionPhase = SessionPhase.MID_SESSION,
    data_quality_score: float = 1.0,
) -> CanonicalFeatureVector:
    """
    Extracts and maps raw market data to the standardized CanonicalFeatureVector.
    Uses zero lookahead; all calculations are anchored strictly at candles[-1].
    """
    if not candles:
        return CanonicalFeatureVector()

    curr = candles[-1]
    n_candles = len(candles)
    close_p = curr.close
    open_p = curr.open
    high_p = curr.high
    low_p = curr.low
    vol = curr.volume

    prev = candles[-2] if n_candles >= 2 else curr

    # 1. Price Dynamics
    ret = ((close_p - prev.close) / max(1e-4, prev.close)) * 100.0 if prev.close > 0 else 0.0
    log_ret = math.log(max(1e-4, close_p) / max(1e-4, prev.close)) * 100.0 if prev.close > 0 else 0.0
    gap = open_p - prev.close
    
    # Acceleration over last 3 bars
    prev2 = candles[-3] if n_candles >= 3 else prev
    ret_prev = ((prev.close - prev2.close) / max(1e-4, prev2.close)) * 100.0 if prev2.close > 0 else 0.0
    accel = ret - ret_prev

    # Rolling VWAP
    cum_vol = sum(c.volume for c in candles)
    cum_pv = sum(((c.high + c.low + c.close) / 3.0) * c.volume for c in candles)
    vwap = (cum_pv / cum_vol) if cum_vol > 0 else close_p
    vwap_dist = close_p - vwap

    price_f = PriceFeatures(
        returns=round(ret, 4),
        log_returns=round(log_ret, 4),
        gap=round(gap, 2),
        acceleration=round(accel, 4),
        vwap_distance=round(vwap_dist, 2),
    )

    # 2. Candle Geometry
    rng = max(1e-4, high_p - low_p)
    body = abs(close_p - open_p)
    u_wick = high_p - max(open_p, close_p)
    l_wick = min(open_p, close_p) - low_p
    body_ratio = body / rng
    close_loc = (close_p - low_p) / rng
    
    # Compression: compare current range against recent 10-bar median range
    recent_ranges = [max(1e-4, c.high - c.low) for c in candles[-10:]]
    med_range = sorted(recent_ranges)[len(recent_ranges) // 2] if recent_ranges else rng
    compression = rng / med_range if med_range > 0 else 1.0

    candle_f = CandleFeatures(
        range_pts=round(rng, 2),
        body=round(body, 2),
        upper_wick=round(u_wick, 2),
        lower_wick=round(l_wick, 2),
        body_to_range=round(body_ratio, 4),
        close_location=round(close_loc, 4),
        compression=round(compression, 4),
    )

    # 3. Market Structure (Swings, HH/HL/LH/LL, Consolidation)
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    swing_h = max(highs[-20:]) if n_candles >= 20 else max(highs)
    swing_l = min(lows[-20:]) if n_candles >= 20 else min(lows)

    is_hh = close_p > swing_h * 0.999
    is_ll = close_p < swing_l * 1.001
    is_hl = (low_p > swing_l) and not is_ll
    is_lh = (high_p < swing_h) and not is_hh

    # Consolidation: range of last 10 bars is tight (< 1.5x current bar range)
    cons_range = (max(highs[-10:]) - min(lows[-10:])) if n_candles >= 10 else rng
    consolidation = cons_range < (med_range * 1.8)
    breakout_dist = max(0.0, close_p - swing_h) if close_p > swing_h else min(0.0, close_p - swing_l)

    retest = "NONE"
    if abs(close_p - swing_h) < (rng * 0.5):
        retest = "RETESTING_RESISTANCE"
    elif abs(close_p - swing_l) < (rng * 0.5):
        retest = "RETESTING_SUPPORT"

    structure_f = StructureFeatures(
        swing_high=round(swing_h, 2),
        swing_low=round(swing_l, 2),
        is_hh=is_hh,
        is_hl=is_hl,
        is_lh=is_lh,
        is_ll=is_ll,
        consolidation=consolidation,
        breakout_distance=round(breakout_dist, 2),
        retest_state=retest,
    )

    # 4. Trend & Momentum (Indicators)
    # Default indicators if not passed
    ema20 = getattr(indicators, "ema_20", None)
    if ema20 is None:
        # Calculate EMA-20 manually from close prices
        k = 2.0 / 21.0
        ema20 = candles[0].close
        for c in candles[1:]:
            ema20 = (c.close * k) + (ema20 * (1.0 - k))

    ema50 = getattr(indicators, "sma_50", None) or getattr(indicators, "ema_50", None) or ema20
    rsi_val = getattr(indicators, "rsi_14", None)
    if rsi_val is None:
        # Simple RSI calculation
        gains, losses = [], []
        for i in range(1, min(15, n_candles)):
            chg = candles[-i].close - candles[-i - 1].close
            if chg >= 0:
                gains.append(chg)
            else:
                losses.append(abs(chg))
        avg_g = (sum(gains) / 14.0) if gains else 0.0
        avg_l = (sum(losses) / 14.0) if losses else 0.0
        rs = avg_g / max(1e-4, avg_l)
        rsi_val = 100.0 - (100.0 / (1.0 + rs))

    adx_val = getattr(indicators, "adx_14", 25.0) or 25.0
    macd_val = getattr(indicators, "macd", 0.0) or 0.0

    # EMA Slope
    ema_prev = prev.close
    ema_slope = (ema20 - ema_prev)

    trend_f = TrendFeatures(
        ema_short=round(ema20, 2),
        ema_medium=round(ema50, 2),
        ema_slope=round(ema_slope, 4),
        sma=round(ema50, 2),
        slope=round(ema_slope, 4),
        vwap=round(vwap, 2),
        adx=round(float(adx_val), 2),
        rsi=round(float(rsi_val), 2),
        macd=round(float(macd_val), 4),
        momentum_accel=round(accel, 4),
    )

    # 5. Volume & Volatility
    vol_window = [c.volume for c in candles[-20:]]
    avg_vol = (sum(vol_window) / len(vol_window)) if vol_window else 1000.0
    rel_vol = vol / max(1.0, avg_vol)
    vol_pct = (sum(1 for v in vol_window if v <= vol) / len(vol_window)) * 100.0 if vol_window else 50.0

    prev_vol = prev.volume
    vol_accel = ((vol - prev_vol) / max(1.0, prev_vol)) if prev_vol > 0 else 0.0

    # ATR (14 bars)
    tr_list = []
    for i in range(1, min(15, n_candles)):
        c_i = candles[-i]
        c_prev = candles[-i - 1]
        tr = max(c_i.high - c_i.low, abs(c_i.high - c_prev.close), abs(c_i.low - c_prev.close))
        tr_list.append(tr)
    atr = (sum(tr_list) / len(tr_list)) if tr_list else rng

    # Realized Volatility annualized %
    rets = [((candles[i].close - candles[i - 1].close) / candles[i - 1].close) for i in range(1, min(30, n_candles))]
    var = (sum(r * r for r in rets) / len(rets)) if rets else 0.0001
    realized_vol = math.sqrt(var) * math.sqrt(252 * 375) * 100.0  # intraday 1m to annual %

    vol_vol_f = VolumeVolFeatures(
        relative_volume=round(rel_vol, 4),
        volume_percentile=round(vol_pct, 2),
        volume_acceleration=round(vol_accel, 4),
        atr=round(atr, 2),
        realized_volatility=round(realized_vol, 2),
        vix=round(vix_val, 2),
        iv=round(getattr(options_analytics, "atm_iv", vix_val) or vix_val, 2),
        iv_percentile=round(getattr(options_analytics, "iv_percentile", 50.0) or 50.0, 2),
    )

    # 6. Futures Context
    fut_basis = getattr(futures_data, "basis", 0.0) if futures_data else 0.0
    fut_oi = getattr(futures_data, "oi", 0.0) if futures_data else 0.0
    fut_oi_chg = getattr(futures_data, "oi_change", 0.0) if futures_data else 0.0
    fut_buildup = getattr(futures_data, "buildup", "LONG_BUILDUP") if futures_data else "LONG_BUILDUP"
    price_oi_div = ret * fut_oi_chg

    futures_f = FuturesFeatures(
        basis=round(float(fut_basis), 2),
        oi=round(float(fut_oi), 2),
        oi_change=round(float(fut_oi_chg), 2),
        price_oi_divergence=round(price_oi_div, 4),
        buildup=str(fut_buildup),
    )

    # 7. Options Context
    ce_oi = getattr(options_analytics, "total_call_oi", 0.0) if options_analytics else 0.0
    pe_oi = getattr(options_analytics, "total_put_oi", 0.0) if options_analytics else 0.0
    pcr_oi = getattr(options_analytics, "pcr_oi", 1.0) if options_analytics else 1.0
    pcr_vol = getattr(options_analytics, "pcr_volume", 1.0) if options_analytics else 1.0
    atm_iv = getattr(options_analytics, "atm_iv", vix_val) if options_analytics else vix_val
    skew = getattr(options_analytics, "iv_skew", 0.0) if options_analytics else 0.0

    options_f = OptionsFeatures(
        ce_oi=round(float(ce_oi), 2),
        pe_oi=round(float(pe_oi), 2),
        pcr_oi=round(float(pcr_oi), 4),
        pcr_volume=round(float(pcr_vol), 4),
        atm_iv=round(float(atm_iv), 2),
        iv_skew=round(float(skew), 2),
        atm_pressure=round(float(pcr_oi - 1.0), 4),
        liquidity_score=1.0,
    )

    # 8. Market Context & Support/Resistance
    dist_sup = max(0.0, close_p - swing_l)
    dist_res = max(0.0, swing_h - close_p)

    context_f = MarketContextFeatures(
        breadth=0.0,
        market_liquidity=1.0,
        distance_to_support=round(dist_sup, 2),
        distance_to_resistance=round(dist_res, 2),
        session_phase=session_phase,
        cross_market_state="NEUTRAL",
        data_quality_score=round(data_quality_score, 4),
    )

    return CanonicalFeatureVector(
        price=price_f,
        candle=candle_f,
        structure=structure_f,
        trend=trend_f,
        volume_vol=vol_vol_f,
        futures=futures_f,
        options=options_f,
        market_context=context_f,
    )
