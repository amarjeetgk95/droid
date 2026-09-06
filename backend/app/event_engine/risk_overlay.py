from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Literal, Optional
from pydantic import BaseModel, Field
import structlog

from app.event_engine.models import CanonicalEvent

logger = structlog.get_logger()

ProximityState = Literal["NORMAL", "APPROACHING_WINDOW", "BLACKOUT_WINDOW", "REACTION_WINDOW"]


class EventRiskParameters(BaseModel):
    underlying: str
    proximity_state: ProximityState = "NORMAL"
    can_enter: bool = True
    sizing_multiplier: float = 1.0
    max_loss_dampener: float = 1.0
    prohibit_naked_options: bool = False
    rejection_reason: Optional[str] = None
    triggering_event_id: Optional[str] = None
    triggering_event_title: Optional[str] = None
    minutes_to_event: Optional[float] = None
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventRiskOverlayService:
    """Institutional Event-Aware Risk Overlay Engine (§28).
    
    Guarantees:
      1. Sizing and risk can ONLY be reduced or rejected, never expanded beyond base ceilings.
      2. Enforces strict blackout windows (T-5m to T+5m) around High/Critical importance events.
      3. Dampens position sizing during high uncertainty approach windows (T-30m to T-5m).
      4. Disallows unhedged short options when post-event IV crush risk is elevated.
    """

    def __init__(
        self,
        blackout_pre_minutes: float = 5.0,
        blackout_post_minutes: float = 5.0,
        approaching_window_minutes: float = 30.0,
        reaction_window_minutes: float = 15.0,
        high_importance_threshold: float = 70.0,
    ):
        self.blackout_pre_minutes = blackout_pre_minutes
        self.blackout_post_minutes = blackout_post_minutes
        self.approaching_window_minutes = approaching_window_minutes
        self.reaction_window_minutes = reaction_window_minutes
        self.high_importance_threshold = high_importance_threshold

    def evaluate_overlay(
        self,
        underlying: str,
        events: list[CanonicalEvent],
        now: Optional[datetime] = None,
    ) -> EventRiskParameters:
        """Evaluate proximity and risk envelope adjustments for a given instrument."""
        eval_time = now or datetime.now(timezone.utc)
        clean_symbol = underlying.upper().replace(" ", "")

        # Scan for high importance events affecting this underlying
        relevant_events: list[tuple[CanonicalEvent, float]] = []

        for event in events:
            # Check importance
            importance_score = event.scores.importance.final_score if event.scores else 75.0
            if importance_score < self.high_importance_threshold:
                continue

            # Check if event affects this symbol or sector
            affects_symbol = False
            for m in event.impact_mappings:
                m_target = m.target_symbol.upper().replace(" ", "")
                if m_target == clean_symbol or clean_symbol in m_target:
                    affects_symbol = True
                    break
            
            # Default index mapping for macro/banking
            if not affects_symbol:
                if event.sector == "BANKING" and ("BANKNIFTY" in clean_symbol or clean_symbol == "BANKNIFTY"):
                    affects_symbol = True
                elif event.event_type in ("CENTRAL_BANK", "MACRO") and clean_symbol in ("NIFTY", "BANKNIFTY"):
                    affects_symbol = True

            if not affects_symbol:
                continue

            event_dt = event.event_timestamp
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=timezone.utc)

            # Compute difference in minutes (positive if in future, negative if in past)
            diff_min = (event_dt - eval_time).total_seconds() / 60.0
            relevant_events.append((event, diff_min))

        if not relevant_events:
            return EventRiskParameters(underlying=underlying, proximity_state="NORMAL")

        # Sort by proximity to eval_time
        relevant_events.sort(key=lambda x: abs(x[1]))
        closest_event, minutes_to_event = relevant_events[0]

        # 1. Blackout Window: [-post, +pre] (e.g. -5m to +5m)
        if -self.blackout_post_minutes <= minutes_to_event <= self.blackout_pre_minutes:
            return EventRiskParameters(
                underlying=underlying,
                proximity_state="BLACKOUT_WINDOW",
                can_enter=False,
                sizing_multiplier=0.0,
                max_loss_dampener=0.0,
                prohibit_naked_options=True,
                rejection_reason=f"EVENT_BLACKOUT_ACTIVE: In blackout window ({minutes_to_event:+.1f}m) of '{closest_event.title}'",
                triggering_event_id=closest_event.canonical_event_id,
                triggering_event_title=closest_event.title,
                minutes_to_event=round(minutes_to_event, 1),
            )

        # 2. Approaching Window: (pre, approaching] (e.g. +5m to +30m)
        if self.blackout_pre_minutes < minutes_to_event <= self.approaching_window_minutes:
            return EventRiskParameters(
                underlying=underlying,
                proximity_state="APPROACHING_WINDOW",
                can_enter=True,
                sizing_multiplier=0.5,
                max_loss_dampener=0.5,
                prohibit_naked_options=True,
                rejection_reason=None,
                triggering_event_id=closest_event.canonical_event_id,
                triggering_event_title=closest_event.title,
                minutes_to_event=round(minutes_to_event, 1),
            )

        # 3. Reaction Window: [-reaction, -post) (e.g. -15m to -5m)
        if -self.reaction_window_minutes <= minutes_to_event < -self.blackout_post_minutes:
            return EventRiskParameters(
                underlying=underlying,
                proximity_state="REACTION_WINDOW",
                can_enter=True,
                sizing_multiplier=0.75,
                max_loss_dampener=0.75,
                prohibit_naked_options=True,
                rejection_reason=None,
                triggering_event_id=closest_event.canonical_event_id,
                triggering_event_title=closest_event.title,
                minutes_to_event=round(minutes_to_event, 1),
            )

        return EventRiskParameters(
            underlying=underlying,
            proximity_state="NORMAL",
            can_enter=True,
            sizing_multiplier=1.0,
            minutes_to_event=round(minutes_to_event, 1),
            triggering_event_id=closest_event.canonical_event_id,
        )


event_risk_overlay_service = EventRiskOverlayService()
