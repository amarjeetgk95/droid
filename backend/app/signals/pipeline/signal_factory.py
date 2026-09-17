"""
Signal Factory & Registration Module for Quantitative Scanning Pipeline (Phase 3)
Constructs SignalInstance from validated, sized, and enriched candidate,
registers with SignalFSMManager, logs to SignalAuditLedger, and queues Telegram notifications.
"""
from __future__ import annotations

from typing import Any
import structlog

from app.signals.confluence import ARMED_THRESHOLD
from app.signals.contract_resolver import has_chain_mark
from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.strategies.base import SignalCandidate
from app.signals.trigger_gate import check_trigger_integrity

logger = structlog.get_logger()


def _validate_geometry_from_levels(
    underlying: Any,
    strategy: Any,
    direction: Any,
    spot_price: Any,
    entry_min: Any,
    entry_max: Any,
    trigger: Any,
    stop_loss: Any,
    target_1: Any,
    target_2: Any,
    risk_points: Any,
    risk_reward_t1: Any,
    risk_reward_t2: Any,
    is_scalp: bool,
    timeframe: Any,
) -> None:
    """Re-validates trigger/SL/target geometry. Raises ValueError on failure.

    The risk engine mutates SL/targets after the post-risk gates run, so the
    factory re-checks the final levels instead of trusting gate-time geometry.
    """
    gate = check_trigger_integrity(
        underlying=str(underlying or "?"),
        strategy=str(strategy or "?"),
        direction=str(direction or ""),
        spot_price=spot_price,
        entry_min=entry_min,
        entry_max=entry_max,
        trigger=trigger,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        risk_points=risk_points,
        risk_reward_t1=risk_reward_t1,
        risk_reward_t2=risk_reward_t2,
        is_scalp=bool(is_scalp),
        timeframe=str(timeframe or "5M"),
    )
    if not gate.passed:
        raise ValueError(f"TRIGGER_GEOMETRY_REJECTED:{gate.reason_code}:{gate.message}")


def build_signal_instance(
    cand: SignalCandidate,
    fused_score: float,
    fsm_init_state: str,
    risk_decision: Any,
    inst_overlay: dict[str, Any],
    ai_advice: Any | None,
    ml_pred: dict[str, Any] | None,
    overlay: Any | None,
    explain_bundle: Any | None,
    fno_is_degraded: bool,
) -> SignalInstance:
    """Constructs SignalInstance with Version 6.0 fields.

    Re-validates the final trigger/SL/target geometry (post risk-engine mutation).
    Raises ValueError when the levels carry no edge — the caller must drop the
    candidate instead of registering a born-triggered signal.
    """
    _validate_geometry_from_levels(
        underlying=cand.underlying,
        strategy=cand.strategy,
        direction=cand.direction,
        spot_price=cand.spot_price,
        entry_min=cand.entry_min,
        entry_max=cand.entry_max,
        trigger=cand.trigger,
        stop_loss=cand.stop_loss,
        target_1=cand.target_1,
        target_2=cand.target_2,
        risk_points=cand.risk_points,
        risk_reward_t1=cand.risk_reward_t1,
        risk_reward_t2=cand.risk_reward_t2,
        is_scalp=getattr(cand, "is_scalp", False),
        timeframe=getattr(cand, "timeframe", "5M"),
    )
    watch_ttl_seconds = cand.ttl_seconds
    if fsm_init_state == "VALIDATED":
        try:
            watch_ttl_seconds = min(int(cand.ttl_seconds or 300), 900)
        except Exception:
            watch_ttl_seconds = 300
        try:
            cand.rationale.append(
                f"WATCH only (score {fused_score:.1f} < ARMED {ARMED_THRESHOLD:.0f}) — waiting for confirmation, not executable"
            )
        except Exception:
            pass

    instance = SignalInstance(
        underlying=cand.underlying,
        strategy=cand.strategy,
        direction=cand.direction,
        timeframe=cand.timeframe,
        spot_price=cand.spot_price,
        signal_type=cand.signal_type,
        is_scalp=cand.is_scalp,
        entry_min=cand.entry_min,
        entry_max=cand.entry_max,
        trigger=cand.trigger,
        stop_loss=cand.stop_loss,
        initial_stop_loss=cand.stop_loss,
        current_stop_loss=cand.stop_loss,
        target_1=cand.target_1,
        target_2=cand.target_2,
        t1_price=cand.target_1,
        t2_price=cand.target_2,
        risk_points=cand.risk_points,
        risk_reward_t1=cand.risk_reward_t1,
        risk_reward_t2=cand.risk_reward_t2,
        ttl_seconds=watch_ttl_seconds,
        runner_ttl_seconds=cand.runner_ttl_seconds,
        time_stop_seconds=cand.time_stop_seconds,
        lots=risk_decision.lots,
        quantity=risk_decision.quantity,
        max_rupee_loss=risk_decision.max_rupee_loss,
        confidence=fused_score,
        confluence_breakdown={
            "technical": cand.technical_score,
            "mtf": cand.mtf_score,
            "fno": cand.fno_score,
            "regime": cand.regime_score,
            "ai": cand.ai_score,
            "ai_status": getattr(ai_advice, "status", "UNAVAILABLE") if ai_advice else "UNAVAILABLE",
            "ml_score": (ml_pred.get("bullish_pct") if "CALL" in cand.direction else ml_pred.get("bearish_pct")) if ml_pred else None,
            "ml_status": "AVAILABLE" if ml_pred else "UNAVAILABLE",
            "event_state": getattr(overlay, "proximity_state", "NORMAL") if overlay else "NORMAL",
            "event_sizing_multiplier": getattr(overlay, "sizing_multiplier", 1.0) if overlay else 1.0,
            "fno_degraded": fno_is_degraded,
            "institutional_delta": float(inst_overlay.get("delta", 0.0)) if isinstance(inst_overlay, dict) else 0.0,
            "institutional_applied": bool(inst_overlay.get("applied")) if isinstance(inst_overlay, dict) else False,
            "institutional_reasons": list(inst_overlay.get("reasons", [])) if isinstance(inst_overlay, dict) else [],
            "institutional_event_date": (inst_overlay.get("flow_event_date") if isinstance(inst_overlay, dict) else None),
            "institutional_downgrade": bool(inst_overlay.get("downgrade_to_validated")) if isinstance(inst_overlay, dict) else False,
            "institutional_composite": (inst_overlay.get("composite_score") if isinstance(inst_overlay, dict) else None),
            "institutional_composite_sentiment": (inst_overlay.get("composite_sentiment") if isinstance(inst_overlay, dict) else None),
            "institutional_composite_status": (inst_overlay.get("composite_status") if isinstance(inst_overlay, dict) else None),
        },
        rationale=cand.rationale,
        explain=explain_bundle,
        option_contract=cand.option_contract.model_dump() if cand.option_contract else None,
        greeks=cand.greeks,
        expected_move=cand.expected_move,
        ai_research=cand.ai_research,
        path_simulation=cand.path_simulation,
        fsm_state=fsm_init_state,
    )
    return instance


async def register_and_notify(instance: SignalInstance) -> None:
    """Registers signal in FSM, records into audit ledger, and enqueues Telegram alert.

    Fail-closed: geometry and live chain-mark are re-validated BEFORE registering.
    Audit/Telegram failures roll back the FSM registration (and audit row) and
    raise — never leave a ghost signal that exists in one store but not the others.
    """
    _validate_geometry_from_levels(
        underlying=instance.underlying,
        strategy=instance.strategy,
        direction=instance.direction,
        spot_price=instance.spot_price,
        entry_min=instance.entry_min,
        entry_max=instance.entry_max,
        trigger=instance.trigger,
        stop_loss=instance.stop_loss,
        target_1=instance.target_1,
        target_2=instance.target_2,
        risk_points=getattr(instance, "risk_points", None),
        risk_reward_t1=getattr(instance, "risk_reward_t1", 1.5),
        risk_reward_t2=getattr(instance, "risk_reward_t2", 3.0),
        is_scalp=getattr(instance, "is_scalp", False),
        timeframe=getattr(instance, "timeframe", "5M"),
    )
    if not has_chain_mark(getattr(instance, "option_contract", None)):
        raise ValueError("CHAIN_MARK_UNAVAILABLE: no live FYERS chain quote for contract")

    signal_fsm.register(instance)

    # Record into Signal Audit Ledger
    try:
        from app.signals.audit_ledger import signal_audit_ledger
        signal_audit_ledger.record_signal_created(
            signal_id=instance.signal_id,
            underlying=instance.underlying,
            strategy=instance.strategy,
            direction=instance.direction,
            timeframe=instance.timeframe,
            spot_price=float(instance.spot_price),
            trigger=float(instance.trigger),
            stop_loss=float(instance.stop_loss),
            target_1=float(instance.target_1),
            target_2=float(instance.target_2),
            confidence=float(instance.confidence),
            option_contract=instance.option_contract,
            status=instance.fsm_state,
        )
    except Exception as ae:
        logger.warning("audit_record_created_failed", error=str(ae))
        try:
            signal_fsm.delete(instance.signal_id)
        except Exception:
            pass
        raise

    # Enqueue Telegram notification
    try:
        from app.institutional.telegram_notifications import (
            SignalEvent,
            telegram_notification_queue,
        )
        ev = SignalEvent(
            event_type="POSSIBLE_SETUP",
            signal_id=instance.signal_id,
            instrument=instance.underlying,
            candle_timeframe=instance.timeframe,
            setup_type=f"{'⚡ ' if instance.is_scalp else ''}{instance.strategy}",
            direction="BULLISH" if "CALL" in instance.direction else "BEARISH",
            status=instance.fsm_state,
            trigger_level=float(instance.trigger),
            current_price=float(instance.spot_price),
            stop_loss=float(instance.stop_loss),
            target_low=float(instance.target_1),
            target_high=float(instance.target_2),
            confidence=float(instance.confidence),
        )
        await telegram_notification_queue.publish_signal_event(ev)
    except Exception as te:
        logger.warning("telegram_notify_failed", error=str(te))
        try:
            signal_fsm.delete(instance.signal_id)
        except Exception:
            pass
        try:
            from app.signals.audit_ledger import signal_audit_ledger
            signal_audit_ledger.delete_trade(instance.signal_id)
        except Exception:
            pass
        raise
