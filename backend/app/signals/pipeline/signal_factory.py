"""
Signal Factory & Registration Module for Quantitative Scanning Pipeline (Phase 3)
Constructs SignalInstance from validated, sized, and enriched candidate,
registers with SignalFSMManager, logs to SignalAuditLedger, and queues Telegram notifications.
"""
from __future__ import annotations

from typing import Any
import structlog

from app.signals.confluence import ARMED_THRESHOLD
from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.strategies.base import SignalCandidate

logger = structlog.get_logger()


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
    """Constructs SignalInstance with Version 6.0 fields."""
    watch_ttl_seconds = cand.ttl_seconds
    if fsm_init_state == "VALIDATED":
        try:
            watch_ttl_seconds = max(int(cand.ttl_seconds or 0), 1800)
        except Exception:
            watch_ttl_seconds = 1800
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
    """Registers signal in FSM, records into audit ledger, and enqueues Telegram alert."""
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
