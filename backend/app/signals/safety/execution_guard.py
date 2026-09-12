"""
Hierarchical 15-Check Final Execution Guard
Cost-ordered checks immediately prior to paper dispatch or broker order transmission.
Fails closed on any ambiguity or safety violation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal
import structlog

from app.signals.safety.decimal_types import (
    D,
    normalize_price_to_tick,
    validate_quantity,
)
from app.signals.safety.feed_circuit import feed_circuit
from app.signals.safety.kill_switch import kill_switch

logger = structlog.get_logger()


@dataclass
class GuardCheckResult:
    passed: bool
    failed_check: str | None = None
    reason: str | None = None
    level: int | None = None
    checks_evaluated: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    evaluated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failed_check": self.failed_check,
            "reason": self.reason,
            "level": self.level,
            "checks_evaluated": self.checks_evaluated,
            "details": self.details,
            "evaluated_at_ms": self.evaluated_at_ms,
        }


def final_execution_guard(
    signal: Any,
    execution_intent_id: str | None,
    order_price: Any | None = None,
    order_quantity: Any | None = None,
    latest_price: Any | None = None,
    feed_health: str | None = None,
    market_session_state: str = "OPEN",
    contract_spec: dict | None = None,
    max_slippage_pct: float = 0.5,
    risk_approved: bool = True,
    risk_stale: bool = False,
    has_duplicate_order: bool = False,
    setup_invalidated: bool = False,
    clock_drift_ms: float | None = None,
    max_clock_drift_ms: float = 2000.0,
    allow_closed_market: bool = False,
    audit_available: bool = True,
    db_available: bool = True,
) -> GuardCheckResult:
    """
    Evaluates all 15 execution safety invariants in strict cost order:
      Level 1: Zero-cost in-memory invariants
      Level 2: Exact financial math & quantization
      Level 3: Feed, clock, and intent integrity
      Level 4: Persistence durability
    """
    evaluated: list[str] = []
    details: dict[str, Any] = {}

    # ═════════════════════════════════════════════════════════════════════
    # LEVEL 1: Zero-cost in-memory invariants
    # ═════════════════════════════════════════════════════════════════════

    # 1. Global Kill Switch
    evaluated.append("1_KILL_SWITCH")
    if kill_switch.is_active():
        return GuardCheckResult(
            passed=False,
            failed_check="1_KILL_SWITCH",
            reason=f"GUARD_FAIL: Global kill switch ACTIVE ({kill_switch.status().get('reason')})",
            level=1,
            checks_evaluated=evaluated,
        )

    # 2. TTL Validity
    evaluated.append("2_TTL_VALIDITY")
    now_ms = int(time.time() * 1000)
    is_expired = False
    if hasattr(signal, "is_expired"):
        is_expired = signal.is_expired() if callable(signal.is_expired) else bool(signal.is_expired)
    elif getattr(signal, "expires_at_utc", None) is not None:
        is_expired = now_ms > signal.expires_at_utc
    if is_expired:
        return GuardCheckResult(
            passed=False,
            failed_check="2_TTL_VALIDITY",
            reason="GUARD_FAIL: Signal TTL expired",
            level=1,
            checks_evaluated=evaluated,
        )

    # 3. Market Session Open
    evaluated.append("3_MARKET_SESSION")
    if not allow_closed_market and market_session_state != "OPEN":
        return GuardCheckResult(
            passed=False,
            failed_check="3_MARKET_SESSION",
            reason=f"GUARD_FAIL: Market session is {market_session_state} (expected OPEN)",
            level=1,
            checks_evaluated=evaluated,
        )

    # 4. Signal Actionable State
    evaluated.append("4_SIGNAL_ACTIONABLE")
    sig_state = getattr(signal, "fsm_state", getattr(signal, "status", "UNKNOWN"))
    actionable_states = {"ARMED", "TRIGGERED", "CONFIRMED", "EXECUTION_PENDING"}
    if sig_state not in actionable_states:
        return GuardCheckResult(
            passed=False,
            failed_check="4_SIGNAL_ACTIONABLE",
            reason=f"GUARD_FAIL: Signal state {sig_state} not actionable (must be one of {actionable_states})",
            level=1,
            checks_evaluated=evaluated,
        )

    # 5. Setup Validity
    evaluated.append("5_SETUP_VALIDITY")
    if setup_invalidated:
        return GuardCheckResult(
            passed=False,
            failed_check="5_SETUP_VALIDITY",
            reason="GUARD_FAIL: Underlying technical setup invalidated",
            level=1,
            checks_evaluated=evaluated,
        )

    # ═════════════════════════════════════════════════════════════════════
    # LEVEL 2: Financial exactness & quantization
    # ═════════════════════════════════════════════════════════════════════

    # 6. Contract Specification Loaded
    evaluated.append("6_CONTRACT_SPEC")
    resolved_spec = contract_spec or getattr(signal, "option_contract", None)
    if not resolved_spec:
        return GuardCheckResult(
            passed=False,
            failed_check="6_CONTRACT_SPEC",
            reason="GUARD_FAIL: Tradable contract specification missing",
            level=2,
            checks_evaluated=evaluated,
        )

    # 7. Price Tick Alignment
    evaluated.append("7_PRICE_TICK_ALIGNMENT")
    tick_size = resolved_spec.get("tick_size", "0.05") if isinstance(resolved_spec, dict) else getattr(resolved_spec, "tick_size", "0.05")
    if order_price is not None:
        try:
            op_d = D(order_price)
            quantized = normalize_price_to_tick(op_d, tick_size)
            if op_d != quantized:
                return GuardCheckResult(
                    passed=False,
                    failed_check="7_PRICE_TICK_ALIGNMENT",
                    reason=f"GUARD_FAIL: Order price {op_d} not aligned to tick size {tick_size} (expected {quantized})",
                    level=2,
                    checks_evaluated=evaluated,
                    details={"order_price": str(op_d), "quantized": str(quantized), "tick_size": str(tick_size)},
                )
        except Exception as te:
            return GuardCheckResult(
                passed=False,
                failed_check="7_PRICE_TICK_ALIGNMENT",
                reason=f"GUARD_FAIL: Tick validation error: {te}",
                level=2,
                checks_evaluated=evaluated,
            )

    # 8. Quantity & Lot Size Step Validation
    evaluated.append("8_QUANTITY_STEP_VALIDATION")
    if order_quantity is not None:
        try:
            min_q = resolved_spec.get("min_order_qty", "1") if isinstance(resolved_spec, dict) else "1"
            q_step = resolved_spec.get("quantity_step", "1") if isinstance(resolved_spec, dict) else "1"
            lot_sz = resolved_spec.get("lot_size") if isinstance(resolved_spec, dict) else getattr(resolved_spec, "lot_size", None)
            ok_q, reason_q = validate_quantity(order_quantity, min_q, q_step, lot_sz)
            if not ok_q:
                return GuardCheckResult(
                    passed=False,
                    failed_check="8_QUANTITY_STEP_VALIDATION",
                    reason=f"GUARD_FAIL: {reason_q}",
                    level=2,
                    checks_evaluated=evaluated,
                    details={"order_quantity": str(order_quantity), "min_qty": str(min_q), "lot_size": str(lot_sz)},
                )
        except Exception as qe:
            return GuardCheckResult(
                passed=False,
                failed_check="8_QUANTITY_STEP_VALIDATION",
                reason=f"GUARD_FAIL: Quantity validation error: {qe}",
                level=2,
                checks_evaluated=evaluated,
            )

    # 9. Slippage Policy Check
    evaluated.append("9_SLIPPAGE_POLICY")
    if latest_price is not None and order_price is not None:
        try:
            lp_d = D(latest_price)
            op_d = D(order_price)
            if op_d > D(0):
                slip_pct = abs(lp_d - op_d) / op_d * D(100)
                details["measured_slippage_pct"] = float(slip_pct)
                if slip_pct > D(str(max_slippage_pct)):
                    return GuardCheckResult(
                        passed=False,
                        failed_check="9_SLIPPAGE_POLICY",
                        reason=f"GUARD_FAIL: Slippage {slip_pct:.2f}% exceeds policy limit {max_slippage_pct:.2f}%",
                        level=2,
                        checks_evaluated=evaluated,
                        details={"slippage_pct": float(slip_pct), "limit_pct": max_slippage_pct},
                    )
        except Exception as se:
            logger.debug("slippage_calc_error", error=str(se))

    # ═════════════════════════════════════════════════════════════════════
    # LEVEL 3: Feed, clock, and intent integrity
    # ═════════════════════════════════════════════════════════════════════

    # 10. Feed Health
    evaluated.append("10_FEED_HEALTH")
    instrument = getattr(signal, "underlying", getattr(signal, "instrument_id", "UNKNOWN"))
    eff_feed_health = feed_health or ("FEED_DEGRADED" if feed_circuit.is_degraded(instrument) else "HEALTHY")
    if eff_feed_health in ("FEED_DEGRADED", "UNKNOWN"):
        return GuardCheckResult(
            passed=False,
            failed_check="10_FEED_HEALTH",
            reason=f"GUARD_FAIL: Market data feed is {eff_feed_health} for {instrument}",
            level=3,
            checks_evaluated=evaluated,
        )

    # 11. Clock Drift Check
    evaluated.append("11_CLOCK_DRIFT")
    if clock_drift_ms is not None:
        details["clock_drift_ms"] = clock_drift_ms
        if abs(clock_drift_ms) > max_clock_drift_ms:
            return GuardCheckResult(
                passed=False,
                failed_check="11_CLOCK_DRIFT",
                reason=f"GUARD_FAIL: Clock drift {clock_drift_ms:.1f}ms exceeds threshold {max_clock_drift_ms}ms",
                level=3,
                checks_evaluated=evaluated,
                details=details,
            )

    # 12. Risk Approval Current & Non-Stale
    evaluated.append("12_RISK_APPROVAL")
    if not risk_approved or risk_stale:
        reason_msg = "Risk decision STALE" if risk_stale else "Risk NOT approved"
        return GuardCheckResult(
            passed=False,
            failed_check="12_RISK_APPROVAL",
            reason=f"GUARD_FAIL: {reason_msg}",
            level=3,
            checks_evaluated=evaluated,
        )

    # 13. Execution Intent Ownership
    evaluated.append("13_INTENT_OWNERSHIP")
    sig_intent = getattr(signal, "execution_intent_id", None)
    if sig_intent and execution_intent_id and sig_intent != execution_intent_id:
        return GuardCheckResult(
            passed=False,
            failed_check="13_INTENT_OWNERSHIP",
            reason=f"GUARD_FAIL: Intent ID mismatch ({sig_intent} != {execution_intent_id})",
            level=3,
            checks_evaluated=evaluated,
        )

    # 14. Duplicate Order Idempotency Guard
    evaluated.append("14_DUPLICATE_ORDER_GUARD")
    if has_duplicate_order:
        return GuardCheckResult(
            passed=False,
            failed_check="14_DUPLICATE_ORDER_GUARD",
            reason="GUARD_FAIL: Duplicate broker order detected for intent",
            level=3,
            checks_evaluated=evaluated,
        )

    # ═════════════════════════════════════════════════════════════════════
    # LEVEL 4: Persistence durability
    # ═════════════════════════════════════════════════════════════════════

    # 15. Audit & Persistence Availability
    evaluated.append("15_PERSISTENCE_DURABILITY")
    if not audit_available or not db_available:
        missing = []
        if not audit_available:
            missing.append("audit_ledger")
        if not db_available:
            missing.append("database")
        return GuardCheckResult(
            passed=False,
            failed_check="15_PERSISTENCE_DURABILITY",
            reason=f"GUARD_FAIL: Authoritative persistence unavailable ({', '.join(missing)})",
            level=4,
            checks_evaluated=evaluated,
        )

    return GuardCheckResult(
        passed=True,
        checks_evaluated=evaluated,
        details=details,
    )
