"""
Liquidity & Structural Level Engine (§5).

Maintains a dynamic Structural Level Map tracking PDH, PDL, PDC, CDO,
Session High/Low, ORH/ORL, VWAP, and rolling swing pivots with dynamic
relevance scoring based on proximity, historical reactions, and recency.
"""
from __future__ import annotations

import math
import time
from typing import List, Optional, Tuple

from app.signals.strategies.vortex_snap.types import (
    Candle,
    LevelType,
    StructuralLevel,
    StructuralLevelMapResult,
)
from app.signals.strategies.vortex_snap.config import StructuralLevelConfig


class StructuralLevelEngine:
    """Computes and updates structural levels with dynamic relevance scoring."""

    def __init__(self, config: Optional[StructuralLevelConfig] = None) -> None:
        self.config = config or StructuralLevelConfig()

    def compute(
        self,
        candles_1m: List[Candle],
        pdh: Optional[float] = None,
        pdl: Optional[float] = None,
        pdc: Optional[float] = None,
        cdo: Optional[float] = None,
        orh: Optional[float] = None,
        orl: Optional[float] = None,
        vwap: Optional[float] = None,
        candles_5m: Optional[List[Candle]] = None,
        volume_nodes: Optional[List[Tuple[float, float]]] = None,
    ) -> StructuralLevelMapResult:
        """Calculate dynamic structural level map at current bar.

        Args:
            candles_1m: History of 1-minute candles up to current bar.
            pdh: Previous day high.
            pdl: Previous day low.
            pdc: Previous day close.
            cdo: Current day open.
            orh: Opening range high (09:15 - 09:30 or 09:45).
            orl: Opening range low.
            vwap: Volume-weighted average price at current bar.
            candles_5m: Optional 5-minute candles for swing detection.
            volume_nodes: Optional list of (price, volume) tuples.

        Returns:
            StructuralLevelMapResult snapshot.
        """
        start_t = time.perf_counter()
        if not candles_1m:
            return StructuralLevelMapResult(computation_time_ms=0.0)

        current_price = candles_1m[-1].close
        raw_levels: List[Tuple[LevelType, float, float]] = []  # (type, price, associated_vol)

        # 1. Macro day levels
        if pdh is not None and pdh > 0:
            raw_levels.append((LevelType.PDH, pdh, 0.0))
        if pdl is not None and pdl > 0:
            raw_levels.append((LevelType.PDL, pdl, 0.0))
        if pdc is not None and pdc > 0:
            raw_levels.append((LevelType.PDC, pdc, 0.0))
        if cdo is not None and cdo > 0:
            raw_levels.append((LevelType.CDO, cdo, 0.0))
        if orh is not None and orh > 0:
            raw_levels.append((LevelType.ORH, orh, 0.0))
        if orl is not None and orl > 0:
            raw_levels.append((LevelType.ORL, orl, 0.0))

        # 2. Intraday Session Extremes (established prior to current candle)
        if len(candles_1m) > 1:
            session_high = max(c.high for c in candles_1m[:-1])
            session_low = min(c.low for c in candles_1m[:-1])
        else:
            session_high = candles_1m[0].high
            session_low = candles_1m[0].low
        raw_levels.append((LevelType.SESSION_HIGH, session_high, 0.0))
        raw_levels.append((LevelType.SESSION_LOW, session_low, 0.0))

        # 3. Dynamic VWAP level
        if vwap is not None and vwap > 0:
            raw_levels.append((LevelType.VWAP, vwap, 0.0))

        # 4. Rolling 5-minute swing pivots
        if candles_5m and len(candles_5m) >= self.config.swing_window_5m * 2 + 1:
            w = self.config.swing_window_5m
            for i in range(w, len(candles_5m) - w):
                cand = candles_5m[i]
                # Swing High
                if all(candles_5m[j].high < cand.high for j in range(i - w, i + w + 1) if j != i):
                    raw_levels.append((LevelType.SWING_HIGH_5M, cand.high, cand.volume))
                # Swing Low
                if all(candles_5m[j].low > cand.low for j in range(i - w, i + w + 1) if j != i):
                    raw_levels.append((LevelType.SWING_LOW_5M, cand.low, cand.volume))

        # 5. Volume nodes
        if volume_nodes:
            for vn_price, vn_vol in volume_nodes:
                raw_levels.append((LevelType.VOLUME_NODE, vn_price, vn_vol))

        # Evaluate interactions & relevance for each level
        evaluated_levels: List[StructuralLevel] = []
        half_life = max(self.config.relevance_decay_half_life_points, 1.0)
        retest_band = self.config.retest_tolerance_pct
        touch_band = self.config.touch_tolerance_pct

        for l_type, l_price, l_vol in raw_levels:
            dist_pts = current_price - l_price
            dist_abs = abs(dist_pts)
            dist_pct = dist_abs / max(current_price, 1e-6)

            # Analyze historical candle touches and rejections
            touches = 0
            rejections = 0
            broken = False

            for c in candles_1m[-50:]:  # Inspect recent 50 bars
                price_touched = (c.low <= l_price * (1 + touch_band)) and (c.high >= l_price * (1 - touch_band))
                if price_touched:
                    touches += 1
                    # Rejection: candle closed away from level
                    if l_price >= current_price and c.close < c.open and c.upper_wick > c.range * 0.35:
                        rejections += 1
                    elif l_price <= current_price and c.close > c.open and c.lower_wick > c.range * 0.35:
                        rejections += 1

            # Is level broken? (Closed convincingly past it)
            if l_type in (LevelType.PDH, LevelType.ORH, LevelType.SWING_HIGH_5M, LevelType.SESSION_HIGH):
                broken = current_price > l_price * (1 + touch_band)
            elif l_type in (LevelType.PDL, LevelType.ORL, LevelType.SWING_LOW_5M, LevelType.SESSION_LOW):
                broken = current_price < l_price * (1 - touch_band)

            # Is currently retesting?
            is_retest = dist_pct <= retest_band

            # Dynamic relevance score calculation
            # Component 1: Distance proximity (0.0 to 1.0)
            proximity_score = math.exp(-dist_abs / half_life)
            # Component 2: Touch & reaction weight
            reaction_score = min((touches * 0.15) + (rejections * 0.25), 1.0)
            # Component 3: Retest boost
            retest_boost = 0.25 if is_retest else 0.0
            # Component 4: Level intrinsic weight
            macro_bonus = 0.20 if l_type in (LevelType.PDH, LevelType.PDL, LevelType.ORH, LevelType.ORL, LevelType.VWAP) else 0.10

            raw_score = (proximity_score * 0.45) + (reaction_score * 0.25) + retest_boost + macro_bonus
            # Penalty if broken long ago
            if broken and not is_retest:
                raw_score *= 0.70

            relevance = max(0.0, min(1.0, raw_score))

            evaluated_levels.append(
                StructuralLevel(
                    level_type=l_type,
                    price=round(l_price, 2),
                    relevance_score=round(relevance, 4),
                    distance_points=round(dist_pts, 2),
                    distance_pct=round(dist_pct, 6),
                    touch_count=touches,
                    rejection_count=rejections,
                    is_broken=broken,
                    is_retested=is_retest,
                    volume_at_level=round(l_vol, 2),
                )
            )

        # Sort levels by price
        evaluated_levels.sort(key=lambda lvl: lvl.price)

        # Identify nearest support and resistance STRICTLY by price side
        # (support = level price < current price, resistance = level price > current).
        # NOTE: a level below the current price keeps its native level_type — e.g. a
        # broken SWING_HIGH_5M/SESSION_HIGH/PDH/ORH below price is returned as the
        # nearest *support*, and a SWING_LOW_5M above price as *resistance*.
        # Consumers MUST read level_type on the returned StructuralLevel (and the
        # HUD payload exposes it explicitly) and never assume support => LOW-type.
        # Silently relabelling the type would hide breakouts/reclaims.
        supports = [lvl for lvl in evaluated_levels if lvl.price < current_price]
        resistances = [lvl for lvl in evaluated_levels if lvl.price > current_price]

        nearest_supp = max(supports, key=lambda lvl: lvl.price) if supports else None
        nearest_res = min(resistances, key=lambda lvl: lvl.price) if resistances else None

        dist_supp = (current_price - nearest_supp.price) if nearest_supp else None
        dist_res = (nearest_res.price - current_price) if nearest_res else None

        # Truncate to top max_levels_tracked by relevance
        if len(evaluated_levels) > self.config.max_levels_tracked:
            evaluated_levels.sort(key=lambda lvl: lvl.relevance_score, reverse=True)
            evaluated_levels = evaluated_levels[: self.config.max_levels_tracked]
            evaluated_levels.sort(key=lambda lvl: lvl.price)

        elapsed = (time.perf_counter() - start_t) * 1000.0

        return StructuralLevelMapResult(
            levels=evaluated_levels,
            nearest_support=nearest_supp,
            nearest_resistance=nearest_res,
            distance_to_nearest_support=round(dist_supp, 2) if dist_supp is not None else None,
            distance_to_nearest_resistance=round(dist_res, 2) if dist_res is not None else None,
            vwap=vwap,
            computation_time_ms=round(elapsed, 3),
        )
