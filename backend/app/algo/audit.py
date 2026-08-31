"""
Audit Trail — §70, Observability — §68-69

Every material event append-only. Answers why trade entered/rejected/exit etc.
Alert deduplication with fingerprint + cooldown.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Any
import structlog

logger = structlog.get_logger()


@dataclass
class AuditRecord:
    account_id: Any
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = ""  # SIGNAL_CREATED, RISK_DECISION, ORDER_SUBMITTED, FILL, etc.
    strategy_id: str | None = None
    signal_id: Any | None = None
    symbol: str | None = None
    instrument_id: str | None = None
    market_state: dict = field(default_factory=dict)
    technical_state: dict = field(default_factory=dict)
    mtf_state: dict = field(default_factory=dict)
    fo_state: dict = field(default_factory=dict)
    ai_result: dict = field(default_factory=dict)
    model_id: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    signal: dict = field(default_factory=dict)
    trigger: str | None = None
    trade_risk_result: str | None = None
    portfolio_risk_result: str | None = None
    risk_checks: dict = field(default_factory=dict)
    capital_limit: Any | None = None
    reservation_id: Any | None = None
    client_order_id: Any | None = None
    broker_order_id: str | None = None
    execution_result: dict = field(default_factory=dict)
    expected_price: Any | None = None
    trigger_price: Any | None = None
    actual_fill: Any | None = None
    slippage: Any | None = None
    realized_pnl: Any | None = None
    portfolio_state: dict = field(default_factory=dict)
    reconciliation_state: str | None = None
    risk_state: str | None = None
    data_health_state: str | None = None
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "account_id": str(self.account_id),
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "strategy_id": self.strategy_id,
            "signal_id": str(self.signal_id) if self.signal_id else None,
            "symbol": self.symbol,
            "instrument_id": self.instrument_id,
            "market_state": self.market_state,
            "technical_state": self.technical_state,
            "mtf_state": self.mtf_state,
            "fo_state": self.fo_state,
            "ai_result": self.ai_result,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
            "signal": self.signal,
            "trigger": self.trigger,
            "trade_risk_result": self.trade_risk_result,
            "portfolio_risk_result": self.portfolio_risk_result,
            "risk_checks": self.risk_checks,
            "capital_limit": str(self.capital_limit) if self.capital_limit else None,
            "reservation_id": str(self.reservation_id) if self.reservation_id else None,
            "client_order_id": str(self.client_order_id) if self.client_order_id else None,
            "broker_order_id": self.broker_order_id,
            "execution_result": self.execution_result,
            "expected_price": str(self.expected_price) if self.expected_price else None,
            "trigger_price": str(self.trigger_price) if self.trigger_price else None,
            "actual_fill": str(self.actual_fill) if self.actual_fill else None,
            "slippage": str(self.slippage) if self.slippage else None,
            "realized_pnl": str(self.realized_pnl) if self.realized_pnl else None,
            "portfolio_state": self.portfolio_state,
            "reconciliation_state": self.reconciliation_state,
            "risk_state": self.risk_state,
            "data_health_state": self.data_health_state,
            "details": self.details,
        }


class AuditTrail:
    """
    Append-only audit. In production persisted to algo_audit_log table.
    In-memory buffer for testing + structured logging.
    """

    def __init__(self, max_buffer: int = 10000):
        self._buffer: list[AuditRecord] = []
        self._max_buffer = max_buffer

    def append(self, record: AuditRecord) -> AuditRecord:
        self._buffer.append(record)
        if len(self._buffer) > self._max_buffer:
            self._buffer = self._buffer[-self._max_buffer:]
        logger.info(
            "audit_event",
            event_type=record.event_type,
            account_id=str(record.account_id),
            symbol=record.symbol,
            trade_risk=record.trade_risk_result,
            portfolio_risk=record.portfolio_risk_result,
        )
        return record

    def query(self, account_id: Any, limit: int = 100, event_type: str | None = None) -> list[AuditRecord]:
        res = [r for r in self._buffer if str(r.account_id) == str(account_id)]
        if event_type:
            res = [r for r in res if r.event_type == event_type]
        res.sort(key=lambda r: r.timestamp, reverse=True)
        return res[:limit]

    def explain_trade(self, signal_id: Any) -> dict:
        """Answer: Why entered/rejected/exit etc + portfolio exposure + model config."""
        related = [r for r in self._buffer if str(r.signal_id) == str(signal_id)]
        related.sort(key=lambda r: r.timestamp)
        return {
            "signal_id": str(signal_id),
            "events": [r.to_dict() for r in related],
            "summary": {
                "entered": any(r.trade_risk_result == "APPROVED" and r.portfolio_risk_result == "APPROVED" for r in related),
                "rejected_reason": next((r.risk_checks for r in related if r.trade_risk_result == "REJECTED" or r.portfolio_risk_result == "REJECTED"), None),
                "exit_trigger": next((r.details.get("exit_trigger") for r in related if r.details.get("exit_trigger")), None),
                "portfolio_exposure": next((r.portfolio_state for r in related if r.portfolio_state), None),
                "model": next(({"model_id": r.model_id, "model_version": r.model_version} for r in related if r.model_id), None),
            }
        }


audit_trail = AuditTrail()


# ── Alerting with deduplication — §69 ────────────────────────────────

class AlertDeduper:
    """
    Fingerprint + cooldown + severity escalation + incident lifecycle.
    First failure → ALERT, continued → UPDATE, recovery → RECOVERY ALERT
    Critical incidents continue escalating without suppression.
    """

    def __init__(self, default_cooldown_s: int = 300, critical_cooldown_s: int = 60):
        self._last_sent: dict[str, datetime] = {}
        self._incident_state: dict[str, str] = {}  # fingerprint -> ACTIVE/RECOVERED
        self.default_cooldown_s = default_cooldown_s
        self.critical_cooldown_s = critical_cooldown_s

    def fingerprint(self, title: str, metric_name: str | None = None, account_id: Any = None) -> str:
        raw = f"{account_id}:{metric_name}:{title}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    def should_send(self, fingerprint: str, severity: str, is_recovery: bool = False) -> tuple[bool, str]:
        now = datetime.now(timezone.utc)
        cooldown = self.critical_cooldown_s if severity == "CRITICAL" else self.default_cooldown_s

        if is_recovery:
            # Always send recovery alerts
            self._incident_state[fingerprint] = "RECOVERED"
            self._last_sent[fingerprint] = now
            return True, "RECOVERY_ALERT"

        last = self._last_sent.get(fingerprint)
        state = self._incident_state.get(fingerprint)

        if last is None or state == "RECOVERED":
            self._incident_state[fingerprint] = "ACTIVE"
            self._last_sent[fingerprint] = now
            return True, "ALERT"

        elapsed = (now - last).total_seconds()
        if severity == "CRITICAL":
            # Critical escalates even within cooldown but with shorter interval
            if elapsed >= cooldown:
                self._last_sent[fingerprint] = now
                return True, "CRITICAL_ESCALATION"
            return False, "COOLDOWN_SUPPRESSED_CRITICAL_WILL_ESCALATE"

        if elapsed >= cooldown:
            self._last_sent[fingerprint] = now
            return True, "UPDATE"

        return False, "COOLDOWN_SUPPRESSED"

    def mark_recovery(self, fingerprint: str) -> None:
        self._incident_state[fingerprint] = "RECOVERED"


alert_deduper = AlertDeduper()
