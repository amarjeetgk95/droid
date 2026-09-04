"""
Account & State Orchestration — §2-4, §79-82, §87-88

System modes OFF/PAPER/LIVE, consent, kill switch, live entry gate §81
"""
from __future__ import annotations

from typing import Literal
import structlog

logger = structlog.get_logger()

SystemMode = Literal["OFF", "PAPER", "LIVE"]
KillLevel = Literal["NONE","STOP_NEW_ENTRIES","CANCEL_ENTRY_ORDERS","EXIT_ALL_POSITIONS","FULL_EXECUTION_STOP"]


def live_entry_gate(checks: dict) -> tuple[bool, str | None]:
    """
    §81 Live entry permitted only when ALL required conditions pass.
    Otherwise NO_NEW_ENTRY.
    Checks dict keys per spec §81 list.
    """
    required = {
        "data_healthy": "DATA_UNHEALTHY",
        "clock_healthy": "CLOCK_DRIFT",
        "broker_healthy": "BROKER_UNHEALTHY",
        "reconciliation_healthy": "RECONCILIATION_BLOCKED",
        "instrument_valid": "INSTRUMENT_INVALID",
        "instrument_tradable": "INSTRUMENT_NOT_TRADABLE",
        "no_circuit": "CIRCUIT_ACTIVE",
        "signal_valid": "SIGNAL_INVALID",
        "technical_valid": "TECHNICAL_INVALID",
        "fno_valid": "FNO_INVALID",
        "ai_valid": "AI_INVALID",  # if required
        "position_sizing_valid": "POSITION_SIZING_INVALID",
        "algo_capital_available": "INSUFFICIENT_CAPITAL",
        "trade_risk_pass": "TRADE_RISK_REJECTED",
        "portfolio_risk_pass": "PORTFOLIO_RISK_REJECTED",
        "margin_available": "INSUFFICIENT_MARGIN",
        "liquidity_ok": "ILLIQUID",
        "spread_ok": "SPREAD_TOO_WIDE",
        "slippage_ok": "SLIPPAGE_EXCEEDED",
        "no_duplicate_signal": "DUPLICATE_SIGNAL",
        "no_duplicate_order": "DUPLICATE_ORDER",
        "conflict_resolved": "STRATEGY_CONFLICT_UNRESOLVED",
        "kill_switch_inactive": "KILL_SWITCH_ACTIVE",
        "execution_safety_pass": "EXECUTION_SAFETY_FAILED",
    }
    for key, reason in required.items():
        # if key not in checks, assume need to fail closed (§82, §70 when material uncertainty → NO_NEW_ENTRY)
        val = checks.get(key)
        if val is None:
            # Missing risk data never means zero risk (§88.33)
            # For gate: missing required check → block
            if key in ("data_healthy","clock_healthy","broker_healthy","reconciliation_healthy","trade_risk_pass","portfolio_risk_pass","kill_switch_inactive","execution_safety_pass"):
                return False, f"MISSING_CHECK_{key}"
            continue
        if val is False or val == "FAIL" or val == "REJECTED":
            return False, reason

    # Special: data_health stale → block even if other checks passed
    if checks.get("data_health_state") == "STALE":
        return False, "DATA_HEALTH_STALE"
    if checks.get("kill_switch_active"):
        return False, "KILL_SWITCH_ACTIVE"
    if checks.get("is_orphaned_alert"):
        return False, "ORPHANED_ALERT_ACTIVE"
    if checks.get("is_full_execution_stop"):
        return False, "FULL_EXECUTION_STOP"

    return True, None


# Interaction of critical states §80
CRITICAL_STATES = {"FULL_EXECUTION_STOP","ORPHANED_ALERT","CRITICAL_RECONCILIATION_FAILURE","CRITICAL_DATA_FAILURE","CRITICAL_BROKER_FAILURE","GLOBAL_KILL_SWITCH"}

def critical_state_snapshot(global_state: str, kill_level: KillLevel, has_orphaned: bool) -> dict:
    is_critical = global_state in CRITICAL_STATES or kill_level == "FULL_EXECUTION_STOP" or has_orphaned
    return {
        "is_critical": is_critical,
        "new_entries_blocked": is_critical or kill_level != "NONE",
        "ai_canary_influence_zero": is_critical,
        "normal_triggers_blocked": is_critical,
        "portfolio_risk_active": True,
        "position_monitoring_active": True,
        "emergency_exit_active": True,
        "reconciliation_active": True,
        "alerting_active": True,
    }

def should_restore_after_recovery(manual_validation_done: bool) -> bool:
    """After recovery, do not automatically restore LIVE/canary without explicit validation §80."""
    return manual_validation_done is True
