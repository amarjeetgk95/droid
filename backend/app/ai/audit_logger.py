"""
Audit Logger — §2, §15

Append-only audit trail for AI decisions.
Fire-and-forget with local durable queue; never blocks main process.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional
import structlog

from app.ai.schemas import (
    AuditRecord,
    AISignal,
    LatencyBreakdown,
)

logger = structlog.get_logger()

MAX_BUFFER_SIZE = 10000
BUFFER_FLUSH_INTERVAL_SECONDS = 5.0


class AuditLogger:
    """
    Append-only audit logger for AI decisions.

    Per §2: Fire-and-forget with local durable queue; never blocks main process.
    Per §15: Append-only; corrections are new records referencing original signal_id.
    """

    def __init__(self):
        self._buffer: list[AuditRecord] = []
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
        self._total_records = 0
        self._buffer_overflow_count = 0

    async def start(self) -> None:
        """Start background flush task."""
        if self._running:
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("audit_logger_started")

    async def stop(self) -> None:
        """Stop background flush and flush remaining records."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_buffer()
        logger.info("audit_logger_stopped", total_records=self._total_records)

    def log(
        self,
        signal: AISignal,
        ai_input: dict,
        ai_output: dict,
        latency_breakdown: LatencyBreakdown,
        execution_decision: str,
        actual_execution: Optional[str] = None,
        actual_fill: Optional[dict] = None,
        eventual_outcome: Optional[str] = None,
    ) -> str:
        """
        Log AI decision to audit trail.

        Args:
            signal: AI signal
            ai_input: Input to AI provider
            ai_output: Raw output from AI provider
            latency_breakdown: Latency breakdown
            execution_decision: PASS or REJECT
            actual_execution: What actually happened (e.g., FILLED, REJECTED)
            actual_fill: Fill details if executed
            eventual_outcome: Final outcome (e.g., WIN, LOSS, BREAKEVEN)

        Returns:
            record_id for reference
        """
        record_id = str(uuid.uuid4())

        record = AuditRecord(
            record_id=record_id,
            timestamp=datetime.now(timezone.utc),
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            market_context_hash_version=signal.version,
            regime=signal.regime.value if signal.regime else "",
            ai_provider=signal.provider,
            ai_model=signal.model,
            prompt_version="1.0.0",
            ai_input=ai_input,
            ai_output=ai_output,
            validation_result=signal.validation_result.value,
            rejection_reason_code=signal.rejection_reason_code.value if signal.rejection_reason_code else None,
            latency_breakdown=latency_breakdown,
            signal_ttl=signal.ttl_seconds,
            execution_decision=execution_decision,
            actual_execution=actual_execution,
            actual_fill=actual_fill,
            eventual_outcome=eventual_outcome,
        )

        self._buffer.append(record)
        self._total_records += 1

        if len(self._buffer) >= MAX_BUFFER_SIZE:
            self._buffer_overflow_count += 1
            logger.warning(
                "audit_buffer_overflow",
                buffer_size=len(self._buffer),
                overflow_count=self._buffer_overflow_count,
            )
            asyncio.create_task(self._flush_buffer())

        return record_id

    def log_correction(self, original_signal_id: str, correction_record_id: str, reason: str) -> str:
        """
        Log a correction to a previous record.

        Per §15: Corrections are new records referencing original signal_id.
        """
        record_id = str(uuid.uuid4())
        record = AuditRecord(
            record_id=record_id,
            timestamp=datetime.now(timezone.utc),
            signal_id=original_signal_id,
            execution_decision=f"CORRECTION:{reason}",
            ai_input={"correction_record_id": correction_record_id},
            ai_output={"reason": reason},
            validation_result="CORRECTION",
        )
        self._buffer.append(record)
        return record_id

    async def _flush_loop(self) -> None:
        """Background loop to flush buffer periodically."""
        while self._running:
            await asyncio.sleep(BUFFER_FLUSH_INTERVAL_SECONDS)
            await self._flush_buffer()

    async def _flush_buffer(self) -> None:
        """Flush buffered records to durable storage."""
        if not self._buffer:
            return

        records_to_flush = self._buffer[:]
        self._buffer = []

        try:
            for record in records_to_flush:
                await self._persist_record(record)
            logger.debug("audit_records_flushed", count=len(records_to_flush))
        except Exception as e:
            logger.error("audit_flush_failed", error=str(e), count=len(records_to_flush))
            self._buffer = records_to_flush + self._buffer

    async def _persist_record(self, record: AuditRecord) -> None:
        """
        Persist single record to durable storage.

        In a full implementation, this would write to a database.
        For now, logs the record for downstream processing.
        """
        logger.info(
            "audit_record",
            record_id=record.record_id,
            signal_id=record.signal_id,
            symbol=record.symbol,
            timestamp=record.timestamp.isoformat(),
            execution_decision=record.execution_decision,
            provider=record.ai_provider,
            model=record.ai_model,
            latency_ms=record.latency_breakdown.total_latency_ms if record.latency_breakdown else 0,
        )

    def get_buffer_size(self) -> int:
        """Get current buffer size."""
        return len(self._buffer)

    def get_total_records(self) -> int:
        """Get total records logged."""
        return self._total_records

    def get_buffer_overflow_count(self) -> int:
        """Get number of times buffer overflowed."""
        return self._buffer_overflow_count

    def is_healthy(self) -> bool:
        """Check if audit logger is healthy (buffer not growing unbounded)."""
        return len(self._buffer) < MAX_BUFFER_SIZE * 0.9


audit_logger = AuditLogger()
