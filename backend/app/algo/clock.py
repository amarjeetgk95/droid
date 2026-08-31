"""
Clock & Timestamp Authority — §6

Exchange timestamp is authority. Fallback: broker/gateway arrival.
Server clock only for processing metadata. Track drift.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Literal
import structlog

logger = structlog.get_logger()

ClockSource = Literal["EXCHANGE", "BROKER_GATEWAY", "SERVER"]


@dataclass
class ClockMetrics:
    exchange_gateway_delay_ms: float | None = None
    gateway_server_delay_ms: float | None = None
    server_drift_ms: float | None = None
    last_exchange_ts: datetime | None = None
    last_gateway_ts: datetime | None = None
    last_server_ts: datetime | None = None


class ClockAuthority:
    """Single time authority per §6."""

    # Thresholds configurable (ms)
    DEGRADED_DRIFT_MS: float = 500
    STALE_DRIFT_MS: float = 2000
    STALE_DATA_AGE_S: float = 5.0

    def __init__(self):
        self._metrics = ClockMetrics()
        self._drift_exceeded_at: datetime | None = None

    def ingest(
        self,
        exchange_ts: datetime | None,
        gateway_ts: datetime | None = None,
        server_ts: datetime | None = None,
    ) -> datetime:
        """
        Return authoritative timestamp for event ordering.
        Also updates drift metrics.
        Never silently rewrites timestamps.
        """
        now = datetime.now(timezone.utc)
        server_ts = server_ts or now
        gateway_ts = gateway_ts or server_ts

        # Authority selection
        if exchange_ts is not None:
            authoritative = exchange_ts
            source: ClockSource = "EXCHANGE"
        elif gateway_ts is not None:
            authoritative = gateway_ts
            source = "BROKER_GATEWAY"
        else:
            authoritative = server_ts
            source = "SERVER"

        # Track delays
        if exchange_ts and gateway_ts:
            self._metrics.exchange_gateway_delay_ms = (gateway_ts - exchange_ts).total_seconds() * 1000
        if gateway_ts and server_ts:
            self._metrics.gateway_server_delay_ms = (server_ts - gateway_ts).total_seconds() * 1000
        if exchange_ts and server_ts:
            self._metrics.server_drift_ms = abs((server_ts - exchange_ts).total_seconds() * 1000)

        self._metrics.last_exchange_ts = exchange_ts
        self._metrics.last_gateway_ts = gateway_ts
        self._metrics.last_server_ts = server_ts

        logger.debug("clock_ingest", source=source, authoritative=authoritative.isoformat(), drift_ms=self._metrics.server_drift_ms)
        return authoritative

    def health(self) -> str:
        """Return DATA_HEALTH contribution from clock: HEALTHY / DEGRADED / STALE"""
        drift = self._metrics.server_drift_ms
        if drift is None:
            return "HEALTHY"
        if drift >= self.STALE_DRIFT_MS:
            return "STALE"
        if drift >= self.DEGRADED_DRIFT_MS:
            return "DEGRADED"
        return "HEALTHY"

    def metrics(self) -> ClockMetrics:
        return self._metrics


# Singleton for convenience
clock_authority = ClockAuthority()
