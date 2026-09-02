"""
Empirical Support & Resistance Engine — §26, §27, §28, §29
Detects multi-touch price pivot clusters, Volume Profile (POC/HVN), Options OI Strike Walls, and applies recency decay.
"""
from __future__ import annotations

import math
from app.quant.historical_intelligence.models import CandleData, SupportResistanceZone


def detect_support_resistance_zones(
    candles: list[CandleData],
    oi_call_walls: list[float] | None = None,
    oi_put_walls: list[float] | None = None,
    max_zones: int = 8,
) -> list[SupportResistanceZone]:
    """
    Computes adaptive Support and Resistance zones from:
    1. Swing Highs and Swing Lows (Fractal pivots).
    2. Volume Profile clusters (POC / High Volume Nodes).
    3. Options Call/Put Open Interest concentration walls.
    """
    if len(candles) < 20:
        return []

    curr_price = candles[-1].close
    curr_ts = candles[-1].timestamp_utc

    # 1. Calculate Average True Range (ATR) for adaptive tolerance (§27)
    trs = [max(c.high - c.low, abs(c.high - candles[i-1].close) if i > 0 else 0) for i, c in enumerate(candles)]
    atr = sum(trs[-14:]) / min(14, len(trs)) if trs else curr_price * 0.005
    tolerance = max(atr * 0.6, curr_price * 0.0015)

    # 2. Extract Swing Highs and Swing Lows
    raw_pivots: list[tuple[float, str, int, float]] = []  # (price, type, ts, volume)
    n = len(candles)

    for i in range(2, n - 2):
        c = candles[i]
        # Swing High
        if c.high > candles[i-1].high and c.high > candles[i-2].high and c.high > candles[i+1].high and c.high > candles[i+2].high:
            raw_pivots.append((c.high, "RESISTANCE", c.timestamp_utc, c.volume))
        # Swing Low
        if c.low < candles[i-1].low and c.low < candles[i-2].low and c.low < candles[i+1].low and c.low < candles[i+2].low:
            raw_pivots.append((c.low, "SUPPORT", c.timestamp_utc, c.volume))

    # 3. Volume Profile (POC and Volume Concentration)
    price_bins: dict[float, float] = {}
    step = round(tolerance / 2.0, 2) or 5.0
    for c in candles:
        bin_p = round(c.close / step) * step
        price_bins[bin_p] = price_bins.get(bin_p, 0.0) + c.volume

    poc_price = max(price_bins.keys(), key=lambda k: price_bins[k]) if price_bins else curr_price
    max_vol = price_bins.get(poc_price, 1.0) or 1.0

    # 4. Cluster Pivots into Adaptive Zones (§27)
    clusters: list[list[tuple[float, str, int, float]]] = []

    for p in sorted(raw_pivots, key=lambda x: x[0]):
        added = False
        for cl in clusters:
            cl_avg = sum(x[0] for x in cl) / len(cl)
            if abs(p[0] - cl_avg) <= tolerance:
                cl.append(p)
                added = True
                break
        if not added:
            clusters.append([p])

    # 5. Build S/R Zones & Calculate Strength Score (§28, §29)
    zones: list[SupportResistanceZone] = []

    for idx, cl in enumerate(clusters):
        touches = len(cl)
        prices = [x[0] for x in cl]
        zone_low = min(prices)
        zone_high = max(prices)
        zone_center = sum(prices) / touches
        zone_width = max(zone_high - zone_low, tolerance * 0.5)

        last_test = max(x[2] for x in cl)
        age_hours = max(0.1, (curr_ts - last_test) / (1000.0 * 3600.0))

        # Recency decay: exp(-age / 48 hours)
        recency_score = math.exp(-age_hours / 48.0)

        # Volume strength from profile
        nearest_bin = min(price_bins.keys(), key=lambda k: abs(k - zone_center)) if price_bins else zone_center
        vol_strength = min(1.0, price_bins.get(nearest_bin, 0.0) / max_vol)

        # Options OI wall check
        is_oi_wall = False
        oi_strength = 0.0
        if oi_call_walls and any(abs(w - zone_center) <= tolerance for w in oi_call_walls):
            is_oi_wall = True
            oi_strength = 0.85
        if oi_put_walls and any(abs(w - zone_center) <= tolerance for w in oi_put_walls):
            is_oi_wall = True
            oi_strength = 0.85

        is_poc = abs(poc_price - zone_center) <= tolerance

        # Determine Zone Type
        z_type = "RESISTANCE" if zone_center > curr_price else "SUPPORT"

        # Strength Score (0 - 100) per §28
        touch_score = min(40.0, touches * 12.0)
        vol_score = vol_strength * 25.0
        rec_score = recency_score * 15.0
        oi_score = oi_strength * 20.0
        poc_bonus = 10.0 if is_poc else 0.0

        strength = min(100.0, touch_score + vol_score + rec_score + oi_score + poc_bonus)

        # Filter out single-touch weak wicks unless they align with POC or OI wall
        if touches >= 2 or is_poc or is_oi_wall:
            zone_id = f"sr_{z_type.lower()}_{int(zone_center)}"
            zones.append(SupportResistanceZone(
                zone_id=zone_id,
                zone_type=z_type,
                zone_center=round(zone_center, 2),
                zone_low=round(zone_low, 2),
                zone_high=round(zone_high, 2),
                zone_width=round(zone_width, 2),
                touch_count=touches,
                volume_strength=round(vol_strength, 2),
                oi_strength=round(oi_strength, 2),
                recency_score=round(recency_score, 2),
                strength_score=round(strength, 1),
                is_poc=is_poc,
                is_oi_wall=is_oi_wall,
                last_tested_ts=last_test,
            ))

    # Sort zones by strength descending and take top N
    zones.sort(key=lambda z: z.strength_score, reverse=True)
    return zones[:max_zones]
