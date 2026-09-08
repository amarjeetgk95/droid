"""
EMA Feature Extraction Module (§16, §17).
Computes multi-period EMA ordering, slopes, ribbon separation, compression/expansion,
and price-to-EMA distances to serve as shared, reusable technical features.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel, Field


class EMAFeatures(BaseModel):
    ema_fast: Optional[float] = None       # e.g., EMA 8 / 9
    ema_medium: Optional[float] = None     # e.g., EMA 20 / 21
    ema_slow: Optional[float] = None       # e.g., EMA 50 / 55
    ema_trend: Optional[float] = None      # e.g., EMA 200
    
    # Ordering state: BULLISH_EXPANSION | BEARISH_EXPANSION | COMPRESSION | MIXED
    alignment: str = "MIXED"
    is_bullish_ordered: bool = False
    is_bearish_ordered: bool = False
    
    # Velocity & Geometry
    fast_slope: float = 0.0                # Normalized rate of change of fast EMA
    medium_slope: float = 0.0              # Normalized rate of change of medium EMA
    ribbon_separation_pct: float = 0.0     # (Fast - Slow) / Slow * 100
    is_compressed: bool = False            # True when ribbon width is in lowest quartile
    is_expanding: bool = False             # True when ribbon width is widening significantly
    
    # Distance from price
    price_to_ema_fast_pct: float = 0.0
    price_to_ema_medium_pct: float = 0.0
    price_to_ema_slow_pct: float = 0.0
    price_to_ema_trend_pct: Optional[float] = None


def compute_ema_series(values: list[float], period: int) -> list[float]:
    """Computes streaming EMA series for given values, seeded at values[0]."""
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    ema = [values[0]]
    for val in values[1:]:
        ema.append(val * k + ema[-1] * (1.0 - k))
    return ema


def extract_ema_features(
    closes: list[float],
    current_price: Optional[float] = None,
    fast_period: int = 9,
    medium_period: int = 21,
    slow_period: int = 50,
    trend_period: int = 200,
) -> EMAFeatures:
    """Extracts standardized EMA features from a series of closing prices."""
    if not closes:
        return EMAFeatures()
        
    p = current_price if current_price is not None else closes[-1]
    
    ema_f_series = compute_ema_series(closes, fast_period)
    ema_m_series = compute_ema_series(closes, medium_period)
    ema_s_series = compute_ema_series(closes, slow_period)
    ema_t_series = compute_ema_series(closes, trend_period) if len(closes) >= trend_period else []

    ema_f = ema_f_series[-1] if ema_f_series else None
    ema_m = ema_m_series[-1] if ema_m_series else None
    ema_s = ema_s_series[-1] if ema_s_series else None
    ema_t = ema_t_series[-1] if ema_t_series else None

    # Slopes (rate of change over last 2 steps)
    f_slope = 0.0
    if len(ema_f_series) >= 3 and ema_f_series[-3] > 0:
        f_slope = round((ema_f_series[-1] - ema_f_series[-3]) / ema_f_series[-3] * 100.0, 4)

    m_slope = 0.0
    if len(ema_m_series) >= 3 and ema_m_series[-3] > 0:
        m_slope = round((ema_m_series[-1] - ema_m_series[-3]) / ema_m_series[-3] * 100.0, 4)

    # Ordering
    is_bull = False
    is_bear = False
    if ema_f is not None and ema_m is not None and ema_s is not None:
        is_bull = ema_f > ema_m > ema_s
        is_bear = ema_f < ema_m < ema_s

    # Separation
    sep_pct = 0.0
    if ema_f is not None and ema_s is not None and ema_s > 0:
        sep_pct = round(abs(ema_f - ema_s) / ema_s * 100.0, 3)

    # Compression check: separation < 0.25% of price
    is_comp = sep_pct < 0.25 if sep_pct > 0 else False
    is_exp = sep_pct > 0.60 and (abs(f_slope) > 0.10)

    alignment = "MIXED"
    if is_bull and is_exp:
        alignment = "BULLISH_EXPANSION"
    elif is_bear and is_exp:
        alignment = "BEARISH_EXPANSION"
    elif is_comp:
        alignment = "COMPRESSION"
    elif is_bull:
        alignment = "BULLISH"
    elif is_bear:
        alignment = "BEARISH"

    dist_f = round((p - ema_f) / ema_f * 100.0, 3) if ema_f and ema_f > 0 else 0.0
    dist_m = round((p - ema_m) / ema_m * 100.0, 3) if ema_m and ema_m > 0 else 0.0
    dist_s = round((p - ema_s) / ema_s * 100.0, 3) if ema_s and ema_s > 0 else 0.0
    dist_t = round((p - ema_t) / ema_t * 100.0, 3) if ema_t and ema_t > 0 else None

    return EMAFeatures(
        ema_fast=ema_f,
        ema_medium=ema_m,
        ema_slow=ema_s,
        ema_trend=ema_t,
        alignment=alignment,
        is_bullish_ordered=is_bull,
        is_bearish_ordered=is_bear,
        fast_slope=f_slope,
        medium_slope=m_slope,
        ribbon_separation_pct=sep_pct,
        is_compressed=is_comp,
        is_expanding=is_exp,
        price_to_ema_fast_pct=dist_f,
        price_to_ema_medium_pct=dist_m,
        price_to_ema_slow_pct=dist_s,
        price_to_ema_trend_pct=dist_t,
    )
