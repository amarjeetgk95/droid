"""
Technical Feature Engine for Swing Trading (v5.0 §7).
Pure deterministic calculations of:
  - 20 EMA, 50 SMA, 150 SMA, 200 SMA
  - ATR(14)
  - 20-day Volume SMA & Relative Volume (RVOL)
  - 52-Week High & Low metrics
  - Multi-bar Volatility Contraction & Range metrics
  - Swing Pivots (Highs & Lows)
"""
from __future__ import annotations

import math
from typing import Any
from pydantic import BaseModel, Field


class SwingFeatures(BaseModel):
    close: float
    open: float
    high: float
    low: float
    volume: int

    # Moving Averages
    ema_20: float | None = None
    sma_50: float | None = None
    sma_150: float | None = None
    sma_200: float | None = None

    # Trend Structure Flags
    price_above_ema20: bool = False
    price_above_sma50: bool = False
    price_above_sma200: bool = False
    sma50_above_sma200: bool = False
    sma200_slope_positive: bool = False

    # Volatility & Range
    atr_14: float = 0.0
    atr_pct: float = 0.0                     # (ATR / Close) * 100

    # Volume Metrics
    volume_sma_20: float = 0.0
    rvol: float = 1.0                        # Relative volume today
    volume_dry_up: bool = False              # Today's volume < 60% of 20d avg

    # 52-Week Context
    high_52w: float = 0.0
    low_52w: float = 0.0
    dist_from_52w_high_pct: float = 0.0      # % distance from 52w high

    # Swing Pivots
    recent_swing_high: float = 0.0           # Highest high in last 20 bars
    recent_swing_low: float = 0.0            # Lowest low in last 20 bars
    pivot_breakout_level: float = 0.0

    # Contraction Metrics (VCP)
    daily_range_pct: float = 0.0             # (High - Low) / Close * 100
    avg_range_5d_pct: float = 0.0
    avg_range_20d_pct: float = 0.0
    range_contraction_ratio: float = 1.0     # 5d avg range / 20d avg range

    # Intraday Specific Metrics
    vwap: float | None = None
    price_above_vwap: bool = False
    opening_range_high: float = 0.0          # High of first 30m / ORB
    opening_range_low: float = 0.0           # Low of first 30m / ORB
    is_orb_bullish: bool = False             # Price > Opening Range High
    is_orb_bearish: bool = False             # Price < Opening Range Low


def compute_ema(series: list[float], period: int) -> list[float]:
    """Calculates Exponential Moving Average."""
    if len(series) < period or period <= 0:
        return [float("nan")] * len(series)

    ema = [float("nan")] * len(series)
    # Start with SMA for the first period
    initial_sma = sum(series[:period]) / period
    ema[period - 1] = initial_sma

    multiplier = 2.0 / (period + 1.0)
    for i in range(period, len(series)):
        ema[i] = (series[i] - ema[i - 1]) * multiplier + ema[i - 1]

    return ema


def compute_sma(series: list[float], period: int) -> list[float]:
    """Calculates Simple Moving Average."""
    if len(series) < period or period <= 0:
        return [float("nan")] * len(series)

    sma = [float("nan")] * len(series)
    window_sum = sum(series[:period])
    sma[period - 1] = window_sum / period

    for i in range(period, len(series)):
        window_sum += series[i] - series[i - period]
        sma[i] = window_sum / period

    return sma


def compute_atr(candles: list[dict[str, Any]], period: int = 14) -> list[float]:
    """Calculates Average True Range (Wilder's ATR)."""
    if len(candles) < 2:
        return [0.0] * len(candles)

    tr: list[float] = [candles[0]["high"] - candles[0]["low"]]
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        prev_c = candles[i - 1]["close"]
        true_range = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr.append(true_range)

    if len(tr) < period:
        return [sum(tr) / len(tr)] * len(candles)

    atr = [float("nan")] * len(candles)
    atr[period - 1] = sum(tr[:period]) / period
    for i in range(period, len(candles)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


def extract_swing_features(candles: list[dict[str, Any]]) -> SwingFeatures:
    """
    Extracts all swing-trading features from finalized daily candles.
    Expects candles ordered chronologically.
    """
    if not candles:
        raise ValueError("Cannot extract features from empty candle list.")

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [float(c["volume"]) for c in candles]

    n = len(candles)
    last_c = candles[-1]
    curr_close = float(last_c["close"])
    curr_open = float(last_c["open"])
    curr_high = float(last_c["high"])
    curr_low = float(last_c["low"])
    curr_vol = int(last_c["volume"])

    # 1. Moving Averages
    ema20_series = compute_ema(closes, 20)
    sma50_series = compute_sma(closes, 50)
    sma150_series = compute_sma(closes, 150)
    sma200_series = compute_sma(closes, 200)

    ema20 = ema20_series[-1] if not math.isnan(ema20_series[-1]) else None
    sma50 = sma50_series[-1] if not math.isnan(sma50_series[-1]) else None
    sma150 = sma150_series[-1] if not math.isnan(sma150_series[-1]) else None
    sma200 = sma200_series[-1] if not math.isnan(sma200_series[-1]) else None

    # SMA 200 Slope (over last 20 bars)
    sma200_slope_pos = False
    if sma200 is not None and len(sma200_series) >= 20 and not math.isnan(sma200_series[-20]):
        sma200_slope_pos = sma200 > sma200_series[-20]

    # 2. ATR(14)
    atr_series = compute_atr(candles, 14)
    atr14 = atr_series[-1] if not math.isnan(atr_series[-1]) else (curr_high - curr_low)
    atr_pct = (atr14 / curr_close * 100.0) if curr_close > 0 else 0.0

    # 3. Volume metrics
    vol_sma_series = compute_sma(volumes, 20)
    vol_sma20 = vol_sma_series[-1] if not math.isnan(vol_sma_series[-1]) else (sum(volumes[-5:]) / max(1, len(volumes[-5:])))
    rvol = (curr_vol / vol_sma20) if vol_sma20 > 0 else 1.0
    volume_dry_up = rvol <= 0.60

    # 4. 52-Week High/Low (or available history up to 252 bars)
    lookback_52w = min(n, 252)
    h52 = max(highs[-lookback_52w:])
    l52 = min(lows[-lookback_52w:])
    dist_52w = ((curr_close - h52) / h52 * 100.0) if h52 > 0 else 0.0

    # 5. Swing Pivots (Last 20 bars)
    pivot_lookback = min(n, 20)
    recent_sw_high = max(highs[-pivot_lookback:])
    recent_sw_low = min(lows[-pivot_lookback:])
    # Prior swing high excluding the current bar
    prior_pivot_high = max(highs[-pivot_lookback:-1]) if pivot_lookback > 1 else recent_sw_high

    # 6. Volatility Contraction / Range compression
    daily_range_pct = ((curr_high - curr_low) / curr_close * 100.0) if curr_close > 0 else 0.0
    
    ranges_pct = [((highs[i] - lows[i]) / closes[i] * 100.0) if closes[i] > 0 else 0.0 for i in range(n)]
    avg_range_5d = sum(ranges_pct[-5:]) / max(1, len(ranges_pct[-5:]))
    avg_range_20d = sum(ranges_pct[-20:]) / max(1, len(ranges_pct[-20:]))
    contraction_ratio = (avg_range_5d / avg_range_20d) if avg_range_20d > 0 else 1.0

    return SwingFeatures(
        close=curr_close,
        open=curr_open,
        high=curr_high,
        low=curr_low,
        volume=curr_vol,
        ema_20=ema20,
        sma_50=sma50,
        sma_150=sma150,
        sma_200=sma200,
        price_above_ema20=(curr_close > ema20) if ema20 is not None else False,
        price_above_sma50=(curr_close > sma50) if sma50 is not None else False,
        price_above_sma200=(curr_close > sma200) if sma200 is not None else False,
        sma50_above_sma200=(sma50 > sma200) if (sma50 is not None and sma200 is not None) else False,
        sma200_slope_positive=sma200_slope_pos,
        atr_14=round(atr14, 2),
        atr_pct=round(atr_pct, 2),
        volume_sma_20=round(vol_sma20, 0),
        rvol=round(rvol, 2),
        volume_dry_up=volume_dry_up,
        high_52w=round(h52, 2),
        low_52w=round(l52, 2),
        dist_from_52w_high_pct=round(dist_52w, 2),
        recent_swing_high=round(recent_sw_high, 2),
        recent_swing_low=round(recent_sw_low, 2),
        pivot_breakout_level=round(prior_pivot_high, 2),
        daily_range_pct=round(daily_range_pct, 2),
        avg_range_5d_pct=round(avg_range_5d, 2),
        avg_range_20d_pct=round(avg_range_20d, 2),
        range_contraction_ratio=round(contraction_ratio, 2),
    )


def extract_intraday_swing_features(candles: list[dict[str, Any]]) -> SwingFeatures:
    """
    Extracts intraday swing features from 15M / 5M candles.
    Computes:
      - 20 EMA & 50 SMA on intraday timeframe
      - Intraday VWAP (Volume Weighted Average Price)
      - Opening Range (first 2 bars of 15M session or first 6 bars of 5M session)
      - 14-period intraday ATR
      - Intraday Relative Volume (RVOL)
    """
    if len(candles) < 5:
        raise ValueError("Insufficient intraday candles to extract features (minimum 5 required).")

    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    opens = [float(c["open"]) for c in candles]
    volumes = [int(c.get("volume", 0)) for c in candles]

    curr_close = closes[-1]
    curr_open = opens[-1]
    curr_high = highs[-1]
    curr_low = lows[-1]
    curr_vol = volumes[-1]

    # 1. Intraday Moving Averages
    ema20_series = compute_ema(closes, min(20, len(closes)))
    ema20 = ema20_series[-1] if not math.isnan(ema20_series[-1]) else None

    sma50_series = compute_sma(closes, min(50, len(closes)))
    sma50 = sma50_series[-1] if not math.isnan(sma50_series[-1]) else None

    # 2. Intraday VWAP
    cum_vol = 0.0
    cum_tp_vol = 0.0
    for h, l, c, v in zip(highs, lows, closes, volumes):
        tp = (h + l + c) / 3.0
        v_eff = max(1, v)
        cum_tp_vol += tp * v_eff
        cum_vol += v_eff
    vwap_val = round(cum_tp_vol / cum_vol, 2) if cum_vol > 0 else curr_close
    price_above_vwap = curr_close >= vwap_val

    # 3. Opening Range
    or_bars = min(len(candles), 2 if len(candles) <= 25 else 6)
    or_high = round(max(highs[:or_bars]), 2)
    or_low = round(min(lows[:or_bars]), 2)
    is_orb_bull = curr_close > or_high
    is_orb_bear = curr_close < or_low

    # 4. Intraday ATR(14)
    atr14_series = compute_atr(candles, period=min(14, len(candles) - 1))
    atr14 = atr14_series[-1] if not math.isnan(atr14_series[-1]) else max(1.0, curr_high - curr_low)
    atr_pct = (atr14 / curr_close) * 100.0 if curr_close > 0 else 0.0

    # 5. Relative Volume
    vol_period = min(20, len(volumes))
    vol_sma20 = sum(volumes[-vol_period:]) / vol_period if vol_period > 0 else 1.0
    rvol = curr_vol / vol_sma20 if vol_sma20 > 0 else 1.0

    # 6. Intraday Swings
    lookback_sw = min(15, len(candles))
    recent_sw_high = max(highs[-lookback_sw:])
    recent_sw_low = min(lows[-lookback_sw:])

    return SwingFeatures(
        close=curr_close,
        open=curr_open,
        high=curr_high,
        low=curr_low,
        volume=curr_vol,
        ema_20=round(ema20, 2) if ema20 is not None else None,
        sma_50=round(sma50, 2) if sma50 is not None else None,
        sma_150=None,
        sma_200=None,
        price_above_ema20=(curr_close > ema20) if ema20 is not None else False,
        price_above_sma50=(curr_close > sma50) if sma50 is not None else False,
        price_above_sma200=False,
        sma50_above_sma200=False,
        sma200_slope_positive=False,
        atr_14=round(atr14, 2),
        atr_pct=round(atr_pct, 2),
        volume_sma_20=round(vol_sma20, 0),
        rvol=round(rvol, 2),
        volume_dry_up=(curr_vol < 0.6 * vol_sma20) if vol_sma20 > 0 else False,
        high_52w=recent_sw_high,
        low_52w=recent_sw_low,
        dist_from_52w_high_pct=0.0,
        recent_swing_high=round(recent_sw_high, 2),
        recent_swing_low=round(recent_sw_low, 2),
        pivot_breakout_level=round(recent_sw_high, 2),
        daily_range_pct=round(((curr_high - curr_low) / curr_close) * 100.0, 2) if curr_close > 0 else 0.0,
        avg_range_5d_pct=round(atr_pct, 2),
        avg_range_20d_pct=round(atr_pct, 2),
        range_contraction_ratio=1.0,
        vwap=vwap_val,
        price_above_vwap=price_above_vwap,
        opening_range_high=or_high,
        opening_range_low=or_low,
        is_orb_bullish=is_orb_bull,
        is_orb_bearish=is_orb_bear,
    )



# ---------------------------------------------------------------------------
# Options Volatility & IV Surface Helpers
# ---------------------------------------------------------------------------
def compute_iv_percentile(current_iv: float, iv_history: list[float]) -> float:
    """
    Computes IV percentile rank (0-100) — percentage of historical observations strictly below current_iv.
    """
    if not iv_history:
        return 50.0
    valid_obs = [x for x in iv_history if x is not None and not math.isnan(x) and x > 0]
    if not valid_obs:
        return 50.0
    below = sum(1 for x in valid_obs if x < current_iv)
    return round((below / len(valid_obs)) * 100.0, 1)


def classify_iv_regime(iv_percentile: float) -> Literal["LOW", "NORMAL", "ELEVATED", "EXTREME"]:
    """
    Classifies volatility regime based on percentile rank:
    LOW < 25, NORMAL 25-60, ELEVATED 60-85, EXTREME > 85.
    """
    if iv_percentile < 25.0:
        return "LOW"
    elif iv_percentile <= 60.0:
        return "NORMAL"
    elif iv_percentile <= 85.0:
        return "ELEVATED"
    else:
        return "EXTREME"


def compute_iv_edge(expected_move: float, implied_move: float) -> float:
    """
    Calculates expected_move / implied_move ratio.
    Values > 1.0 favor long premium (realized move expected to exceed option premium implied move).
    """
    if implied_move <= 0:
        return 1.0
    return round(expected_move / implied_move, 2)
