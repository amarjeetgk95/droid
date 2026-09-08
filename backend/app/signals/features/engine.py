"""
Central Feature Engine & Snapshot Provider (§17).
Produces unified, immutable FeatureSnapshot objects combining Price, Trend, Momentum,
Volatility, Volume, EMA states, and Market Structure.
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel, Field

from app.signals.features.ema_features import EMAFeatures, extract_ema_features
from app.signals.features.structure import MarketStructureFeatures, extract_market_structure


class FeatureSnapshot(BaseModel):
    underlying: str
    spot_price: float
    timeframe: str
    timestamp_ms: int
    
    # Feature Domains
    ema: EMAFeatures = Field(default_factory=EMAFeatures)
    structure: MarketStructureFeatures = Field(default_factory=MarketStructureFeatures)
    
    # Momentum & Velocity
    roc_1: float = 0.0                     # 1-bar return %
    roc_3: float = 0.0                     # 3-bar return %
    roc_5: float = 0.0                     # 5-bar return %
    momentum_acceleration: float = 0.0     # Change in ROC
    rsi: Optional[float] = None
    macd_histogram: Optional[float] = None
    
    # Volatility & Range Compression
    atr: float = 20.0
    atr_pct: float = 0.0                   # ATR as % of spot
    is_volatility_compressed: bool = False # Bollinger squeeze / ATR contraction
    is_volatility_expanding: bool = False
    
    # Volume & Participation Proxies
    rvol: float = 1.0                      # Relative Volume vs 20 MA
    volume_acceleration: float = 0.0       # Volume ROC
    vwap: Optional[float] = None
    distance_to_vwap_pct: float = 0.0
    vwap_slope: float = 0.0
    
    # Raw context pass-through
    raw_indicators: dict[str, Any] = Field(default_factory=dict)


def compute_feature_snapshot(
    underlying: str,
    spot_price: float,
    candles: list[dict],
    timeframe: str = "5M",
    vwap: Optional[float] = None,
    indicators: Optional[dict[str, Any]] = None,
    timestamp_ms: Optional[int] = None,
    prior_day_high: Optional[float] = None,
    prior_day_low: Optional[float] = None,
) -> FeatureSnapshot:
    """Computes a complete, unified FeatureSnapshot from candle data and live context."""
    ts = timestamp_ms if timestamp_ms is not None else int(__import__("time").time() * 1000)
    ind = indicators or {}
    closes = [float(c.get("close", 0)) for c in candles] if candles else []

    # 1. EMA Features
    ema_feat = extract_ema_features(closes, current_price=spot_price)

    # 2. Market Structure Features
    struct_feat = extract_market_structure(
        candles,
        current_price=spot_price,
        prior_day_high=prior_day_high,
        prior_day_low=prior_day_low,
    )

    # 3. Momentum & Velocity
    r1, r3, r5, acc = 0.0, 0.0, 0.0, 0.0
    if len(closes) >= 2 and closes[-2] > 0:
        r1 = round((closes[-1] - closes[-2]) / closes[-2] * 100.0, 3)
    if len(closes) >= 4 and closes[-4] > 0:
        r3 = round((closes[-1] - closes[-4]) / closes[-4] * 100.0, 3)
    if len(closes) >= 6 and closes[-6] > 0:
        r5 = round((closes[-1] - closes[-6]) / closes[-6] * 100.0, 3)
        # Acceleration: r1 vs prior r1
        prior_r1 = (closes[-2] - closes[-3]) / closes[-3] * 100.0 if closes[-3] > 0 else 0.0
        acc = round(r1 - prior_r1, 4)

    rsi_val = None
    if "momentum" in ind and isinstance(ind["momentum"], dict):
        rsi_val = ind["momentum"].get("rsi")
    elif "rsi" in ind:
        rsi_val = ind.get("rsi")

    macd_hist = None
    if "momentum" in ind and isinstance(ind["momentum"], dict):
        macd_hist = ind["momentum"].get("macd_hist")

    # 4. Volatility & Compression
    atr_val = 20.0
    if "volatility" in ind and isinstance(ind["volatility"], dict):
        atr_val = float(ind["volatility"].get("atr", 20.0))
    elif "atr" in ind:
        atr_val = float(ind.get("atr", 20.0))

    atr_pct_val = round((atr_val / spot_price * 100.0), 3) if spot_price > 0 else 0.0

    # Compression check: Bandwidth or range narrowness
    is_compressed = False
    is_expanding = False
    if "volatility" in ind and isinstance(ind["volatility"], dict):
        bw = float(ind["volatility"].get("bollinger_bandwidth", 0.0) or 0.0)
        if bw > 0:
            is_compressed = bw < 0.015  # <1.5% bandwidth
            is_expanding = bw > 0.035
    elif ema_feat.is_compressed:
        is_compressed = True

    # 5. Volume & Participation
    rvol_val = 1.0
    vol_acc_val = 0.0
    if len(candles) >= 5:
        recent_v = [float(c.get("volume", 0)) for c in candles[-5:]]
        avg_v = sum(float(c.get("volume", 0)) for c in candles[-20:]) / max(1, min(20, len(candles)))
        if avg_v > 0:
            rvol_val = round(recent_v[-1] / avg_v, 2)
        if len(recent_v) >= 2 and recent_v[-2] > 0:
            vol_acc_val = round((recent_v[-1] - recent_v[-2]) / recent_v[-2], 3)

    # 6. VWAP Distance & Slope
    vwap_val = vwap
    dist_vwap = 0.0
    vwap_slope_val = 0.0
    if vwap_val and vwap_val > 0:
        dist_vwap = round((spot_price - vwap_val) / vwap_val * 100.0, 3)
        # Approximate VWAP slope from spot vs close
        if len(closes) >= 3 and closes[-3] > 0:
            vwap_slope_val = round((closes[-1] - closes[-3]) / closes[-3] * 100.0, 4)

    return FeatureSnapshot(
        underlying=underlying,
        spot_price=spot_price,
        timeframe=timeframe,
        timestamp_ms=ts,
        ema=ema_feat,
        structure=struct_feat,
        roc_1=r1,
        roc_3=r3,
        roc_5=r5,
        momentum_acceleration=acc,
        rsi=rsi_val,
        macd_histogram=macd_hist,
        atr=atr_val,
        atr_pct=atr_pct_val,
        is_volatility_compressed=is_compressed,
        is_volatility_expanding=is_expanding,
        rvol=rvol_val,
        volume_acceleration=vol_acc_val,
        vwap=vwap_val,
        distance_to_vwap_pct=dist_vwap,
        vwap_slope=vwap_slope_val,
        raw_indicators=ind,
    )
