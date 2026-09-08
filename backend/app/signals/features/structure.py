"""
Market Structure Feature Extraction Module (§59).
Tracks swing highs/lows, trend structure (HH_HL, LH_LL), Break of Structure (BOS),
Change of Character (CHoCH), session levels, and liquidity sweep events.
"""
from __future__ import annotations

from typing import Optional, Any
from pydantic import BaseModel, Field


class SwingPoint(BaseModel):
    index: int
    price: float
    point_type: str  # "SWING_HIGH" | "SWING_LOW"
    timestamp: Optional[Any] = None


class MarketStructureFeatures(BaseModel):
    structure_type: str = "RANGE"  # "HH_HL" | "LH_LL" | "RANGE" | "EXPANDING"
    trend_bias: str = "NEUTRAL"    # "BULLISH" | "BEARISH" | "NEUTRAL"
    
    recent_swing_high: Optional[float] = None
    recent_swing_low: Optional[float] = None
    
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    prior_day_high: Optional[float] = None
    prior_day_low: Optional[float] = None
    
    # Event flags
    is_bos_bullish: bool = False   # Break of Structure (continuation)
    is_bos_bearish: bool = False
    is_choch_bullish: bool = False # Change of Character (trend reversal)
    is_choch_bearish: bool = False
    
    # Liquidity Sweeps
    high_swept_and_reclaimed: bool = False  # Swept swing/session high and closed back below
    low_swept_and_reclaimed: bool = False   # Swept swing/session low and closed back above
    swept_level: Optional[float] = None


def extract_swing_points(candles: list[dict], window: int = 3) -> list[SwingPoint]:
    """Identifies local swing highs and swing lows using a rolling window."""
    swings: list[SwingPoint] = []
    n = len(candles)
    if n < window * 2 + 1:
        return swings

    for i in range(window, n - window):
        curr_h = float(candles[i].get("high", 0))
        curr_l = float(candles[i].get("low", 0))

        # Check Swing High
        is_high = True
        for j in range(i - window, i + window + 1):
            if j != i and float(candles[j].get("high", 0)) >= curr_h:
                is_high = False
                break
        if is_high:
            swings.append(SwingPoint(index=i, price=curr_h, point_type="SWING_HIGH", timestamp=candles[i].get("timestamp")))

        # Check Swing Low
        is_low = True
        for j in range(i - window, i + window + 1):
            if j != i and float(candles[j].get("low", 0)) <= curr_l:
                is_low = False
                break
        if is_low:
            swings.append(SwingPoint(index=i, price=curr_l, point_type="SWING_LOW", timestamp=candles[i].get("timestamp")))

    return swings


def extract_market_structure(
    candles: list[dict],
    current_price: Optional[float] = None,
    prior_day_high: Optional[float] = None,
    prior_day_low: Optional[float] = None,
    window: int = 3,
) -> MarketStructureFeatures:
    """Computes comprehensive market structure features from historical candles."""
    if not candles:
        return MarketStructureFeatures(
            prior_day_high=prior_day_high,
            prior_day_low=prior_day_low,
        )

    p = current_price if current_price is not None else float(candles[-1].get("close", 0))
    session_h = max(float(c.get("high", 0)) for c in candles)
    session_l = min(float(c.get("low", float("inf"))) for c in candles)

    swings = extract_swing_points(candles, window=window)
    swing_highs = [s for s in swings if s.point_type == "SWING_HIGH"]
    swing_lows = [s for s in swings if s.point_type == "SWING_LOW"]

    recent_sh = swing_highs[-1].price if swing_highs else None
    recent_sl = swing_lows[-1].price if swing_lows else None

    structure_type = "RANGE"
    trend_bias = "NEUTRAL"

    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        sh1, sh2 = swing_highs[-2].price, swing_highs[-1].price
        sl1, sl2 = swing_lows[-2].price, swing_lows[-1].price

        if sh2 > sh1 and sl2 > sl1:
            structure_type = "HH_HL"
            trend_bias = "BULLISH"
        elif sh2 < sh1 and sl2 < sl1:
            structure_type = "LH_LL"
            trend_bias = "BEARISH"
        elif sh2 > sh1 and sl2 < sl1:
            structure_type = "EXPANDING"
        else:
            structure_type = "RANGE"

    # Break of Structure & CHoCH checks
    is_bos_bull = False
    is_bos_bear = False
    is_choch_bull = False
    is_choch_bear = False

    if recent_sh and p > recent_sh:
        if trend_bias == "BULLISH":
            is_bos_bull = True
        elif trend_bias == "BEARISH":
            is_choch_bull = True

    if recent_sl and p < recent_sl:
        if trend_bias == "BEARISH":
            is_bos_bear = True
        elif trend_bias == "BULLISH":
            is_choch_bear = True

    # Liquidity Sweep Reclaim Check (last 3 candles)
    high_sweep = False
    low_sweep = False
    swept_lvl = None

    if len(candles) >= 3:
        # Check if any level was pierced by high/low but closed back within
        prior_h = max(float(c.get("high", 0)) for c in candles[:-1])
        prior_l = min(float(c.get("low", float("inf"))) for c in candles[:-1])
        target_high_level = recent_sh or prior_h
        target_low_level = recent_sl or prior_l

        last_c = candles[-1]
        prev_c = candles[-2]
        
        last_close = float(last_c.get("close", 0))
        last_high = float(last_c.get("high", 0))
        last_low = float(last_c.get("low", 0))
        prev_high = float(prev_c.get("high", 0))
        prev_low = float(prev_c.get("low", 0))

        # Bearish sweep: High pierced level, but close is back BELOW level
        if target_high_level and (last_high > target_high_level or prev_high > target_high_level) and last_close < target_high_level:
            high_sweep = True
            swept_lvl = target_high_level

        # Bullish sweep: Low undercut level, but close is back ABOVE level
        if target_low_level and (last_low < target_low_level or prev_low < target_low_level) and last_close > target_low_level:
            low_sweep = True
            swept_lvl = target_low_level

    return MarketStructureFeatures(
        structure_type=structure_type,
        trend_bias=trend_bias,
        recent_swing_high=recent_sh,
        recent_swing_low=recent_sl,
        session_high=session_h,
        session_low=session_l,
        prior_day_high=prior_day_high,
        prior_day_low=prior_day_low,
        is_bos_bullish=is_bos_bull,
        is_bos_bearish=is_bos_bear,
        is_choch_bullish=is_choch_bull,
        is_choch_bearish=is_choch_bear,
        high_swept_and_reclaimed=high_sweep,
        low_swept_and_reclaimed=low_sweep,
        swept_level=swept_lvl,
    )
