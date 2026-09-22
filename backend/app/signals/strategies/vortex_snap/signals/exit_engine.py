"""
Dynamic Exit Engine & Invalidation Logic (§20, §21, §22, §23).

Calculates volatility-scaled targets (Target 1 = 0.8x, Target 2 = 1.3x),
structural stop-losses, time-decay horizons, and dynamic pressure-collapse exits.
"""
from __future__ import annotations

import math
from typing import Literal, Optional, Tuple
from pydantic import BaseModel, Field

from app.signals.strategies.vortex_snap.types import (
    Candle,
    StructuralLevel,
    VortexFeatureSnapshot,
)


class ExitTargets(BaseModel):
    """Calculated trade parameters for execution."""
    entry_price: float
    stop_price: float
    target_1: float
    target_2: float
    expected_move: float
    expected_holding_minutes: float
    risk_points: float
    reward_risk_ratio: float


class DynamicExitEngine:
    """Computes dynamic, volatility-scaled targets and structural stops."""

    def calculate_trade_envelope(
        self,
        direction: int,  # +1 for LONG, -1 for SHORT
        entry_price: float,
        snapshot: VortexFeatureSnapshot,
        interacted_level: Optional[StructuralLevel] = None,
        min_risk_points: Optional[float] = None,
        max_risk_points: Optional[float] = None,
    ) -> ExitTargets:
        """Calculate entry, stop, and dual targets for a validated candidate.

        Args:
            direction: +1 (LONG) or -1 (SHORT).
            entry_price: Current spot price.
            snapshot: Microstructure feature snapshot at entry.
            interacted_level: Structural pivot/level broken or defended.
            min_risk_points: Optional instrument minimum stop envelope.
            max_risk_points: Optional instrument maximum stop envelope.

        Returns:
            ExitTargets model.
        """
        inst = (snapshot.instrument or "").upper()
        if "SENSEX" in inst:
            default_min_risk = 35.0
            default_max_risk = 70.0
            default_atr = max(snapshot.structural_levels.distance_to_nearest_resistance or 45.0, 35.0)
            t1_ceil = 100.0
            t2_ceil = 160.0
        elif "BANK" in inst:
            default_min_risk = 25.0
            default_max_risk = 50.0
            default_atr = max(snapshot.structural_levels.distance_to_nearest_resistance or 30.0, 25.0)
            t1_ceil = 75.0
            t2_ceil = 120.0
        else:
            default_min_risk = 8.0
            default_max_risk = 18.0
            default_atr = max(snapshot.structural_levels.distance_to_nearest_resistance or 15.0, 10.0)
            t1_ceil = 30.0
            t2_ceil = 45.0

        actual_min_risk = min_risk_points if min_risk_points is not None else default_min_risk
        actual_max_risk = max_risk_points if max_risk_points is not None else default_max_risk
        atr_proxy = default_atr

        # 1. Expected Move Calculation (§21)
        # Driven by ATR, snap energy, and proximity of next structural target
        energy_boost = 1.0 + (0.5 * snapshot.snap_energy.snap_energy)
        raw_expected_move = 1.8 * atr_proxy * energy_boost

        if direction > 0:
            # Check distance to next resistance
            if snapshot.structural_levels.distance_to_nearest_resistance:
                next_res_dist = snapshot.structural_levels.distance_to_nearest_resistance
                expected_move = min(raw_expected_move, max(next_res_dist * 0.90, actual_min_risk * 1.5))
            else:
                expected_move = raw_expected_move
        else:
            # Check distance to next support
            if snapshot.structural_levels.distance_to_nearest_support:
                next_supp_dist = snapshot.structural_levels.distance_to_nearest_support
                expected_move = min(raw_expected_move, max(next_supp_dist * 0.90, actual_min_risk * 1.5))
            else:
                expected_move = raw_expected_move

        expected_move = min(expected_move, t2_ceil)

        # 2. Structural Stop Placement (§21)
        # Use broken level if available, with volatility buffer
        vol_buffer = max(0.20 * atr_proxy, 3.0)

        if direction > 0:
            if interacted_level and interacted_level.price < entry_price:
                stop = interacted_level.price - vol_buffer
            else:
                stop = entry_price - (0.85 * atr_proxy)
            risk = entry_price - stop
        else:
            if interacted_level and interacted_level.price > entry_price:
                stop = interacted_level.price + vol_buffer
            else:
                stop = entry_price + (0.85 * atr_proxy)
            risk = stop - entry_price

        # Bound risk within instrument envelope
        risk = max(actual_min_risk, min(risk, actual_max_risk))
        if direction > 0:
            stop = entry_price - risk
            t1 = entry_price + min(0.80 * expected_move, t1_ceil)
            t2 = entry_price + expected_move
        else:
            stop = entry_price + risk
            t1 = entry_price - min(0.80 * expected_move, t1_ceil)
            t2 = entry_price - expected_move

        rr = round(abs(t1 - entry_price) / max(risk, 1e-6), 2)

        # 3. Holding Horizon (§20)
        # Scalps typically hold 2 to 5 minutes based on volatility
        expected_hold_mins = round(max(2.0, min(5.5, 3.0 * (expected_move / max(atr_proxy, 1.0)))), 1)

        return ExitTargets(
            entry_price=round(entry_price, 2),
            stop_price=round(stop, 2),
            target_1=round(t1, 2),
            target_2=round(t2, 2),
            expected_move=round(expected_move, 2),
            expected_holding_minutes=expected_hold_mins,
            risk_points=round(risk, 2),
            reward_risk_ratio=rr,
        )

    def check_dynamic_exits(
        self,
        direction: int,
        entry_price: float,
        current_candle: Candle,
        snapshot: VortexFeatureSnapshot,
        signal_age_minutes: float,
        max_holding_minutes: float = 6.0,
    ) -> Tuple[bool, Optional[str]]:
        """Evaluate if an active trade should be closed early (§20, §22, §23).

        Returns:
            (should_exit, reason_code_or_description)
        """
        # 1. Time Decay Exit (§20): Scalp trade went stale without hitting target
        if signal_age_minutes >= max_holding_minutes:
            return True, "TIME_DECAY_EXHAUSTION"

        # 2. Pressure Collapse Exit (§22)
        # Long trade: price is not progressing or stalling, and buy pressure completely collapsed
        if direction > 0:
            if snapshot.pressure.pressure_score <= -0.40 and current_candle.close < entry_price:
                return True, "PRESSURE_COLLAPSE_BEARISH"
        # Short trade: sell pressure collapsed and buyers entered aggressively
        elif direction < 0:
            if snapshot.pressure.pressure_score >= 0.40 and current_candle.close > entry_price:
                return True, "PRESSURE_COLLAPSE_BULLISH"

        return False, None
