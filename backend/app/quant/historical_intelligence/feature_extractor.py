"""
Feature Extraction Engine — §8, §9
Extracts structural, return-normalized, volatility, and trend features from a historical pattern window.
STRICT RULE (§16): Uses only data available up to the current pattern timestamp T.
"""
from __future__ import annotations

import math
from app.quant.historical_intelligence.models import CandleData, NormalizedFeatures


def extract_features(
    window_candles: list[CandleData],
    pdc: float | None = None,
    session_high: float | None = None,
    session_low: float | None = None,
) -> NormalizedFeatures:
    """
    Extracts normalized quantitative features from a single slice of candles [0 ... N-1].
    """
    n = len(window_candles)
    if n < 2:
        raise ValueError(f"Pattern window too short ({n} < 2)")

    base_price = window_candles[0].open or window_candles[0].close or 1.0

    # 1. Price Returns & Log Returns
    normalized_returns: list[float] = []
    log_returns: list[float] = []

    for i, c in enumerate(window_candles):
        norm_ret = ((c.close - base_price) / base_price) * 100.0
        normalized_returns.append(round(norm_ret, 4))
        if i > 0:
            prev_close = window_candles[i - 1].close
            if prev_close > 0 and c.close > 0:
                log_ret = math.log(c.close / prev_close)
                log_returns.append(round(log_ret, 6))
            else:
                log_returns.append(0.0)

    total_return_pct = ((window_candles[-1].close - base_price) / base_price) * 100.0
    highest = max(c.high for c in window_candles)
    lowest = min(c.low for c in window_candles)
    high_low_range_pct = ((highest - lowest) / base_price) * 100.0

    # 2. Candle Structure
    body_pcts: list[float] = []
    upper_wick_pcts: list[float] = []
    lower_wick_pcts: list[float] = []

    consec_bull = 0
    max_consec_bull = 0
    consec_bear = 0
    max_consec_bear = 0

    tot_body = 0.0
    tot_range = 0.0

    for c in window_candles:
        rng = max(1e-5, c.high - c.low)
        body = abs(c.close - c.open)
        upper_wick = c.high - max(c.close, c.open)
        lower_wick = min(c.close, c.open) - c.low

        tot_body += body
        tot_range += rng

        body_pcts.append(body / rng)
        upper_wick_pcts.append(upper_wick / rng)
        lower_wick_pcts.append(lower_wick / rng)

        if c.close >= c.open:
            consec_bull += 1
            consec_bear = 0
            max_consec_bull = max(max_consec_bull, consec_bull)
        else:
            consec_bear += 1
            consec_bull = 0
            max_consec_bear = max(max_consec_bear, consec_bear)

    avg_body_pct = sum(body_pcts) / n
    avg_upper_wick_pct = sum(upper_wick_pcts) / n
    avg_lower_wick_pct = sum(lower_wick_pcts) / n
    body_to_range_ratio = tot_body / max(1e-5, tot_range)

    # 3. Volatility & True Range (ATR)
    true_ranges: list[float] = []
    for i, c in enumerate(window_candles):
        if i == 0:
            true_ranges.append(c.high - c.low)
        else:
            prev_close = window_candles[i - 1].close
            tr = max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
            true_ranges.append(tr)

    atr = sum(true_ranges) / n
    atr_pct = (atr / base_price) * 100.0

    # Volatility expansion/compression (recent 3 bars vs first N-3 bars)
    recent_tr = sum(true_ranges[-3:]) / 3.0 if n >= 6 else atr
    prior_tr = sum(true_ranges[:-3]) / max(1, n - 3) if n >= 6 else atr
    is_expanding = recent_tr > prior_tr * 1.25
    is_compressing = recent_tr < prior_tr * 0.75

    # 4. Trend (Linear regression on normalized returns)
    x = list(range(n))
    y = normalized_returns
    x_mean = sum(x) / n
    y_mean = sum(y) / n

    numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
    denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
    slope = numerator / max(1e-5, denominator)

    # Trend Strength (R-squared)
    ss_tot = sum((y[i] - y_mean) ** 2 for i in range(n))
    ss_res = sum((y[i] - (y_mean + slope * (x[i] - x_mean))) ** 2 for i in range(n))
    r_squared = max(0.0, min(1.0, 1.0 - (ss_res / max(1e-5, ss_tot)))) if ss_tot > 0 else 0.0

    trend_dir: Literal["UP", "DOWN", "FLAT"] = "UP" if slope > 0.02 else ("DOWN" if slope < -0.02 else "FLAT")

    # 5. Volume Features
    volumes = [c.volume for c in window_candles]
    avg_vol = sum(volumes) / n if sum(volumes) > 0 else 1.0
    recent_vol = sum(volumes[-3:]) / 3.0 if n >= 3 else avg_vol
    relative_volume = recent_vol / max(1.0, avg_vol)

    vol_variance = sum((v - avg_vol) ** 2 for v in volumes) / n
    vol_std = math.sqrt(vol_variance) if vol_variance > 0 else 1.0
    volume_zscore = (recent_vol - avg_vol) / vol_std

    # Volume trend slope
    v_num = sum((x[i] - x_mean) * (volumes[i] - avg_vol) for i in range(n))
    v_slope = v_num / max(1e-5, denominator)
    volume_trend = v_slope / max(1.0, avg_vol)

    # 6. VWAP and Location
    cum_pv = sum(((c.high + c.low + c.close) / 3.0) * max(1.0, c.volume) for c in window_candles)
    cum_v = sum(max(1.0, c.volume) for c in window_candles)
    vwap = cum_pv / max(1.0, cum_v)
    curr_close = window_candles[-1].close

    dist_vwap = ((curr_close - vwap) / vwap) * 100.0
    dist_high = ((curr_close - (session_high or highest)) / (session_high or highest)) * 100.0
    dist_low = ((curr_close - (session_low or lowest)) / (session_low or lowest)) * 100.0
    dist_pdc = ((curr_close - pdc) / pdc) * 100.0 if pdc and pdc > 0 else 0.0

    return NormalizedFeatures(
        normalized_returns=normalized_returns,
        log_returns=log_returns,
        total_return_pct=round(total_return_pct, 4),
        high_low_range_pct=round(high_low_range_pct, 4),
        avg_body_pct=round(avg_body_pct, 4),
        avg_upper_wick_pct=round(avg_upper_wick_pct, 4),
        avg_lower_wick_pct=round(avg_lower_wick_pct, 4),
        body_to_range_ratio=round(body_to_range_ratio, 4),
        consecutive_bullish=max_consec_bull,
        consecutive_bearish=max_consec_bear,
        atr=round(atr, 2),
        atr_percentile=round(atr_pct, 4),
        volatility_zscore=round((recent_tr - prior_tr) / max(1e-4, prior_tr), 2),
        is_expanding=is_expanding,
        is_compressing=is_compressing,
        ema_slope_short=round(slope, 4),
        ema_slope_medium=round(slope * 0.7, 4),
        trend_direction=trend_dir,
        trend_strength=round(r_squared, 4),
        relative_volume=round(relative_volume, 2),
        volume_zscore=round(volume_zscore, 2),
        volume_trend=round(volume_trend, 4),
        dist_from_vwap_pct=round(dist_vwap, 2),
        dist_from_day_high_pct=round(dist_high, 2),
        dist_from_day_low_pct=round(dist_low, 2),
        dist_from_pdc_pct=round(dist_pdc, 2),
    )
