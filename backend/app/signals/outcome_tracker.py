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
from typing import Optional
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
    time_stop_hits: int = 0
    runner_time_stop_hits: int = 0

    strategy_breakdown: dict[str, dict] = Field(default_factory=dict)
    underlying_breakdown: dict[str, dict] = Field(default_factory=dict)
    scalp_summary: dict = Field(default_factory=dict)
    intraday_summary: dict = Field(default_factory=dict)
    audit_summary: Optional[dict] = None


class SignalOutcomeTracker:
    """
    Monitors price progression for active signals and calculates performance attribution.
    Enforces Version 6.0:
      - Ordered priority execution via signal_fsm.evaluate_tick()
      - Breakeven Ratchet (+0.8R)
      - Staged Exits (T1 50% booked + Runner to T2)
      - Independent Two-Clock time-stop handling
      - Fill Reconciler & Statutory cost deductions
    """

    def update_with_price(
        self,
        underlying: str,
        current_price: Decimal | float,
        now_ms: Optional[int] = None,
        allow_closed_market: bool = False,
    ) -> list[dict]:
        from app.services.calendar_service import calendar_service
        if not allow_closed_market and not calendar_service.can_trade_now().allowed:
            return []

        try:
            d_price = Decimal(str(current_price))
        except Exception:
            return []

        if d_price <= Decimal("0"):
            return []

        ts_now = now_ms or int(__import__("time").time() * 1000)
        active = signal_fsm.list_active(underlying=underlying)
        events = []

        for sig in active:
            if sig.outcome_status is not None:
                continue
            st = sig.fsm_state
            if st in ("TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT", "CLOSED", "EXPIRED", "INVALIDATED"):
                continue
            direction = sig.direction

            # ── 1. TRIGGER & CONFIRMATION ──
            if st in ("VALIDATED", "ARMED"):
                triggered = False
                if direction == "LONG_CALL" and d_price >= sig.trigger:
                    triggered = True
                elif direction == "LONG_PUT" and d_price <= sig.trigger:
                    triggered = True

                if triggered:
                    signal_fsm.transition(sig.signal_id, "TRIGGERED", market_price=d_price, reason="TRIGGER_LEVEL_HIT")
                    signal_fsm.transition(sig.signal_id, "CONFIRMED", market_price=d_price, reason="ENTRY_CONFIRMED")
                    events.append({"signal_id": sig.signal_id, "event": "CONFIRMED", "price": float(d_price)})

            # ── 2. ORDERED EVALUATION FOR CONFIRMED & TARGET_1_HIT (RUNNER) ──
            elif st in ("CONFIRMED", "TARGET_1_HIT"):
                res = signal_fsm.evaluate_tick(sig, d_price, ts_now)
                if res == "BE_ACTIVATED":
                    signal_fsm.ratchet_breakeven(sig.signal_id, d_price)
                    events.append({"signal_id": sig.signal_id, "event": "BREAKEVEN_RATCHET", "price": float(d_price)})
                elif res:
                    signal_fsm.transition(sig.signal_id, res, market_price=d_price, reason=f"{res}_TRIGGERED")
                    events.append({
                        "signal_id": sig.signal_id,
                        "event": res,
                        "price": float(d_price),
                        "rr": float(sig.realized_rr or 0.0),
                    })

        return events

    async def process_price_update_async(
        self,
        underlying: str,
        current_price: Decimal | float,
        now_ms: Optional[int] = None,
        allow_closed_market: bool = False,
    ) -> list[dict]:
        """
        Asynchronous processing pipeline:
          1. Evaluates active signals against live price using deterministic evaluate_tick priority
          2. Auto-executes confirmed signals into Paper Trading & registers entry fill
          3. Staged T1 exit: 50% booked, SL ratchets to cost, runner clock starts
          4. Final exit (T2, SL, Time-Stop, Runner Time-Stop) with exact actual option P&L
          5. Dispatches Telegram notifications and SSE broadcasts
        """
        from app.services.calendar_service import calendar_service
        if not allow_closed_market and not calendar_service.can_trade_now().allowed:
            return []

        try:
            d_price = Decimal(str(current_price))
        except Exception:
            return []

        if d_price <= Decimal("0"):
            return []

        from app.signals.paper_engine import signal_paper_engine
        from app.signals.audit_ledger import signal_audit_ledger
        from app.signals.sse import signal_sse_hub
        from app.institutional.telegram_notifications import SignalEvent, telegram_notification_queue
        from app.signals.fill_reconciler import option_fill_reconciler

        ts_now = now_ms or int(__import__("time").time() * 1000)
        active = signal_fsm.list_active(underlying=underlying)
        processed_events: list[dict] = []

        for sig in active:
            if sig.outcome_status is not None:
                continue
            st = sig.fsm_state
            if st in ("TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT", "CLOSED", "EXPIRED", "INVALIDATED"):
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
                    # First transition to TRIGGERED
                    signal_fsm.transition(sig.signal_id, "TRIGGERED", market_price=d_price, reason="TRIGGER_LEVEL_HIT")

                    # Attempt paper execution
                    paper_res = None
                    lots_to_trade = (sig.option_contract or {}).get("lots") or getattr(sig, "lots", None) or 1
                    try:
                        paper_res = await signal_paper_engine.execute_signal(
                            sig.signal_id,
                            lots_override=lots_to_trade,
                            allow_closed_market=allow_closed_market,
                        )
                    except Exception as pe:
                        logger.warning("auto_paper_execution_failed", signal_id=sig.signal_id, error=str(pe))

                    # Transition to CONFIRMED only on successful, non-rejected paper execution
                    if paper_res and paper_res.success and paper_res.status != "REJECTED":
                        signal_fsm.transition(sig.signal_id, "CONFIRMED", market_price=d_price, reason="ENTRY_CONFIRMED")
                        opt_rec = option_fill_reconciler.reconcile_entry(
                            sig=sig,
                            fill_price=paper_res.fill_price,
                            quantity=paper_res.quantity,
                            lot_size=int((sig.option_contract or {}).get("lot_size", 75)),
                        )

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
                                paper_order_id=paper_res.order_id,
                                paper_fill_price=paper_res.fill_price,
                                paper_filled_qty=paper_res.quantity,
                                paper_status="FILLED",
                                paper_side="BUY" if "CALL" in sig.direction else "SELL",
                            )
                            await telegram_notification_queue.publish_signal_event(conf_ev)
                        except Exception as te:
                            logger.warning("telegram_auto_confirmed_failed", signal_id=sig.signal_id, error=str(te))

                        # Broadcast SSE
                        try:
                            await signal_sse_hub.broadcast("signal_confirmed", sig.model_dump(), priority="P0")
                        except Exception as se:
                            logger.warning("sse_confirmed_broadcast_failed", signal_id=sig.signal_id, error=str(se))

                        processed_events.append({
                            "signal_id": sig.signal_id,
                            "event": "CONFIRMED",
                            "price": float(d_price),
                            "paper_order": paper_res.model_dump(),
                        })
                    else:
                        # Do NOT leave the signal stranded in CONFIRMED. Transition to INVALIDATED.
                        fail_msg = paper_res.message if paper_res and paper_res.message else "unknown"
                        signal_fsm.transition(
                            sig.signal_id,
                            "INVALIDATED",
                            market_price=d_price,
                            reason=f"EXECUTION_FAILED: {fail_msg}",
                        )
                        logger.warning(
                            "signal_paper_execution_blocked",
                            signal_id=sig.signal_id,
                            reason=fail_msg,
                        )
                        processed_events.append({
                            "signal_id": sig.signal_id,
                            "event": "INVALIDATED",
                            "price": float(d_price),
                            "reason": f"EXECUTION_FAILED: {fail_msg}",
                        })

            # ── 2. ORDERED TICK EVALUATION (CONFIRMED & TARGET_1_HIT RUNNERS) ──
            elif st in ("CONFIRMED", "TARGET_1_HIT"):
                eval_action = signal_fsm.evaluate_tick(sig, d_price, ts_now)
                if not eval_action:
                    continue

                opt = sig.option_contract or {}
                strike = float(opt.get("strike", float(sig.trigger)))
                opt_type = opt.get("option_type", "CE" if "CALL" in sig.direction else "PE")
                est_opt_price = option_fill_reconciler.estimate_option_premium(float(d_price), strike, opt_type)

                if eval_action == "BE_ACTIVATED":
                    ratcheted = signal_fsm.ratchet_breakeven(sig.signal_id, d_price)
                    if ratcheted:
                        await signal_sse_hub.broadcast(
                            "signal_breakeven",
                            {"signal_id": sig.signal_id, "new_stop_loss": float(sig.current_stop_loss or 0.0)},
                            priority="P1",
                        )
                        processed_events.append({"signal_id": sig.signal_id, "event": "BREAKEVEN_RATCHET", "price": float(d_price)})

                elif eval_action == "TARGET_1_HIT" and st == "CONFIRMED":
                    # Transition FSM to TARGET_1_HIT (Runner Mode begins)
                    signal_fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=d_price, reason="TARGET_1_ACHIEVED")

                    # Reconcile T1 Staged Exit (50% position booked)
                    recon = option_fill_reconciler.reconcile_t1_exit(sig, est_opt_price, ts_now)

                    # Partial square-off in paper engine
                    try:
                        await signal_paper_engine.close_signal_position(
                            sig.signal_id,
                            float(d_price),
                            reason="TARGET_1_HIT",
                            quantity_to_close=recon.t1_qty,
                        )
                    except Exception as pe:
                        logger.warning("paper_t1_close_failed", signal_id=sig.signal_id, error=str(pe))

                    # Dispatch Telegram for T1 Staged Exit
                    try:
                        t1_ev = SignalEvent(
                            event_type="TARGET_HIT",
                            signal_id=sig.signal_id,
                            instrument=sig.underlying,
                            candle_timeframe=sig.timeframe,
                            setup_type=sig.strategy,
                            direction="BULLISH" if "CALL" in sig.direction else "BEARISH",
                            status="TARGET_1_HIT",
                            result="TARGET_1_HIT",
                            theoretical_entry=float(sig.trigger),
                            exit_price=float(d_price),
                            actual_pnl_amount=recon.t1_realized_pnl,
                            current_price=float(d_price),
                        )
                        await telegram_notification_queue.publish_signal_event(t1_ev)
                    except Exception as te:
                        logger.warning("telegram_t1_failed", signal_id=sig.signal_id, error=str(te))

                    await signal_sse_hub.broadcast(
                        "signal_staged_exit",
                        {
                            "signal_id": sig.signal_id,
                            "event": "TARGET_1_HIT",
                            "closed_qty": recon.t1_qty,
                            "remaining_qty": recon.remaining_qty,
                            "t1_pnl": recon.t1_realized_pnl,
                            "runner_ttl_seconds": sig.runner_ttl_seconds or 300,
                        },
                        priority="P0",
                    )
                    processed_events.append({
                        "signal_id": sig.signal_id,
                        "event": "TARGET_1_HIT",
                        "price": float(d_price),
                        "t1_pnl": recon.t1_realized_pnl,
                        "remaining_qty": recon.remaining_qty,
                    })

                elif eval_action in ("TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT"):
                    # Final Exit
                    signal_fsm.transition(sig.signal_id, eval_action, market_price=d_price, reason=f"{eval_action}_TRIGGERED")

                    # Reconcile final exit and close residual quantity
                    recon = option_fill_reconciler.reconcile_final_exit(sig, est_opt_price, exit_reason=eval_action, exit_time_ms=ts_now)

                    # Full square-off in paper engine
                    try:
                        await signal_paper_engine.close_signal_position(
                            sig.signal_id,
                            float(d_price),
                            reason=eval_action,
                        )
                    except Exception as pe:
                        logger.warning("paper_final_close_failed", signal_id=sig.signal_id, error=str(pe))

                    # Ensure authoritative square-off is recorded in Signal Audit Ledger
                    try:
                        audit_rec = signal_audit_ledger.get(sig.signal_id)
                        if not audit_rec:
                            signal_audit_ledger.record_signal_created(
                                signal_id=sig.signal_id,
                                underlying=sig.underlying,
                                strategy=sig.strategy,
                                direction=sig.direction,
                                timeframe=sig.timeframe,
                                spot_price=float(sig.spot_price),
                                trigger=float(sig.trigger),
                                stop_loss=float(sig.stop_loss),
                                target_1=float(sig.target_1),
                                target_2=float(sig.target_2),
                                confidence=float(sig.confidence),
                                option_contract=sig.option_contract,
                            )
                        sq_rec = signal_audit_ledger.record_square_off(
                            signal_id=sig.signal_id,
                            exit_price=float(d_price),
                            exit_reason=eval_action,
                            exit_time_ms=ts_now,
                        )
                        if sq_rec and recon:
                            sq_rec.actual_pnl_inr = recon.net_realized_pnl_inr
                            sq_rec.total_pnl_inr = recon.net_realized_pnl_inr
                            sq_rec.is_winner = recon.net_realized_pnl_inr > 0
                            sq_rec.status = "WON" if recon.net_realized_pnl_inr > 0 else ("LOST" if recon.net_realized_pnl_inr < 0 else "CLOSED")
                            signal_audit_ledger._schedule_persist(sq_rec)
                    except Exception as le:
                        logger.warning("audit_square_off_failed", signal_id=sig.signal_id, error=str(le))

                    # Dispatch Telegram notifications
                    try:
                        ev_type = "TARGET_HIT" if "TARGET" in eval_action else ("STOP_HIT" if "STOP" in eval_action else "TIME_STOP")
                        res_ev = SignalEvent(
                            event_type=ev_type,
                            signal_id=sig.signal_id,
                            instrument=sig.underlying,
                            candle_timeframe=sig.timeframe,
                            setup_type=sig.strategy,
                            direction="BULLISH" if "CALL" in sig.direction else "BEARISH",
                            status=eval_action,
                            result=eval_action,
                            theoretical_entry=float(sig.trigger),
                            exit_price=float(d_price),
                            actual_pnl_amount=recon.net_realized_pnl_inr,
                            current_price=float(d_price),
                        )
                        await telegram_notification_queue.publish_signal_event(res_ev)
                        res_ev2 = res_ev.model_copy(update={"event_type": "SIGNAL_RESULT"})
                        await telegram_notification_queue.publish_signal_event(res_ev2)
                    except Exception as te:
                        logger.warning("telegram_final_failed", signal_id=sig.signal_id, error=str(te))

                    # Broadcast SSE
                    await signal_sse_hub.broadcast(
                        "signal_outcome",
                        {
                            "signal_id": sig.signal_id,
                            "event": eval_action,
                            "price": float(d_price),
                            "reconciliation": recon.model_dump(),
                        },
                        priority="P0",
                    )
                    processed_events.append({
                        "signal_id": sig.signal_id,
                        "event": eval_action,
                        "price": float(d_price),
                        "actual_pnl": recon.net_realized_pnl_inr,
                        "realized_rr": recon.realized_rr,
                    })

        return processed_events

    def get_performance_metrics(self) -> PerformanceMetrics:
        """Calculate complete historical performance attribution split across Desks (§31)."""
        all_signals = list(signal_fsm._signals.values())
        total = len(all_signals)
        active_ct = sum(1 for s in all_signals if s.fsm_state in ("DETECTED", "VALIDATED", "ARMED", "TRIGGERED", "CONFIRMED", "TARGET_1_HIT"))

        t1_hits = sum(1 for s in all_signals if s.fsm_state == "TARGET_1_HIT" or s.outcome_status == "WIN_T1")
        t2_hits = sum(1 for s in all_signals if s.fsm_state == "TARGET_2_HIT" or s.outcome_status == "WIN_T2")
        sl_hits = sum(1 for s in all_signals if s.fsm_state == "STOP_LOSS_HIT" or s.outcome_status == "LOSS_SL")
        time_stops = sum(1 for s in all_signals if s.fsm_state in ("TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT") or s.outcome_status in ("TIME_STOP", "RUNNER_TIME_STOP"))
        expired = sum(1 for s in all_signals if s.fsm_state == "EXPIRED" or s.outcome_status == "EXPIRED")

        completed_trades = (t1_hits + t2_hits) + sl_hits + time_stops
        wins = t1_hits + t2_hits
        losses = sl_hits + time_stops

        win_rate = (wins / completed_trades * 100.0) if completed_trades > 0 else 0.0

        # Profit Factor & R:R
        gross_profit_r = (t1_hits * 1.5) + (t2_hits * 3.0)
        gross_loss_r = losses * 1.0
        profit_factor = (gross_profit_r / gross_loss_r) if gross_loss_r > 0 else (gross_profit_r if gross_profit_r > 0 else 1.0)
        expectancy = ((win_rate / 100.0 * 2.0) - ((1.0 - (win_rate / 100.0)) * 1.0)) if completed_trades > 0 else 0.0

        # Desk breakdowns
        def _calc_desk(sub_list: list[SignalInstance]) -> dict:
            sub_total = len(sub_list)
            sub_w = sum(1 for s in sub_list if s.fsm_state in ("TARGET_1_HIT", "TARGET_2_HIT") or s.outcome_status in ("WIN_T1", "WIN_T2"))
            sub_l = sum(1 for s in sub_list if s.fsm_state in ("STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT") or s.outcome_status in ("LOSS_SL", "TIME_STOP", "RUNNER_TIME_STOP"))
            sub_comp = sub_w + sub_l
            sub_wr = round((sub_w / sub_comp * 100.0), 1) if sub_comp > 0 else 0.0
            return {"total": sub_total, "completed": sub_comp, "wins": sub_w, "losses": sub_l, "win_rate_pct": sub_wr}

        scalp_sigs = [s for s in all_signals if getattr(s, "is_scalp", False)]
        intraday_sigs = [s for s in all_signals if not getattr(s, "is_scalp", False)]

        # Strategy breakdown
        strat_breakdown = {}
        for s in all_signals:
            st_name = s.strategy
            entry = strat_breakdown.setdefault(st_name, {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0})
            entry["total"] += 1
            if s.fsm_state in ("TARGET_1_HIT", "TARGET_2_HIT") or s.outcome_status in ("WIN_T1", "WIN_T2"):
                entry["wins"] += 1
            elif s.fsm_state in ("STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT") or s.outcome_status in ("LOSS_SL", "TIME_STOP", "RUNNER_TIME_STOP"):
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
            elif s.fsm_state in ("STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT") or s.outcome_status in ("LOSS_SL", "TIME_STOP", "RUNNER_TIME_STOP"):
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
            time_stop_hits=time_stops,
            runner_time_stop_hits=time_stops,
            strategy_breakdown=strat_breakdown,
            underlying_breakdown=under_breakdown,
            scalp_summary=_calc_desk(scalp_sigs),
            intraday_summary=_calc_desk(intraday_sigs),
            audit_summary=audit_stats,
        )


outcome_tracker = SignalOutcomeTracker()

