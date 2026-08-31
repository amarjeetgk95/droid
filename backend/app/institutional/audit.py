"""
Audit Trail — §70
Persist enough to reconstruct every signal.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

@dataclass
class AuditRecord:
    audit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str = ""
    instrument_id: str = ""
    canonical_timestamp_utc: int | None = None
    exchange_timestamp: int | None = None
    received_timestamp_utc: int | None = None
    sequence_id: int | None = None

    market_context: dict | None = None
    strategy_output: dict | None = None

    ai_request_metadata: dict | None = None
    ai_response: dict | None = None
    ai_schema_validation: dict | None = None

    cross_market_snapshot: dict | None = None
    synchronization_status: str | None = None

    risk_decision: dict | None = None
    portfolio_state_summary: dict | None = None

    ttl_ms: int | None = None
    expires_at_utc: int | None = None

    execution_intent_id: str | None = None
    broker_order_id: str | None = None

    final_state: str | None = None
    error_state: str | None = None
    created_at_ms: int = field(default_factory=lambda: int(time.time()*1000))

    def to_dict(self) -> dict:
        return {
            "audit_id": self.audit_id,
            "signal_id": self.signal_id,
            "instrument_id": self.instrument_id,
            "canonical_timestamp_utc": self.canonical_timestamp_utc,
            "exchange_timestamp": self.exchange_timestamp,
            "received_timestamp_utc": self.received_timestamp_utc,
            "sequence_id": self.sequence_id,
            "market_context": self.market_context,
            "strategy_output": self.strategy_output,
            "ai_request_metadata": self.ai_request_metadata,
            "ai_response": self.ai_response,
            "ai_schema_validation": self.ai_schema_validation,
            "cross_market_snapshot": self.cross_market_snapshot,
            "synchronization_status": self.synchronization_status,
            "risk_decision": self.risk_decision,
            "portfolio_state_summary": self.portfolio_state_summary,
            "ttl_ms": self.ttl_ms,
            "expires_at_utc": self.expires_at_utc,
            "execution_intent_id": self.execution_intent_id,
            "broker_order_id": self.broker_order_id,
            "final_state": self.final_state,
            "error_state": self.error_state,
            "created_at_ms": self.created_at_ms,
        }


class AuditTrail:
    def __init__(self, max_records: int = 10000):
        self._records: list[AuditRecord] = []
        self._by_signal: dict[str, AuditRecord] = {}
        self.max_records = max_records

    def append(self, rec: AuditRecord) -> None:
        self._records.append(rec)
        if rec.signal_id:
            self._by_signal[rec.signal_id] = rec
        if len(self._records) > self.max_records:
            old = self._records.pop(0)
            # keep map but might stale; keep for recent only
        # Also persist to DB asynchronously if available — fire-and-forget
        # (caller may also write to AlgoAuditLog)

    def get_by_signal(self, signal_id: str) -> AuditRecord | None:
        return self._by_signal.get(signal_id)

    def recent(self, limit: int = 50) -> list[dict]:
        return [r.to_dict() for r in self._records[-limit:]][::-1]

    def reconstruct(self, signal_id: str) -> dict | None:
        rec = self.get_by_signal(signal_id)
        return rec.to_dict() if rec else None


audit_trail = AuditTrail()
