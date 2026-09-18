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

from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.outcome_metrics import (
    OutcomeMetricsMixin,
    PerformanceMetrics as PerformanceMetrics,
)

logger = structlog.get_logger()


class SignalOutcomeTracker(OutcomeMetricsMixin):
    """
    Monitors price progression for active signals and calculates performance attribution.
    Enforces Version 6.0:
      - Ordered priority execution via signal_fsm.evaluate_tick()
      - Breakeven Ratchet (+0.8R)
      - Staged Exits (T1 50% booked + Runner to T2)
      - Independent Two-Clock time-stop handling
      - Fill Reconciler & Statutory cost deductions
    """

    def __init__(self):
        import asyncio
        import time as _t
        self._signal_locks: dict[str, asyncio.Lock] = {}
        # Idempotency: (signal_id, eval_action, tick_ts_bucket) -> monotonic expiry.
        self._processed: dict[str, float] = {}
        self._lock_ttl_s: float = 60.0
        self._last_lock_sweep_monotonic: float = _t.monotonic()

    def _get_signal_lock(self, signal_id: str):
        import asyncio
        import time as _t
        # TTL sweep for lock map + idempotency map.
        now_m = _t.monotonic()
        if now_m - self._last_lock_sweep_monotonic > 30.0:
            self._last_lock_sweep_monotonic = now_m
            try:
                expired = [k for k, exp in self._processed.items() if exp < now_m]
                for k in expired:
                    self._processed.pop(k, None)
            except Exception:
                pass
        if signal_id not in self._signal_locks:
            if len(self._signal_locks) > 500:
                self._signal_locks.clear()
            self._signal_locks[signal_id] = asyncio.Lock()
        return self._signal_locks[signal_id]

    def _tick_idempotent_key(self, signal_id: str, eval_action: str, tick_ts: int | None) -> str:
        # Millisecond precision: identical ticks collapse; distinct same-second ticks do not.
        bucket = int(tick_ts or 0)
        return f"{signal_id}:{eval_action}:{bucket}"

    def _check_and_mark_tick(self, signal_id: str, eval_action: str, tick_ts: int | None) -> bool:
        """True when duplicate (already processed), else marks and returns False."""
        import time as _t
        k = self._tick_idempotent_key(signal_id, eval_action, tick_ts)
        now_m = _t.monotonic()
        exp = self._processed.get(k)
        if exp is not None and exp > now_m:
            return True
        self._processed[k] = now_m + self._lock_ttl_s
        return False

    async def _resolve_exit_mark(self, sig: SignalInstance) -> Optional[float]:
        """Real broker premium for this signal's contract, else None.

        FAIL CLOSED: exits are priced from a FYERS quote for the exact contract.
        There is deliberately no Black-76 fallback computed from the index spot —
        a model number is not an exit, and booking one is how cross-domain P&L
        got fabricated in the first place.
        """
        sym = str((sig.option_contract or {}).get("broker_symbol") or "").strip()
        if not sym:
            return None
        from app.signals.option_marks import option_mark_registry, option_mark_service

        mark = option_mark_registry.get_usable(sym, allow_model=False)
        if mark is None or mark.price is None:
            try:
                await option_mark_service.refresh_and_register([sym])
            except Exception as me:
                logger.debug("exit_mark_fetch_failed", signal_id=sig.signal_id, error=str(me)[:150])
            mark = option_mark_registry.get_usable(sym, allow_model=False)
        if mark is None or mark.price is None:
            return None
        return float(mark.price)

    def update_with_price(
        self,
        underlying: str,
        current_price: Decimal | float,
        now_ms: Optional[int] = None,
        allow_closed_market: bool = False,
    ) -> list[dict]:
        """DEPRECATED bare-sync path — use process_price_update_async for CONFIRMED/T1.

        Retained for legacy callers with a deprecation warning; CONFIRMED/T1
        handling here is preview-equivalent and callers should migrate to the
        async pipeline (single atomic TRIGGERED+CONFIRMED with paper receipt).
        Idempotent via (signal_id, eval_action, tick_ts).
        """
        import warnings
        warnings.warn(
            "update_with_price is deprecated for CONFIRMED/T1; use process_price_update_async",
            DeprecationWarning, stacklevel=2,
        )
        logger.warning("outcome_tracker_sync_deprecated", underlying=underlying)
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
            if sig.outcome_status is not None and sig.fsm_state != "TARGET_1_HIT":
                continue
            st = sig.fsm_state
            if st in ("TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT", "CLOSED", "EXPIRED", "INVALIDATED"):
                continue
            direction = sig.direction

            # ── 1. TRIGGER & CONFIRMATION (legacy: two-step; async path is atomic) ──
            if st in ("VALIDATED", "ARMED"):
                triggered = False
                if direction == "LONG_CALL" and d_price >= sig.trigger:
                    triggered = True
                elif direction == "LONG_PUT" and d_price <= sig.trigger:
                    triggered = True

                if triggered:
                    _key = self._tick_idempotent_key(sig.signal_id, "TRIGGERED", ts_now)
                    import time as _t
                    if self._check_and_mark_tick(sig.signal_id, "TRIGGERED", ts_now):
                        continue
                    signal_fsm.transition(sig.signal_id, "TRIGGERED", market_price=d_price, reason="TRIGGER_LEVEL_HIT",
                                          guard_snapshot={"trigger_proof": True, "trigger_price": format(d_price, "f")})
                    # Single atomic TRIGGERED+CONFIRMED intent: CONFIRMED requires
                    # paper receipt in async path; sync legacy path records preview
                    # CONFIRMED without receipt (deprecated).
                    signal_fsm.transition(sig.signal_id, "CONFIRMED", market_price=d_price, reason="ENTRY_CONFIRMED",
                                          guard_snapshot={"trigger_proof": True, "paper_receipt": "SYNC_LEGACY"})
                    events.append({"signal_id": sig.signal_id, "event": "CONFIRMED", "price": float(d_price),
                                   "deprecated_sync": True})

            # ── 2. ORDERED EVALUATION FOR CONFIRMED & TARGET_1_HIT (RUNNER) ──
            elif st in ("CONFIRMED", "TARGET_1_HIT"):
                if self._check_and_mark_tick(sig.signal_id, st, ts_now):
                    continue
                # Fully-booked runner: staged accounting booked the entire
                # position at T1 (intended>0, remaining 0 — single-lot fills).
                # Nothing is left to stop out — settle quietly instead of
                # firing a phantom STOP that would overwrite the settled T1
                # reason/P&L downstream. Runners with untracked quantities
                # (intended 0, e.g. sync-only flows) keep legacy evaluation.
                if st == "TARGET_1_HIT" and sig.t1_hit:
                    try:
                        _intended = Decimal(str(sig.intended_qty)) if sig.intended_qty is not None else Decimal("0")
                        _rem = Decimal(str(sig.remaining_qty)) if sig.remaining_qty is not None else Decimal("0")
                    except Exception:
                        _intended, _rem = Decimal("0"), Decimal("1")
                    if _intended > 0 and _rem <= 0:
                        signal_fsm.transition(sig.signal_id, "CLOSED", market_price=d_price, reason="T1_FULLY_BOOKED_NO_RUNNER")
                        events.append({"signal_id": sig.signal_id, "event": "CLOSED", "price": float(d_price)})
                        continue
                res = signal_fsm.evaluate_tick(sig, d_price, ts_now)
                if res == "BE_ACTIVATED":
                    signal_fsm.ratchet_breakeven(sig.signal_id, d_price)
                    events.append({"signal_id": sig.signal_id, "event": "BREAKEVEN_RATCHET", "price": float(d_price)})
                elif res:
                    if self._check_and_mark_tick(sig.signal_id, res, ts_now):
                        continue
                    signal_fsm.transition(sig.signal_id, res, market_price=d_price, reason=f"{res}_TRIGGERED")
                    events.append({
                        "signal_id": sig.signal_id,
                        "event": res,
                        "price": float(d_price),
                        "rr": float(sig.realized_rr or 0.0),
                    })

        return events

    def preview_with_price(
        self,
        underlying: str,
        current_price: Decimal | float,
        now_ms: Optional[int] = None,
        allow_closed_market: bool = False,
    ) -> list[dict]:
        """Preview-only evaluation: no FSM mutation, returns would-be events."""
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
        previews = []
        for sig in active:
            st = sig.fsm_state
            if st in ("TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT", "CLOSED", "EXPIRED", "INVALIDATED"):
                continue
            if st in ("VALIDATED", "ARMED"):
                trig = (sig.direction == "LONG_CALL" and d_price >= sig.trigger) or \
                       (sig.direction == "LONG_PUT" and d_price <= sig.trigger)
                if trig:
                    previews.append({"signal_id": sig.signal_id, "event": "CONFIRMED", "price": float(d_price), "preview": True})
            elif st in ("CONFIRMED", "TARGET_1_HIT"):
                res = signal_fsm.evaluate_tick(sig, d_price, ts_now)
                if res:
                    previews.append({"signal_id": sig.signal_id, "event": res, "price": float(d_price), "preview": True})
        return previews

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

        from app.signals.paper_engine import SignalPaperExecutionResult, signal_paper_engine
        from app.signals.audit_ledger import signal_audit_ledger
        from app.signals.sse import signal_sse_hub
        from app.institutional.telegram_notifications import SignalEvent, telegram_notification_queue
        from app.signals.fill_reconciler import option_fill_reconciler

        ts_now = now_ms or int(__import__("time").time() * 1000)
        # include_terminal=True: list_active() runs sweep_expired() internally,
        # which can pre-emptively convert a CONFIRMED trade / runner to a terminal
        # state on THIS call (RUNNER_TTL_EXCEEDED / TIME_STOP_EXCEEDED). With the
        # default filter those signals are dropped from the result and the
        # reconciled exit below never runs — the residual quantity ghosts in the
        # paper portfolio. Terminal signals are still skipped in the loop head
        # unless they need sweep-pre-emption recovery.
        active = signal_fsm.list_active(underlying=underlying, include_terminal=True)
        processed_events: list[dict] = []

        for sig in active:
            st = sig.fsm_state
            # Sweep pre-emption recovery: list_active() runs sweep_expired() BEFORE
            # evaluate_tick sees this tick, so a CONFIRMED trade or runner whose
            # time-stop elapsed is force-transitioned to a terminal state WITHOUT
            # the reconciled exit (paper square-off + audit P&L booking). If
            # residual quantity is still open, settle it here instead of skipping,
            # otherwise the remainder ghosts in the paper portfolio with frozen MTM.
            sweep_pre_empted = (
                st in ("RUNNER_TIME_STOP_HIT", "TIME_STOP_HIT")
                and bool(getattr(sig, "paper_order", None))
                and sig.remaining_qty is not None
                and sig.remaining_qty > 0
            )
            # Runners (TARGET_1_HIT / WIN_T1) must keep evaluating until a terminal
            # state; only settled outcomes skip the tick.
            if sig.outcome_status is not None and st != "TARGET_1_HIT" and not sweep_pre_empted:
                continue
            eval_action: Optional[str] = None
            if st in ("TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT", "CLOSED", "EXPIRED", "INVALIDATED"):
                if not sweep_pre_empted:
                    continue
                eval_action = st
            direction = sig.direction

            # ── 1. TRIGGER & CONFIRMATION -> AUTO PAPER EXECUTION ──
            if st in ("VALIDATED", "ARMED"):
                triggered = False
                if direction == "LONG_CALL" and d_price >= sig.trigger:
                    triggered = True
                elif direction == "LONG_PUT" and d_price <= sig.trigger:
                    triggered = True

                if triggered:
                    # Idempotent (signal_id, eval_action, tick_ts): collapse retries.
                    if self._check_and_mark_tick(sig.signal_id, "TRIGGERED", ts_now):
                        continue
                    # First transition to TRIGGERED (atomic part 1/2)
                    ok, trans_err = signal_fsm.transition(sig.signal_id, "TRIGGERED", market_price=d_price, reason="TRIGGER_LEVEL_HIT",
                                                          guard_snapshot={"trigger_proof": True, "trigger_price": format(d_price, "f")})
                    if not ok:
                        logger.warning("fsm_transition_to_triggered_failed", signal_id=sig.signal_id, error=trans_err)
                        if trans_err == "FNO_DATA_DEGRADED_CANNOT_ARM":
                            signal_fsm.transition(sig.signal_id, "INVALIDATED", market_price=d_price, reason=trans_err)
                        continue

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

                    # Single atomic TRIGGERED+CONFIRMED with paper receipt:
                    # CONFIRMED only on successful, non-rejected paper execution,
                    # carrying trigger proof + receipt in guard_snapshot.
                    if paper_res and paper_res.success and paper_res.status != "REJECTED":
                        if self._check_and_mark_tick(sig.signal_id, "CONFIRMED", ts_now):
                            continue
                        signal_fsm.transition(sig.signal_id, "CONFIRMED", market_price=d_price, reason="ENTRY_CONFIRMED",
                                              guard_snapshot={"trigger_proof": True,
                                                              "paper_receipt": getattr(paper_res, "order_id", ""),
                                                              "fill_price": str(getattr(paper_res, "fill_price", ""))})
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
                                # Long options always BUY the contract (LONG_CALL
                                # and LONG_PUT alike); spot SHORT/SELL must never
                                # leak into the execution-side label.
                                paper_side="BUY",
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
            # (also entered for sweep-pre-empted terminal states carrying an
            # eval_action — see recovery comment at the top of the loop)
            elif st in ("CONFIRMED", "TARGET_1_HIT") or eval_action is not None:
                # Fully-booked runner (see sync path above): single-lot T1
                # booked everything; settle to CLOSED instead of a phantom STOP.
                if st == "TARGET_1_HIT" and sig.t1_hit:
                    try:
                        _intended = Decimal(str(sig.intended_qty)) if sig.intended_qty is not None else Decimal("0")
                        _rem = Decimal(str(sig.remaining_qty)) if sig.remaining_qty is not None else Decimal("0")
                    except Exception:
                        _intended, _rem = Decimal("0"), Decimal("1")
                    if _intended > 0 and _rem <= 0:
                        signal_fsm.transition(sig.signal_id, "CLOSED", market_price=d_price, reason="T1_FULLY_BOOKED_NO_RUNNER")
                        processed_events.append({"signal_id": sig.signal_id, "event": "CLOSED", "price": float(d_price)})
                        continue
                if eval_action is None:
                    eval_action = signal_fsm.evaluate_tick(sig, d_price, ts_now)
                if not eval_action:
                    continue
                # Idempotent per (signal_id, eval_action, tick_ts).
                if self._check_and_mark_tick(sig.signal_id, str(eval_action), ts_now):
                    continue

                # Real exit premium for this exact contract, or None (fail closed).
                exit_mark: Optional[float] = await self._resolve_exit_mark(sig)

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

                    # FAIL CLOSED: a staged exit books real P&L, so it needs a real
                    # premium. With no broker mark the runner simply stays open and
                    # settles when a quote returns (or at EOD) — never at a
                    # Black-76 price derived from the index spot.
                    if exit_mark is None:
                        logger.warning(
                            "t1_exit_mark_unavailable_deferred",
                            signal_id=sig.signal_id,
                            broker_symbol=(sig.option_contract or {}).get("broker_symbol"),
                        )
                        processed_events.append({
                            "signal_id": sig.signal_id,
                            "event": "TARGET_1_HIT",
                            "price": float(d_price),
                            "t1_pnl": None,
                            "settlement": "DEFERRED_NO_CHAIN_MARK",
                        })
                        continue

                    # Reconcile T1 Staged Exit (50% position booked)
                    recon = option_fill_reconciler.reconcile_t1_exit(sig, exit_mark, ts_now)

                    # Partial square-off in paper engine
                    try:
                        await signal_paper_engine.close_signal_position(
                            sig.signal_id,
                            float(exit_mark),
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
                    # ── SETTLE FIRST, THEN WRITE THE TERMINAL STATE (phase 2b-1) ──
                    # The paper position is squared off BEFORE the terminal FSM
                    # state exists. A rejected/unfilled exit keeps the signal in
                    # its pre-close state so the next tick retries; a terminal
                    # signal with an open position is structurally impossible.
                    # FAIL CLOSED: the risk action (close the position) always
                    # happens; the P&L reconciliation only happens when a real
                    # broker mark priced the exit. Without one the position is
                    # settled flat rather than at an invented premium.
                    close_at: Optional[float] = float(exit_mark) if exit_mark is not None else None
                    close_res = None
                    try:
                        close_res = await signal_paper_engine.close_signal_position(
                            sig.signal_id,
                            close_at,
                            reason=eval_action,
                        )
                    except Exception as pe:
                        logger.warning("paper_final_close_failed", signal_id=sig.signal_id, error=str(pe))
                        close_res = None

                    if close_res is None or (
                        isinstance(close_res, SignalPaperExecutionResult) and not close_res.success
                    ):
                        # Exit order did not fill (or there was nothing to close
                        # it with). Do NOT write the terminal state, do NOT
                        # reconcile, do NOT book P&L — leave everything exactly
                        # as it was so the next update tick retries.
                        logger.warning(
                            "final_close_not_filled_deferred",
                            signal_id=sig.signal_id,
                            action=eval_action,
                            status=getattr(close_res, "status", None),
                            detail=getattr(close_res, "message", None),
                        )
                        processed_events.append({
                            "signal_id": sig.signal_id,
                            "event": eval_action,
                            "price": float(d_price),
                            "settlement": "DEFERRED_EXIT_NOT_FILLED",
                        })
                        continue

                    # Confirmed fill → finalize the reconciler, then commit the
                    # terminal FSM state. `record_square_off` may already have
                    # finalized the reconciler via the paper-close path; the
                    # reconciler is idempotent per (stage, fill, time bucket).
                    if exit_mark is not None:
                        recon = option_fill_reconciler.reconcile_final_exit(sig, exit_mark, exit_reason=eval_action, exit_time_ms=ts_now)
                    else:
                        recon = None
                        logger.warning(
                            "final_exit_mark_unavailable_settling_flat",
                            signal_id=sig.signal_id,
                            action=eval_action,
                            broker_symbol=(sig.option_contract or {}).get("broker_symbol"),
                        )

                    signal_fsm.transition(sig.signal_id, eval_action, market_price=d_price, reason=f"{eval_action}_TRIGGERED")

                    # Ensure authoritative square-off is recorded in Signal Audit Ledger
                    sq_rec = None
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
                        # No real premium = no authority to book P&L. The paper
                        # engine's own square-off already settled the record flat.
                        if sig.option_contract and exit_mark is None:
                            sq_rec = signal_audit_ledger.get(sig.signal_id)
                        else:
                            exit_price_to_record = float(exit_mark) if sig.option_contract else float(d_price)
                            sq_rec = signal_audit_ledger.record_square_off(
                                signal_id=sig.signal_id,
                                exit_price=exit_price_to_record,
                                exit_reason=eval_action,
                                exit_time_ms=ts_now,
                            )
                            if not sq_rec:
                                sq_rec = signal_audit_ledger.get(sig.signal_id)
                        if sq_rec and recon:
                            # Guarded sync: the reconciler entry and the audit
                            # fill must share a domain (both option premiums
                            # <5000 or both spot-scale >5000). A spot-scale
                            # entry (e.g. trigger 23807 stored as fill) paired
                            # with a premium exit (132.98) fabricates a -₹17L
                            # P&L while points stay +14.23. Keep the audit's
                            # own P&L in that case and never persist garbage.
                            _audit_fill = sq_rec.actual_fill_price
                            _recon_entry = recon.entry_fill_price
                            _domain_ok = True
                            try:
                                if _audit_fill and _recon_entry:
                                    if (float(_audit_fill) > 5000) != (float(_recon_entry) > 5000):
                                        _domain_ok = False
                            except Exception:
                                _domain_ok = True
                            if _domain_ok:
                                _recon_synthetic = bool(getattr(recon, "synthetic", False))
                                _recon_booked_nothing = (
                                    recon.gross_realized_pnl == 0
                                    or (recon.final_fill_price is None and recon.t1_fill_price is None)
                                )
                                _audit_has_economics = (sq_rec.actual_pnl_inr or 0.0) != 0.0
                                # record_square_off already booked the reconciler
                                # net when the record is non-synthetic and fully
                                # closed — in that case the P&L (costs included)
                                # is final and must not be adjusted again.
                                _recon_is_canonical = (
                                    not _recon_synthetic and bool(recon.is_fully_closed)
                                )
                                if _recon_synthetic and _audit_has_economics:
                                    # Rebuilt after memory loss: prior stage splits
                                    # unknown — the ledger's own fill-based P&L
                                    # is more complete than residual-only sums.
                                    logger.info(
                                        "audit_recon_synthetic_skip_overwrite",
                                        signal_id=sig.signal_id,
                                        audit_pnl=sq_rec.actual_pnl_inr,
                                        recon_pnl=recon.net_realized_pnl_inr,
                                    )
                                elif _recon_booked_nothing and _audit_has_economics and not _recon_is_canonical:
                                    # Reconciler computed no gross price move on a trade
                                    # the ledger priced — deduct statutory costs if any, but keep audit profit.
                                    if recon.total_statutory_costs > 0 and sq_rec.actual_pnl_inr is not None:
                                        sq_rec.actual_pnl_inr = round(sq_rec.actual_pnl_inr - recon.total_statutory_costs, 2)
                                        sq_rec.total_pnl_inr = sq_rec.actual_pnl_inr
                                    sq_rec.is_winner = (sq_rec.actual_pnl_inr or 0.0) > 0
                                    sq_rec.status = "WON" if sq_rec.is_winner else ("LOST" if (sq_rec.actual_pnl_inr or 0.0) < 0 else "CLOSED")
                                    signal_audit_ledger._schedule_persist(sq_rec)
                                elif _recon_booked_nothing and _recon_is_canonical:
                                    # Ledger already booked the canonical net; no
                                    # second cost deduction on top of it.
                                    logger.debug(
                                        "audit_recon_canonical_skip_adjust",
                                        signal_id=sig.signal_id,
                                        audit_pnl=sq_rec.actual_pnl_inr,
                                    )
                                else:
                                    sq_rec.actual_pnl_inr = recon.net_realized_pnl_inr
                                    sq_rec.total_pnl_inr = recon.net_realized_pnl_inr
                                    _qty = recon.intended_qty or sq_rec.quantity or 0
                                    if _qty:
                                        try:
                                            sq_rec.actual_pnl_points = round(recon.gross_realized_pnl / _qty, 2)
                                        except Exception:
                                            pass
                                    if eval_action in ("STOP_LOSS_HIT", "LOSS"):
                                        sq_rec.is_winner = False
                                        sq_rec.status = "LOST"
                                    elif eval_action in ("TARGET_1_HIT", "TARGET_2_HIT"):
                                        sq_rec.is_winner = True
                                        sq_rec.status = "WON"
                                    else:
                                        sq_rec.is_winner = recon.net_realized_pnl_inr > 0
                                        sq_rec.status = "WON" if recon.net_realized_pnl_inr > 0 else ("LOST" if recon.net_realized_pnl_inr < 0 else "CLOSED")
                                    signal_audit_ledger._schedule_persist(sq_rec)
                                # Keep the displayed exit in the premium domain:
                                # a spot-scale exit (e.g. 74561) next to a
                                # premium entry (e.g. 417) reads as fake data.
                                # Skipped when the reconciler booked nothing —
                                # a zero/empty fill must never touch the exit.
                                if not _recon_booked_nothing or not _audit_has_economics:
                                    try:
                                        _final_px = float(recon.final_fill_price or 0.0)
                                        _exit_px = float(sq_rec.exit_price or 0.0)
                                        if _final_px > 0 and (_exit_px <= 0 or (_exit_px > 5000.0) != (_final_px > 5000.0)):
                                            sq_rec.exit_price = round(_final_px, 2)
                                            sq_rec.current_price = round(_final_px, 2)
                                            signal_audit_ledger._schedule_persist(sq_rec)
                                    except Exception:
                                        pass
                            else:
                                logger.warning(
                                    "audit_recon_domain_mismatch_skip_overwrite",
                                    signal_id=sig.signal_id,
                                    audit_fill=_audit_fill,
                                    recon_entry=_recon_entry,
                                    recon_exit=recon.final_fill_price,
                                    audit_pnl=sq_rec.actual_pnl_inr,
                                    recon_pnl=recon.net_realized_pnl_inr,
                                )
                    except Exception as le:
                        logger.warning("audit_square_off_failed", signal_id=sig.signal_id, error=str(le))

                    # Dispatch Telegram notifications
                    _event_pnl = (
                        recon.net_realized_pnl_inr if recon is not None
                        else (sq_rec.actual_pnl_inr if sq_rec is not None else None)
                    )
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
                            actual_pnl_amount=_event_pnl,
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
                            "reconciliation": recon.model_dump() if recon is not None else None,
                        },
                        priority="P0",
                    )
                    processed_events.append({
                        "signal_id": sig.signal_id,
                        "event": eval_action,
                        "price": float(d_price),
                        "actual_pnl": _event_pnl,
                        "realized_rr": recon.realized_rr if recon is not None else None,
                    })

        return processed_events


outcome_tracker = SignalOutcomeTracker()

