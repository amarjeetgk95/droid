"""
Data Health Engine — §5, §6, §59-61, §82

Labeled source: PRIMARY / FALLBACK / STALE
Staleness 2-5s, heartbeat 10s, timeout 30s
"""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Literal
import structlog

logger = structlog.get_logger()

DataHealthState = Literal["HEALTHY", "DEGRADED", "STALE"]
DataSourceLabel = Literal["PRIMARY", "FALLBACK", "STALE"]


@dataclass
class DataHealthSnapshot:
    state: DataHealthState = "HEALTHY"
    source_label: DataSourceLabel = "PRIMARY"
    last_tick_at: datetime | None = None
    age_seconds: float | None = None
    is_stale: bool = False
    reason: str = ""


class DataHealthMonitor:
    """
    Per-account data health.
    Fail-closed: STALE → BLOCK_NEW_ENTRIES (§82)
    """

    # Configurable — spec defaults §59
    HEARTBEAT_INTERVAL_S: float = 10.0
    CONNECTION_TIMEOUT_S: float = 30.0
    STALENESS_THRESHOLD_S: float = 5.0
    DEGRADED_THRESHOLD_S: float = 2.0

    def __init__(self):
        self._last_tick: datetime | None = None
        self._last_heartbeat: datetime | None = None
        self._source_label: DataSourceLabel = "PRIMARY"
        self._connected: bool = True
        self._clock_health: str = "HEALTHY"  # from ClockAuthority
        self._fallback_active: bool = False

    def tick(self, timestamp: datetime, source: DataSourceLabel = "PRIMARY") -> None:
        self._last_tick = timestamp
        self._source_label = source
        self._last_heartbeat = datetime.now(timezone.utc)

    def heartbeat(self) -> None:
        self._last_heartbeat = datetime.now(timezone.utc)

    def set_connection(self, connected: bool, source: DataSourceLabel | None = None) -> None:
        self._connected = connected
        if source:
            self._source_label = source
            self._fallback_active = source == "FALLBACK"

    def set_clock_health(self, health: str) -> None:
        self._clock_health = health

    def set_fallback(self, active: bool) -> None:
        self._fallback_active = active
        self._source_label = "FALLBACK" if active else "PRIMARY"

    def snapshot(self) -> DataHealthSnapshot:
        now = datetime.now(timezone.utc)
        age: float | None = None
        if self._last_tick:
            age = (now - self._last_tick).total_seconds()

        state: DataHealthState = "HEALTHY"
        reason = ""
        is_stale = False

        # Clock drift dominates
        if self._clock_health == "STALE":
            state = "STALE"
            reason = "CLOCK_DRIFT_CRITICAL"
            is_stale = True
        elif self._clock_health == "DEGRADED":
            state = "DEGRADED"
            reason = "CLOCK_DRIFT_DEGRADED"

        # Connection timeout
        if not self._connected:
            state = "STALE"
            reason = "DISCONNECTED"
            is_stale = True

        # Age-based staleness
        if age is not None:
            if age > self.STALENESS_THRESHOLD_S:
                state = "STALE"
                reason = f"DATA_STALE_{age:.1f}s"
                is_stale = True
            elif age > self.DEGRADED_THRESHOLD_S and state == "HEALTHY":
                state = "DEGRADED"
                reason = f"DATA_DEGRADED_{age:.1f}s"

        # Fallback still degraded
        if self._fallback_active and state == "HEALTHY":
            state = "DEGRADED"
            reason = "FALLBACK_SOURCE"

        return DataHealthSnapshot(
            state=state,
            source_label=self._source_label if not is_stale else "STALE",
            last_tick_at=self._last_tick,
            age_seconds=age,
            is_stale=is_stale,
            reason=reason,
        )

    def is_healthy(self) -> bool:
        return self.snapshot().state == "HEALTHY"

    def blocks_new_entries(self) -> bool:
        """STALE or UNHEALTHY blocks entries (§82)."""
        return self.snapshot().state == "STALE"

    def latency_budget(self, tick_ts: datetime, signal_ts: datetime, risk_ts: datetime, submit_ts: datetime) -> dict:
        """§61 latency budget checks."""
        return {
            "tick_to_signal_ms": (signal_ts - tick_ts).total_seconds() * 1000,
            "signal_to_risk_ms": (risk_ts - signal_ts).total_seconds() * 1000 if risk_ts and signal_ts else None,
            "risk_to_submit_ms": (submit_ts - risk_ts).total_seconds() * 1000 if submit_ts and risk_ts else None,
        }


# For api parity expose DataHealth alias
DataHealth = DataHealthMonitor
