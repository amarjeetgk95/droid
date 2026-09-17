"""
Institutional Breakout / Breakdown Strategy (P1: retired duplicate).

Single-logic contract: BREAKOUT is a pointer to the shared
VOLATILITY_BREAKOUT instance (see strategies/__init__.py). This module keeps
the legacy BreakoutStrategy import path for back-compat but delegates all
detection to VolatilityBreakoutStrategy so there is exactly one breakout
logic. Breakout economics preserved: T1 = 1.5R, T2 = 3.0R advisory
(risk_engine overwrites).

P1 gates (inherited): squeeze required, CLOSE beyond level (not intrabar
spot touch), measured volume >= 1.5x fail-closed, pressure measured
fail-closed, S/R missing fail-closed.
"""
from __future__ import annotations

from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.strategies.volatility_breakout import VolatilityBreakoutStrategy


class BreakoutStrategy(Strategy):
    """Legacy alias — delegates to VolatilityBreakoutStrategy (single logic)."""

    name = "BREAKOUT"  # type: ignore[assignment]

    _delegate = VolatilityBreakoutStrategy()

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        cand = self._delegate.detect(ctx)
        if cand is None:
            return None
        # Preserve BREAKOUT identity for callers that instantiate this class
        # directly, while keeping identical geometry/scoring logic.
        try:
            object.__setattr__(cand, "strategy", self.name)  # pydantic v2 path
        except Exception:
            try:
                cand.strategy = self.name  # type: ignore
            except Exception:
                pass
        # BREAKOUT advisory multiples are T1=1.5R / T2=3.0R; the shared
        # VOL logic emits 1.5/2.5. Keep BREAKOUT's 3.0R T2 by extending T2
        # proportionally from the same risk base (risk_engine overwrites).
        try:
            from decimal import Decimal
            from app.signals.contract_resolver import normalize_price

            tick = Decimal("0.05")
            risk_pts = cand.risk_points
            if risk_pts and risk_pts > Decimal("0"):
                if cand.direction == "LONG_CALL":
                    t2 = normalize_price(cand.trigger + (risk_pts * Decimal("3.0")), tick)
                else:
                    t2 = normalize_price(cand.trigger - (risk_pts * Decimal("3.0")), tick)
                try:
                    object.__setattr__(cand, "target_2", t2)
                    object.__setattr__(cand, "risk_reward_t2", 3.0)
                except Exception:
                    cand.target_2 = t2  # type: ignore
                    cand.risk_reward_t2 = 3.0  # type: ignore
        except Exception:
            pass
        return cand
