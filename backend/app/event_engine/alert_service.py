from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Literal
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

AlertType = Literal[
    "EVENT_DISCOVERED",
    "EVENT_VERIFIED",
    "EVENT_APPROACHING",
    "SETUP_DEVELOPING",
    "OPPORTUNITY_CONFIRMED",
    "NO_TRADE",
    "EVENT_ACTIVE",
    "EVENT_COMPLETED",
    "OUTCOME_AVAILABLE",
]


class EventAlert(BaseModel):
    alert_id: str = Field(default_factory=lambda: f"ALT-{uuid.uuid4().hex[:8].upper()}")
    canonical_event_id: str
    alert_type: AlertType
    severity: Literal["INFO", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    title: str
    message: str
    dedup_signature: str
    status: Literal["PENDING_REVIEW", "ACKNOWLEDGED", "SUPPRESSED"] = "PENDING_REVIEW"
    cooldown_until: datetime
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventAlertService:
    """Internal Alert & Review Queue with Strict Cooldown Deduplication (§29).
    
    Generates alerts strictly upon state transitions or critical changes.
    Prevents alert fatigue/spam via configurable cooldown windows.
    """

    def __init__(self, default_cooldown_minutes: int = 15):
        self._alerts: dict[str, EventAlert] = {}
        self._signatures: dict[str, datetime] = {}
        self._default_cooldown = timedelta(minutes=default_cooldown_minutes)

    def compute_signature(self, canonical_event_id: str, alert_type: str, state_fingerprint: str = "") -> str:
        raw = f"{canonical_event_id}|{alert_type}|{state_fingerprint}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def emit_alert(
        self,
        canonical_event_id: str,
        alert_type: AlertType,
        title: str,
        message: str,
        severity: Literal["INFO", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM",
        state_fingerprint: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[EventAlert]:
        """Emit alert only if outside the active deduplication cooldown window (§29)."""
        now = datetime.now(timezone.utc)
        sig = self.compute_signature(canonical_event_id, alert_type, state_fingerprint)

        # Cooldown check
        if sig in self._signatures:
            expires_at = self._signatures[sig]
            if now < expires_at:
                logger.debug(
                    "event_alert_suppressed_cooldown",
                    canonical_event_id=canonical_event_id,
                    alert_type=alert_type,
                    cooldown_remaining_sec=int((expires_at - now).total_seconds()),
                )
                return None

        # Fresh alert
        cooldown_until = now + self._default_cooldown
        self._signatures[sig] = cooldown_until

        alert = EventAlert(
            canonical_event_id=canonical_event_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            dedup_signature=sig,
            status="PENDING_REVIEW",
            cooldown_until=cooldown_until,
            metadata=metadata or {},
            created_at=now,
        )

        self._alerts[alert.alert_id] = alert
        logger.info(
            "event_alert_emitted",
            alert_id=alert.alert_id,
            alert_type=alert_type,
            event_id=canonical_event_id,
            severity=severity,
        )
        return alert

    def acknowledge_alert(self, alert_id: str, user_name: str = "OPS_DESK") -> Optional[EventAlert]:
        alert = self._alerts.get(alert_id)
        if not alert:
            return None
        alert.status = "ACKNOWLEDGED"
        alert.acknowledged_by = user_name
        alert.acknowledged_at = datetime.now(timezone.utc)
        return alert

    def get_pending_alerts(self, limit: int = 50) -> list[EventAlert]:
        pending = [a for a in self._alerts.values() if a.status == "PENDING_REVIEW"]
        return sorted(pending, key=lambda a: a.created_at, reverse=True)[:limit]

    def get_all_alerts(self, limit: int = 100) -> list[EventAlert]:
        return sorted(list(self._alerts.values()), key=lambda a: a.created_at, reverse=True)[:limit]


event_alert_service = EventAlertService()
