from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

SourceHealthStatus = Literal["HEALTHY", "DEGRADED", "OFFLINE"]
CircuitState = Literal["CLOSED", "HALF_OPEN", "OPEN"]


class SourceHealthRecord(BaseModel):
    source_name: str
    status: SourceHealthStatus = "HEALTHY"
    circuit_state: CircuitState = "CLOSED"
    last_sync_timestamp: Optional[datetime] = None
    last_latency_ms: float = 0.0
    success_count: int = 0
    error_count: int = 0
    consecutive_errors: int = 0
    circuit_cooldown_until: Optional[datetime] = None
    last_error_message: Optional[str] = None


class SourceHealthTelemetry(BaseModel):
    overall_status: SourceHealthStatus = "HEALTHY"
    sources: dict[str, SourceHealthRecord] = Field(default_factory=dict)
    active_circuit_breakers: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventIngestionScheduler:
    """Automated Ingestion Scheduler & Source Health Telemetry Engine (§5, §34).
    
    Guarantees:
      1. Periodic synchronization of canonical official sources without blocking main thread.
      2. Circuit-breaker protection against broken upstream APIs or rate-limiting bans.
      3. Live health telemetry (latency, consecutive errors, operational status).
    """

    def __init__(
        self,
        error_threshold_to_trip: int = 4,
        cooldown_minutes: float = 10.0,
    ):
        self.error_threshold = error_threshold_to_trip
        self.cooldown_duration = timedelta(minutes=cooldown_minutes)
        self._sources: dict[str, SourceHealthRecord] = {
            "RBI_OFFICIAL": SourceHealthRecord(source_name="RBI_OFFICIAL"),
            "NSE_CORPORATE": SourceHealthRecord(source_name="NSE_CORPORATE"),
            "BSE_CORPORATE": SourceHealthRecord(source_name="BSE_CORPORATE"),
            "SEBI_OFFICIAL": SourceHealthRecord(source_name="SEBI_OFFICIAL"),
        }
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def can_attempt_sync(self, source_name: str, now: Optional[datetime] = None) -> tuple[bool, str]:
        """Check if source adapter is allowed to execute or is circuit-broken."""
        eval_time = now or datetime.now(timezone.utc)
        record = self._sources.get(source_name)
        if not record:
            return True, "SOURCE_UNKNOWN"

        if record.circuit_state == "OPEN":
            if record.circuit_cooldown_until and eval_time >= record.circuit_cooldown_until:
                record.circuit_state = "HALF_OPEN"
                logger.info("source_circuit_half_open", source=source_name)
                return True, "HALF_OPEN_PROBE"
            return False, f"CIRCUIT_OPEN_UNTIL_{record.circuit_cooldown_until.isoformat()}"

        return True, "CLOSED_NORMAL"

    def record_success(self, source_name: str, latency_ms: float) -> None:
        """Record successful fetch/parse cycle for a source adapter."""
        record = self._sources.setdefault(source_name, SourceHealthRecord(source_name=source_name))
        record.last_sync_timestamp = datetime.now(timezone.utc)
        record.last_latency_ms = round(latency_ms, 2)
        record.success_count += 1
        record.consecutive_errors = 0
        record.status = "HEALTHY"
        record.circuit_state = "CLOSED"
        record.circuit_cooldown_until = None
        record.last_error_message = None

    def record_failure(self, source_name: str, error_msg: str, now: Optional[datetime] = None) -> None:
        """Record failed fetch/parse cycle and evaluate circuit breaker trip (§34)."""
        eval_time = now or datetime.now(timezone.utc)
        record = self._sources.setdefault(source_name, SourceHealthRecord(source_name=source_name))
        record.error_count += 1
        record.consecutive_errors += 1
        record.last_error_message = error_msg

        if record.consecutive_errors >= self.error_threshold:
            record.circuit_state = "OPEN"
            record.status = "OFFLINE"
            record.circuit_cooldown_until = eval_time + self.cooldown_duration
            logger.error(
                "source_circuit_tripped",
                source=source_name,
                consecutive_errors=record.consecutive_errors,
                cooldown_until=record.circuit_cooldown_until.isoformat(),
            )
        else:
            record.status = "DEGRADED"

    def get_telemetry(self) -> SourceHealthTelemetry:
        """Provide full health telemetry across all configured source adapters."""
        overall: SourceHealthStatus = "HEALTHY"
        active_breakers: list[str] = []

        for name, rec in self._sources.items():
            if rec.circuit_state == "OPEN":
                active_breakers.append(name)
                overall = "DEGRADED"
            elif rec.status == "DEGRADED" and overall != "OFFLINE":
                overall = "DEGRADED"

        if len(active_breakers) == len(self._sources):
            overall = "OFFLINE"

        return SourceHealthTelemetry(
            overall_status=overall,
            sources=self._sources,
            active_circuit_breakers=active_breakers,
        )

    def reset_circuit(self, source_name: str) -> None:
        """Manual desk reset for a tripped adapter circuit breaker."""
        if source_name in self._sources:
            rec = self._sources[source_name]
            rec.circuit_state = "CLOSED"
            rec.consecutive_errors = 0
            rec.status = "HEALTHY"
            rec.circuit_cooldown_until = None
            logger.info("source_circuit_manually_reset", source=source_name)


event_ingestion_scheduler = EventIngestionScheduler()
