from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from zoneinfo import ZoneInfo
import structlog

from app.event_engine.models import (
    CanonicalEvent,
    TemporalPhase,
    VerificationStatus,
    LifecycleTransition,
)

logger = structlog.get_logger()
IST = ZoneInfo("Asia/Kolkata")


class EventLifecycleService:
    """Manages Processing Completeness and Temporal Phase Transitions (§9).
    
    Refined architecture: Decouples processing completeness (flags) from
    temporal progression (time to event). All transitions are logged immutably.
    """

    def compute_temporal_phase(
        self,
        event_timestamp: datetime,
        now: Optional[datetime] = None,
    ) -> TemporalPhase:
        """Derive temporal phase dynamically based on current time relative to event.
        
        Rules:
          - > 24 hours before event: SCHEDULED
          - Within 24 hours up to event: APPROACHING
          - Event time to Event time + 2 hours: ACTIVE
          - Event time + 2 hours to 72 hours: POST_EVENT
          - > 72 hours past: ARCHIVED
        """
        current_time = now or datetime.now(timezone.utc)
        # Ensure timezone-aware
        if event_timestamp.tzinfo is None:
            event_timestamp = event_timestamp.replace(tzinfo=timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        diff_seconds = (event_timestamp - current_time).total_seconds()

        if diff_seconds > 86400:  # > 24h away
            return "SCHEDULED"
        elif 0 <= diff_seconds <= 86400:  # Within 24h
            return "APPROACHING"
        elif -7200 <= diff_seconds < 0:  # Within 2h after start
            return "ACTIVE"
        elif -259200 <= diff_seconds < -7200:  # 2h to 3 days after
            return "POST_EVENT"
        else:
            return "ARCHIVED"

    def transition_phase(
        self,
        event: CanonicalEvent,
        target_phase: TemporalPhase,
        reason: str,
        actor: str = "EVENT_ENGINE",
        metadata: Optional[dict[str, Any]] = None,
    ) -> tuple[CanonicalEvent, Optional[LifecycleTransition]]:
        """Transition an event to a new temporal phase with immutable audit log."""
        if event.temporal_phase == target_phase:
            return event, None

        previous_phase = event.temporal_phase
        event.temporal_phase = target_phase
        event.updated_at = datetime.now(timezone.utc)

        transition = LifecycleTransition(
            canonical_event_id=event.canonical_event_id,
            from_phase=previous_phase,
            to_phase=target_phase,
            reason=reason,
            actor=actor,
            event_version=int(event.metadata.get("version", 1)),
            timestamp=datetime.now(timezone.utc),
            metadata=metadata or {},
        )

        logger.info(
            "event_phase_transition",
            canonical_event_id=event.canonical_event_id,
            from_phase=previous_phase,
            to_phase=target_phase,
            reason=reason,
        )
        return event, transition


lifecycle_service = EventLifecycleService()
