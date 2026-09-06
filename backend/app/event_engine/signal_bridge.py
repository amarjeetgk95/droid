from __future__ import annotations

import uuid
import time
from datetime import datetime, timezone
from typing import Optional, Any
from pydantic import BaseModel, Field
import structlog

from app.event_engine.models import CanonicalEvent

logger = structlog.get_logger()


class EventSignalContext(BaseModel):
    event_id: str
    event_type: str
    event_phase: str
    importance_score: float
    market_impact_score: Optional[float] = None
    opportunity_score: float
    affected_instrument: str
    event_context_version: str = "v3.0.0"
    execution_mode: str = "SHADOW_MODE"


class ShadowSignalRecord(BaseModel):
    shadow_signal_id: str = Field(default_factory=lambda: f"SHADOW-{uuid.uuid4().hex[:8].upper()}")
    canonical_event_id: str
    base_signal_id: str
    underlying: str
    strategy: str
    direction: str
    execution_mode: str = "SHADOW_MODE"
    event_importance_score: float
    event_market_impact_score: Optional[float] = None
    event_opportunity_score: float
    suggested_sizing_factor: float = 1.0
    simulated_entry_price: Optional[float] = None
    simulated_exit_price: Optional[float] = None
    simulated_pnl_pct: Optional[float] = None
    shadow_status: str = "TRACKING"  # TRACKING | COMPLETED | INVALIDATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventSignalBridge:
    """Event → Signal Integration Engine (§3, §27).
    
    Guarantees:
      1. Operates strictly in SHADOW_MODE (§3) — zero automatic real capital execution.
      2. Attaches comprehensive event context (§27) to existing SignalInstances.
      3. Records auditable shadow executions for forward-testing validation.
    """

    def __init__(self):
        self._shadow_records: dict[str, ShadowSignalRecord] = {}

    def create_event_context(self, event: CanonicalEvent, underlying: str) -> EventSignalContext:
        """Construct normalized EventContext payload (§27)."""
        importance = event.scores.importance.final_score if event.scores else 80.0
        impact = event.scores.market_impact.final_score if event.scores else None
        opportunity = event.scores.opportunity.final_score if (event.scores and event.scores.opportunity.final_score is not None) else 70.0

        return EventSignalContext(
            event_id=event.canonical_event_id,
            event_type=event.event_type,
            event_phase=event.temporal_phase,
            importance_score=importance,
            market_impact_score=impact,
            opportunity_score=opportunity,
            affected_instrument=underlying,
            event_context_version="v3.0.0",
            execution_mode="SHADOW_MODE",
        )

    def enrich_signal(self, signal: Any, event: CanonicalEvent) -> Any:
        """Attach event context to existing SignalInstance or candidate dict."""
        underlying = str(getattr(signal, "underlying", "BANKNIFTY"))
        ctx = self.create_event_context(event, underlying)

        if hasattr(signal, "confluence_breakdown"):
            signal.confluence_breakdown["event_context"] = ctx.model_dump()
        if hasattr(signal, "rationale") and isinstance(signal.rationale, list):
            signal.rationale.append(f"Event Context: {event.title} ({event.temporal_phase}, Opp: {ctx.opportunity_score}) [SHADOW_MODE]")

        return signal

    def record_shadow_execution(
        self,
        signal_id: str,
        event: CanonicalEvent,
        underlying: str,
        strategy: str,
        direction: str,
        simulated_entry_price: float,
    ) -> ShadowSignalRecord:
        """Record shadow execution for paper forward-testing without touching real capital."""
        ctx = self.create_event_context(event, underlying)
        record = ShadowSignalRecord(
            canonical_event_id=event.canonical_event_id,
            base_signal_id=signal_id,
            underlying=underlying,
            strategy=strategy,
            direction=direction,
            execution_mode="SHADOW_MODE",
            event_importance_score=ctx.importance_score,
            event_market_impact_score=ctx.market_impact_score,
            event_opportunity_score=ctx.opportunity_score,
            suggested_sizing_factor=1.0,
            simulated_entry_price=simulated_entry_price,
            shadow_status="TRACKING",
        )

        self._shadow_records[record.shadow_signal_id] = record
        logger.info(
            "event_shadow_execution_recorded",
            shadow_id=record.shadow_signal_id,
            event_id=event.canonical_event_id,
            signal_id=signal_id,
            underlying=underlying,
        )
        return record

    def get_shadow_records(self, limit: int = 50) -> list[ShadowSignalRecord]:
        return list(self._shadow_records.values())[:limit]


event_signal_bridge = EventSignalBridge()
