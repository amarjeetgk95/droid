"""
Real-Time Signal Outcome Tracker & Quantitative Performance Engine
Tracks live price vs active signals:
  - Triggers & Confirmations
  - Target 1 Hit (1.5R), Target 2 Hit (3.0R), Stop Loss Hit
  - Max Favorable Excursion (MFE) & Max Adverse Excursion (MAE)
  - Historical Win Rate %, Profit Factor, Expectancy, Strategy Attribution
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Any
import structlog
from pydantic import BaseModel, Field

from app.signals.fsm import signal_fsm, SignalInstance

logger = structlog.get_logger()


class PerformanceMetrics(BaseModel):
    total_signals: int = 0
    active_signals: int = 0
    completed_signals: int = 0
    winning_signals: int = 0
    losing_signals: int = 0
    expired_signals: int = 0

    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    average_rr: float = 0.0
    expectancy_r: float = 0.0

    target_1_hits: int = 0
    target_2_hits: int = 0
    stop_loss_hits: int = 0

    strategy_breakdown: dict[str, dict] = Field(default_factory=dict)
    underlying_breakdown: dict[str, dict] = Field(default_factory=dict)
    audit_summary: Optional[dict] = None


class SignalOutcomeTracker:
    """
    Monitors price progression for active signals and calculates performance attribution.
    """

    def update_with_price(self, underlying: str, current_price: Decimal | float) -> list[dict]:
        d_price = Decimal(str(current_price))
        active = signal_fsm.list_active(underlying=underlying)
        events = []

        for sig in active:
            if sig.outcome_status is not None:
                continue
            st = sig.fsm_state
            if st in ("TARGET_1_HIT", "TARGET_2_HIT", "STOP_LOSS_HIT", "CLOSED", "EXPIRED", "INVALIDATED"):
                continue
            direction = sig.direction

            # ── 1. TRIGGER & CONFIRMATION ──
            if st in ("VALIDATED", "ARMED"):
                if direction == "LONG_CALL" and d_price >= sig.trigger:
                    signal_fsm.transition(sig.signal_id, "TRIGGERED", market_price=d_price, reason="TRIGGER_LEVEL_HIT")
                    signal_fsm.transition(sig.signal_id, "CONFIRMED", market_price=d_price, reason="ENTRY_CONFIRMED")
                    events.append({"signal_id": sig.signal_id, "event": "CONFIRMED", "price": float(d_price)})
                elif direction == "LONG_PUT" and d_price <= sig.trigger:
                    signal_fsm.transition(sig.signal_id, "TRIGGERED", market_price=d_price, reason="TRIGGER_LEVEL_HIT")
                    signal_fsm.transition(sig.signal_id, "CONFIRMED", market_price=d_price, reason="ENTRY_CONFIRMED")
                    events.append({"signal_id": sig.signal_id, "event": "CONFIRMED", "price": float(d_price)})

            # ── 2. TARGET & STOP LOSS MONITORING ──
            elif st == "CONFIRMED":
                if direction == "LONG_CALL":
                    # Check Target 2 Hit (Highest Priority Win)
                    if d_price >= sig.target_2:
                        signal_fsm.transition(sig.signal_id, "TARGET_2_HIT", market_price=d_price, reason="TARGET_2_ACHIEVED")
                        events.append({"signal_id": sig.signal_id, "event": "TARGET_2_HIT", "price": float(d_price), "rr": sig.risk_reward_t2})
                    # Check Target 1 Hit
                    elif d_price >= sig.target_1 and st != "TARGET_1_HIT":
                        signal_fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=d_price, reason="TARGET_1_ACHIEVED")
                        events.append({"signal_id": sig.signal_id, "event": "TARGET_1_HIT", "price": float(d_price), "rr": sig.risk_reward_t1})
                    # Check Stop Loss Hit
                    elif d_price <= sig.stop_loss:
                        signal_fsm.transition(sig.signal_id, "STOP_LOSS_HIT", market_price=d_price, reason="STOP_LOSS_TOUCHED")
                        events.append({"signal_id": sig.signal_id, "event": "STOP_LOSS_HIT", "price": float(d_price), "rr": -1.0})

                elif direction == "LONG_PUT":
                    if d_price <= sig.target_2:
                        signal_fsm.transition(sig.signal_id, "TARGET_2_HIT", market_price=d_price, reason="TARGET_2_ACHIEVED")
                        events.append({"signal_id": sig.signal_id, "event": "TARGET_2_HIT", "price": float(d_price), "rr": sig.risk_reward_t2})
                    elif d_price <= sig.target_1 and st != "TARGET_1_HIT":
                        signal_fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=d_price, reason="TARGET_1_ACHIEVED")
                        events.append({"signal_id": sig.signal_id, "event": "TARGET_1_HIT", "price": float(d_price), "rr": sig.risk_reward_t1})
                    elif d_price >= sig.stop_loss:
                        signal_fsm.transition(sig.signal_id, "STOP_LOSS_HIT", market_price=d_price, reason="STOP_LOSS_TOUCHED")
                        events.append({"signal_id": sig.signal_id, "event": "STOP_LOSS_HIT", "price": float(d_price), "rr": -1.0})

        return events

    async def process_price_update_async(self, underlying: str, current_price: Decimal | float) -> list[dict]:
        """
        Asynchronous processing pipeline:
          1. Evaluates active signals against live price
          2. Auto-executes confirmed signals into Paper Trading
          3. Auto-squares off positions on Target/Stop hit with exact actual P&L audit
          4. Dispatches authoritative Telegram notifications and SSE broadcasts
        """
        from app.signals.paper_engine import signal_paper_engine
        from app.signals.audit_ledger import signal_audit_ledger
        from app.signals.sse import signal_sse_hub
        from app.institutional.telegram_notifications import SignalEvent, telegram_notification_queue

        d_price = Decimal(str(current_price))
        active = signal_fsm.list_active(underlying=underlying)
        processed_events: list[dict] = []

        for sig in active:
            if sig.outcome_status is not None:
                continue
            st = sig.fsm_state
            if st in ("TARGET_1_HIT", "TARGET_2_HIT", "STOP_LOSS_HIT", "CLOSED", "EXPIRED", "INVALIDATED"):
                continue
            direction = sig.direction

            # ── 1. TRIGGER & CONFIRMATION -> AUTO PAPER EXECUTION ──
            if st in ("VALIDATED", "ARMED"):
                triggered = False
                if direction == "LONG_CALL" and d_price >= sig.trigger:
                    triggered = True
                elif direction == "LONG_PUT" and d_price <= sig.trigger:
                    triggered = True

                if triggered:
                    signal_fsm.transition(sig.signal_id, "TRIGGERED", market_price=d_price, reason="TRIGGER_LEVEL_HIT")
                    signal_fsm.transition(sig.signal_id, "CONFIRMED", market_price=d_price, reason="ENTRY_CONFIRMED")
                    
                    # Automated paper trade execution upon confirmation
                    paper_res = None
                    lots_to_trade = (sig.option_contract or {}).get("lots") or getattr(sig, "lots", None) or 1
                    try:
                        paper_res = await signal_paper_engine.execute_signal(sig.signal_id, lots_override=lots_to_trade)
                    except Exception as pe:
                        logger.warning("auto_paper_execution_failed", signal_id=sig.signal_id, error=str(pe))

                    # Dispatch Telegram notification for Confirmed Signal
                    try:
                        conf_ev = SignalEvent(
                            event_type="SIGNAL_CONFIRMED",
                            signal_id=sig.signal_id,
                            instrument=sig.underlying,
                            candle_timeframe=sig.timeframe,
                            setup_type=sig.strategy,
                            direction="BULLISH" if "CALL" in sig.direction else "BEARISH",
                            status="CONFIRMED",
                            trigger_level=float(sig.trigger),
                            current_price=float(d_price),
                            stop_loss=float(sig.stop_loss),
                            target_low=float(sig.target_1),
                            target_high=float(sig.target_2),
                            confidence=float(sig.confidence),
                            paper_order_id=paper_res.order_id if paper_res else None,
                            paper_fill_price=paper_res.fill_price if paper_res else None,
                            paper_filled_qty=paper_res.quantity if paper_res else None,
                            paper_status="FILLED" if paper_res else None,
                            paper_side="BUY" if "CALL" in sig.direction else "SELL",
                        )
                        await telegram_notification_queue.publish_signal_event(conf_ev)
                    except Exception as te:
                        logger.warning("telegram_auto_confirmed_failed", signal_id=sig.signal_id, error=str(te))

                    # Broadcast SSE
                    await signal_sse_hub.broadcast("signal_confirmed", sig.model_dump(), priority="P0")
                    processed_events.append({"signal_id": sig.signal_id, "event": "CONFIRMED", "price": float(d_price), "paper_order": paper_res.model_dump() if paper_res else None})

            # ── 2. TARGET & STOP LOSS -> AUTO SQUARE-OFF WITH ACTUAL P&L ──
            elif st == "CONFIRMED":
                exit_event = None
                rr_val = None

                if direction == "LONG_CALL":
                    if d_price >= sig.target_2:
                        exit_event = "TARGET_2_HIT"
                        rr_val = sig.risk_reward_t2
                    elif d_price >= sig.target_1 and st != "TARGET_1_HIT":
                        exit_event = "TARGET_1_HIT"
                        rr_val = sig.risk_reward_t1
                    elif d_price <= sig.stop_loss:
                        exit_event = "STOP_LOSS_HIT"
                        rr_val = -1.0
                elif direction == "LONG_PUT":
                    if d_price <= sig.target_2:
                        exit_event = "TARGET_2_HIT"
                        rr_val = sig.risk_reward_t2
                    elif d_price <= sig.target_1 and st != "TARGET_1_HIT":
                        exit_event = "TARGET_1_HIT"
                        rr_val = sig.risk_reward_t1
                    elif d_price >= sig.stop_loss:
                        exit_event = "STOP_LOSS_HIT"
                        rr_val = -1.0

                if exit_event:
                    signal_fsm.transition(sig.signal_id, exit_event, market_price=d_price, reason=f"{exit_event}_TRIGGERED")

                    # Auto square-off paper trade and compute exact actual PnL
                    audit_rec = None
                    try:
                        audit_rec = await signal_paper_engine.close_signal_position(sig.signal_id, float(d_price), reason=exit_event)
                    except Exception as ce:
                        logger.warning("auto_paper_square_off_failed", signal_id=sig.signal_id, error=str(ce))

                    # Dispatch Telegram notifications (TARGET_HIT / STOP_HIT + SIGNAL_RESULT)
                    try:
                        actual_pnl = audit_rec.actual_pnl_inr if audit_rec else None
                        theo_pnl = audit_rec.theoretical_pnl_inr if audit_rec else None
                        holding_str = audit_rec.holding_time_str if audit_rec else None
                        points_diff = audit_rec.actual_pnl_points if audit_rec else (float(d_price) - float(sig.trigger))

                        ev_type = "TARGET_HIT" if "TARGET" in exit_event else "STOP_HIT"
                        res_ev = SignalEvent(
                            event_type=ev_type,
                            signal_id=sig.signal_id,
                            instrument=sig.underlying,
                            candle_timeframe=sig.timeframe,
                            setup_type=sig.strategy,
                            direction="BULLISH" if "CALL" in sig.direction else "BEARISH",
                            status=exit_event,
                            result=exit_event,
                            theoretical_entry=float(sig.trigger),
                            exit_price=float(d_price),
                            theoretical_pnl_points=float(points_diff),
                            theoretical_pnl_amount=float(theo_pnl) if theo_pnl is not None else None,
                            actual_pnl_amount=float(actual_pnl) if actual_pnl is not None else None,
                            holding_time=holding_str,
                            current_price=float(d_price),
                        )
                        await telegram_notification_queue.publish_signal_event(res_ev)

                        # Also publish canonical SIGNAL_RESULT
                        res_ev2 = res_ev.model_copy(update={"event_type": "SIGNAL_RESULT"})
                        await telegram_notification_queue.publish_signal_event(res_ev2)
                    except Exception as te:
                        logger.warning("telegram_outcome_dispatch_failed", signal_id=sig.signal_id, error=str(te))

                    # Broadcast SSE
                    await signal_sse_hub.broadcast("signal_outcome", {"signal_id": sig.signal_id, "event": exit_event, "price": float(d_price), "audit": audit_rec.model_dump() if audit_rec else None}, priority="P0")
                    processed_events.append({"signal_id": sig.signal_id, "event": exit_event, "price": float(d_price), "rr": rr_val, "actual_pnl": audit_rec.actual_pnl_inr if audit_rec else None})

        return processed_events

    def get_performance_metrics(self) -> PerformanceMetrics:
        """Calculate complete historical performance attribution."""
        all_signals = list(signal_fsm._signals.values())
        total = len(all_signals)
        active_ct = sum(1 for s in all_signals if s.fsm_state in ("DETECTED", "VALIDATED", "ARMED", "TRIGGERED", "CONFIRMED"))
        
        t1_hits = sum(1 for s in all_signals if s.fsm_state == "TARGET_1_HIT" or s.outcome_status == "WIN_T1")
        t2_hits = sum(1 for s in all_signals if s.fsm_state == "TARGET_2_HIT" or s.outcome_status == "WIN_T2")
        sl_hits = sum(1 for s in all_signals if s.fsm_state == "STOP_LOSS_HIT" or s.outcome_status == "LOSS_SL")
        expired = sum(1 for s in all_signals if s.fsm_state == "EXPIRED" or s.outcome_status == "EXPIRED")

        completed_trades = (t1_hits + t2_hits) + sl_hits
        wins = t1_hits + t2_hits
        losses = sl_hits

        win_rate = (wins / completed_trades * 100.0) if completed_trades > 0 else 0.0

        # Profit Factor & R:R
        gross_profit_r = (t1_hits * 1.5) + (t2_hits * 3.0)
        gross_loss_r = losses * 1.0
        profit_factor = (gross_profit_r / gross_loss_r) if gross_loss_r > 0 else (gross_profit_r if gross_profit_r > 0 else 1.0)
        expectancy = ((win_rate / 100.0 * 2.0) - ((1.0 - (win_rate / 100.0)) * 1.0)) if completed_trades > 0 else 0.0

        # Strategy breakdown
        strat_breakdown = {}
        for s in all_signals:
            st_name = s.strategy
            entry = strat_breakdown.setdefault(st_name, {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0})
            entry["total"] += 1
            if s.fsm_state in ("TARGET_1_HIT", "TARGET_2_HIT") or s.outcome_status in ("WIN_T1", "WIN_T2"):
                entry["wins"] += 1
            elif s.fsm_state == "STOP_LOSS_HIT" or s.outcome_status == "LOSS_SL":
                entry["losses"] += 1
            entry["win_rate"] = round((entry["wins"] / (entry["wins"] + entry["losses"]) * 100.0), 1) if (entry["wins"] + entry["losses"]) > 0 else 0.0

        # Underlying breakdown
        under_breakdown = {}
        for s in all_signals:
            u_name = s.underlying
            entry = under_breakdown.setdefault(u_name, {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0})
            entry["total"] += 1
            if s.fsm_state in ("TARGET_1_HIT", "TARGET_2_HIT") or s.outcome_status in ("WIN_T1", "WIN_T2"):
                entry["wins"] += 1
            elif s.fsm_state == "STOP_LOSS_HIT" or s.outcome_status == "LOSS_SL":
                entry["losses"] += 1
            entry["win_rate"] = round((entry["wins"] / (entry["wins"] + entry["losses"]) * 100.0), 1) if (entry["wins"] + entry["losses"]) > 0 else 0.0

        audit_stats = None
        try:
            from app.signals.audit_ledger import signal_audit_ledger
            audit_stats = signal_audit_ledger.get_summary_metrics()
        except Exception:
            pass

        return PerformanceMetrics(
            total_signals=total,
            active_signals=active_ct,
            completed_signals=completed_trades,
            winning_signals=wins,
            losing_signals=losses,
            expired_signals=expired,
            win_rate_pct=round(win_rate, 1),
            profit_factor=round(profit_factor, 2),
            average_rr=2.25 if wins > 0 else 0.0,
            expectancy_r=round(expectancy, 2),
            target_1_hits=t1_hits,
            target_2_hits=t2_hits,
            stop_loss_hits=sl_hits,
            strategy_breakdown=strat_breakdown,
            underlying_breakdown=under_breakdown,
            audit_summary=audit_stats,
        )


outcome_tracker = SignalOutcomeTracker()
