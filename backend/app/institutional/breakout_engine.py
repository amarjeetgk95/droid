"""
Breakout / Breakdown Strategy Engine — §§30,31,32,33,34
Supports NIFTY, BANKNIFTY, SENSEX, BTCUSD
States: BULLISH BREAKOUT, BEARISH BREAKDOWN, POSSIBLE, CONFIRMED, FAILED, INVALIDATED etc.
ShortHorizon (10-min) vs Intraday Continuation (<2h) separation.
Simple price crossing level is not enough — evaluate structure, candle close, volume, momentum etc.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Any
from enum import Enum

from app.algo.money import D
from app.institutional.market_intelligence import MarketContext, market_intelligence_engine

Direction = Literal["BULLISH", "BEARISH"]
BreakoutStatus = Literal["POSSIBLE", "WATCH", "CONFIRMED", "REJECTED", "INVALIDATED", "EXPIRED", "FAILED"]
HorizonStatus = Literal["POSSIBLE", "WATCH", "CONFIRMED", "REJECTED", "INVALIDATED", "EXPIRED"]


@dataclass
class BreakoutSignal:
    instrument_id: str
    direction: Direction
    status: BreakoutStatus
    confidence: int  # 0-100
    breakout_level: Decimal | None = None
    false_breakout_risk: int = 0
    supporting: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class ShortHorizonOutput:
    strategy: str = "10_MINUTE_TRADE"
    instrument: str = ""
    direction: Direction | Literal["NEUTRAL"] = "NEUTRAL"
    status: HorizonStatus = "REJECTED"
    confidence: int = 0
    horizon_minutes: int = 10
    entry_zone: list[str] = field(default_factory=list)
    stop_loss: str = "0"
    target_zone: list[str] = field(default_factory=list)
    false_breakout_risk: int = 0
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "instrument": self.instrument,
            "direction": self.direction,
            "status": self.status,
            "confidence": self.confidence,
            "horizon_minutes": self.horizon_minutes,
            "entry_zone": self.entry_zone,
            "stop_loss": self.stop_loss,
            "target_zone": self.target_zone,
            "false_breakout_risk": self.false_breakout_risk,
            "reason": self.reason,
        }


@dataclass
class ContinuationOutput:
    strategy: str = "INTRADAY_CONTINUATION"
    instrument: str = ""
    direction: Direction | Literal["NEUTRAL"] = "NEUTRAL"
    status: HorizonStatus = "REJECTED"
    confidence: int = 0
    max_holding_minutes: int = 119
    reason: str = ""
    invalidation: str = ""

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "instrument": self.instrument,
            "direction": self.direction,
            "status": self.status,
            "confidence": self.confidence,
            "max_holding_minutes": self.max_holding_minutes,
            "reason": self.reason,
            "invalidation": self.invalidation,
        }


class BreakoutStrategyEngine:
    """
    Core breakout/breakdown detection — not just price cross.
    Evaluates: price structure, candle close, volume, momentum, volatility, VWAP,
    futures, OI, options where applicable, liquidity, market regime, false-breakout risk,
    cross-market confirmation where valid.
    Uses MarketContext from MarketIntelligenceEngine (§25).
    """

    def evaluate(
        self,
        ctx: MarketContext,
        breakout_level: Decimal | None = None,
        current_price: Decimal | None = None,
        close_confirmed: bool = False,
        volume_expansion: bool = False,
        momentum_accelerating: bool = False,
        cross_market_valid: bool = True,
    ) -> BreakoutSignal:
        scores = ctx.scores
        breakout_pressure = scores.get("breakout_pressure", 50)
        breakdown_pressure = scores.get("breakdown_pressure", 50)
        false_risk = scores.get("false_breakout_risk", 30)

        # Determine direction bias
        bullish = scores.get("bullish_score", 50)
        bearish = scores.get("bearish_score", 50)

        supporting = [e.signal for e in ctx.supporting_evidence]
        conflicts = [e.signal for e in ctx.conflicting_evidence]

        # Cross-market must be synchronized; else invalidate cross-market part
        if ctx.synchronization_status == "CROSS_MARKET_DATA_NOT_SYNCHRONIZED" and not cross_market_valid:
            conflicts.append("CROSS_MARKET_DATA_NOT_SYNCHRONIZED")

        # Core logic — multi-factor
        # BULLISH BREAKOUT conditions
        is_bullish_setup = (
            bullish > 65
            and breakout_pressure > 70
            and ctx.price_action.get("trend") in ("BULLISH", "RANGING")
            and ctx.technical.get("vwap") in ("ABOVE", "AT")
            and volume_expansion
            and (close_confirmed or breakout_pressure > 80)
            and false_risk < 60
            and current_price is not None and breakout_level is not None and current_price > breakout_level
        )
        is_bearish_setup = (
            bearish > 65
            and breakdown_pressure > 70
            and ctx.price_action.get("trend") in ("BEARISH", "RANGING")
            and ctx.technical.get("vwap") in ("BELOW", "AT")
            and volume_expansion
            and (close_confirmed or breakdown_pressure > 80)
            and false_risk < 60
            and current_price is not None and breakout_level is not None and current_price < breakout_level
        )

        if is_bullish_setup:
            conf = min(95, int(60 + (bullish-65)*0.6 + (breakout_pressure-70)*0.5 - false_risk*0.2 + (10 if close_confirmed else 0)))
            if false_risk > 45: conf -= 15
            status: BreakoutStatus = "CONFIRMED" if close_confirmed and volume_expansion and false_risk < 40 else "POSSIBLE"
            if false_risk > 50: status = "WATCH"
            return BreakoutSignal(instrument_id=ctx.instrument, direction="BULLISH", status=status, confidence=max(0, conf), breakout_level=breakout_level, false_breakout_risk=false_risk, supporting=supporting, conflicts=conflicts)
        if is_bearish_setup:
            conf = min(95, int(60 + (bearish-65)*0.6 + (breakdown_pressure-70)*0.5 - false_risk*0.2 + (10 if close_confirmed else 0)))
            if false_risk > 45: conf -= 15
            status = "CONFIRMED" if close_confirmed and volume_expansion and false_risk < 40 else "POSSIBLE"
            if false_risk > 50: status = "WATCH"
            return BreakoutSignal(instrument_id=ctx.instrument, direction="BEARISH", status=status, confidence=max(0, conf), breakout_level=breakout_level, false_breakout_risk=false_risk, supporting=supporting, conflicts=conflicts)

        # No breakout
        # Determine if WATCH (nearby)
        if bullish > 58 or bearish > 58:
            # Possible but not confirmed — WATCH
            dir_guess: Direction = "BULLISH" if bullish >= bearish else "BEARISH"
            return BreakoutSignal(instrument_id=ctx.instrument, direction=dir_guess, status="WATCH", confidence=int(max(bullish, bearish)*0.6), breakout_level=breakout_level, false_breakout_risk=false_risk, supporting=supporting, conflicts=conflicts, reason="watch — conditions partially met")
        # Rejected
        return BreakoutSignal(instrument_id=ctx.instrument, direction="BULLISH", status="REJECTED", confidence=0, breakout_level=breakout_level, false_breakout_risk=false_risk, supporting=supporting, conflicts=conflicts, reason="no breakout — multi-factor not satisfied")


class ShortHorizonBreakoutStrategy:
    """
    §31 — 10-minute short-horizon strategy (high-quality directional trade expected ~10 min).
    Not guarantee position must remain 10 min; has explicit time-based exit.
    Prioritize 1m/3m/5m + derivatives/microstructure.
    """
    horizon_minutes = 10

    def __init__(self, breakout_engine: BreakoutStrategyEngine | None = None):
        self._engine = breakout_engine or BreakoutStrategyEngine()

    def evaluate(
        self,
        ctx: MarketContext,
        breakout_level: Decimal | None = None,
        current_price: Decimal | None = None,
        atr: Decimal | None = None,
        # Microstructure inputs for short horizon
        momentum_accel: bool = False,
        volume_expansion: bool = False,
        short_term_oi_supportive: bool | None = None,
        futures_supportive: bool | None = None,
        options_supportive: bool | None = None,
        liquidity_ok: bool = True,
        nearest_opposing_level_distance_atr: float | None = None,
        close_confirmed: bool = False,
    ) -> ShortHorizonOutput:
        # Use breakout engine first
        sig = self._engine.evaluate(ctx, breakout_level=breakout_level, current_price=current_price, close_confirmed=close_confirmed, volume_expansion=volume_expansion, momentum_accelerating=momentum_accel)
        # Short-horizon additional filters
        # Nearby opposing level too close → downgrade
        if nearest_opposing_level_distance_atr is not None and nearest_opposing_level_distance_atr < 0.8:
            # resistance 10 points away for NIFTY with ATR ~ 80 is ~0.125 ATR → too close
            if sig.status in ("POSSIBLE", "CONFIRMED"):
                sig.status = "WATCH"
                sig.conflicts.append("opposing level too close")
                sig.false_breakout_risk = min(100, sig.false_breakout_risk + 15)
        if not liquidity_ok:
            return ShortHorizonOutput(instrument=ctx.instrument, direction=sig.direction, status="REJECTED", confidence=0, false_breakout_risk=90, reason="illiquid")
        # Momentum acceleration required for short horizon quality
        if sig.status != "REJECTED" and not momentum_accel and sig.confidence < 75:
            sig.status = "WATCH"

        # False-breakout probability high → REJECT
        if sig.false_breakout_risk > 70:
            return ShortHorizonOutput(instrument=ctx.instrument, direction=sig.direction, status="REJECTED", confidence=0, false_breakout_risk=sig.false_breakout_risk, reason=f"false breakout risk {sig.false_breakout_risk}")

        # Map breakout status -> horizon status
        status_map: dict[BreakoutStatus, HorizonStatus] = {
            "POSSIBLE": "POSSIBLE", "WATCH": "WATCH", "CONFIRMED": "CONFIRMED",
            "REJECTED": "REJECTED", "INVALIDATED": "INVALIDATED", "EXPIRED": "EXPIRED", "FAILED": "REJECTED",
        }
        horizon_status = status_map.get(sig.status, "REJECTED")

        # Build zones from price/ATR
        entry_zone: list[str] = []
        target_zone: list[str] = []
        stop_loss = "0"
        if current_price is not None and atr is not None and atr > D(0):
            if sig.direction == "BULLISH":
                entry_low = current_price
                entry_high = current_price + atr * D("0.3")
                entry_zone = [format(entry_low, 'f'), format(entry_high, 'f')]
                stop_loss = format(current_price - atr * D("0.7"), 'f')
                target_zone = [format(current_price + atr * D("0.8"), 'f'), format(current_price + atr * D("1.5"), 'f')]
            else:
                entry_low = current_price - atr * D("0.3")
                entry_high = current_price
                entry_zone = [format(entry_low, 'f'), format(entry_high, 'f')]
                stop_loss = format(current_price + atr * D("0.7"), 'f')
                target_zone = [format(current_price - atr * D("1.5"), 'f'), format(current_price - atr * D("0.8"), 'f')]

        return ShortHorizonOutput(
            instrument=ctx.instrument,
            direction=sig.direction if sig.status != "REJECTED" else "NEUTRAL",
            status=horizon_status,
            confidence=sig.confidence if horizon_status != "REJECTED" else 0,
            entry_zone=entry_zone, stop_loss=stop_loss, target_zone=target_zone,
            false_breakout_risk=sig.false_breakout_risk,
            reason=sig.reason or f"short-horizon {horizon_status.lower()}",
        )


class IntradayContinuationStrategy:
    """
    §33 — Intraday long/continuation: initial breakout may develop into larger intraday move.
    Maximum holding <2 hours → max_holding_minutes = 119 (§33 strict)
    Use 5m/15m/30m + asset-specific context. Higher-high / higher-low, persistence, regime etc.
    """
    max_holding_minutes: int = 119

    def __init__(self, breakout_engine: BreakoutStrategyEngine | None = None):
        self._engine = breakout_engine or BreakoutStrategyEngine()

    def evaluate(
        self,
        ctx: MarketContext,
        breakout_level: Decimal | None = None,
        current_price: Decimal | None = None,
        atr: Decimal | None = None,
        higher_high_higher_low: bool = False,
        volume_persistence: bool = False,
        momentum_persistence: bool = False,
        retest_holding: bool = False,
        cross_market_confirmation: bool | None = None,
        close_confirmed: bool = False,
        volume_expansion: bool = False,
    ) -> ContinuationOutput:
        # Continuation requires structure persistence, not just immediate breakout pressure
        # Evaluate higher-timeframe alignment (5m/15m/30m)
        mtf = ctx.price_action  # structure/trend already aggregated but we need persistence signals
        # Use MarketContext scores but require additional persistence evidence
        sig = self._engine.evaluate(ctx, breakout_level=breakout_level, current_price=current_price, close_confirmed=close_confirmed, volume_expansion=volume_expansion)

        # Continuation-specific downgrades
        if not higher_high_higher_low and sig.status != "REJECTED":
            sig.status = "WATCH"
            sig.conflicts.append("higher-high/higher-low not confirmed")
        if not volume_persistence and sig.status == "CONFIRMED":
            sig.status = "WATCH"
            sig.conflicts.append("volume persistence lacking")
        if cross_market_confirmation is False:
            sig.status = "WATCH"
            sig.conflicts.append("cross-market not confirmed")

        if sig.false_breakout_risk > 65:
            return ContinuationOutput(instrument=ctx.instrument, direction=sig.direction, status="REJECTED", confidence=0, reason="continuation false-breakout risk high", max_holding_minutes=self.max_holding_minutes)

        # Map
        status_map: dict[BreakoutStatus, HorizonStatus] = {
            "POSSIBLE": "POSSIBLE", "WATCH": "WATCH", "CONFIRMED": "CONFIRMED",
            "REJECTED": "REJECTED", "INVALIDATED": "INVALIDATED", "EXPIRED": "EXPIRED", "FAILED": "REJECTED",
        }
        horizon_status = status_map.get(sig.status, "REJECTED")
        # Persistence boost confidence
        conf = sig.confidence
        if horizon_status == "CONFIRMED" and momentum_persistence and volume_persistence:
            conf = min(95, conf + 5)
        if retest_holding and horizon_status != "REJECTED":
            conf = min(95, conf + 7)

        invalidation = "break below breakout level or VWAP cross with volume divergence"
        if sig.direction == "BEARISH":
            invalidation = "break above breakdown level or VWAP cross with volume divergence"

        return ContinuationOutput(
            instrument=ctx.instrument,
            direction=sig.direction if horizon_status != "REJECTED" else "NEUTRAL",
            status=horizon_status,
            confidence=conf if horizon_status != "REJECTED" else 0,
            max_holding_minutes=self.max_holding_minutes,
            reason=sig.reason or f"continuation {horizon_status.lower()}",
            invalidation=invalidation,
        )


# Singletons
breakout_engine = BreakoutStrategyEngine()
short_horizon_strategy = ShortHorizonBreakoutStrategy(breakout_engine)
continuation_strategy = IntradayContinuationStrategy(breakout_engine)
