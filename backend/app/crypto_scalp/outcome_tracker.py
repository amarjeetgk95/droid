"""
Crypto Scalp Outcome & Execution Lifecycle Tracker
Deterministic Finite State Machine (FSM) managing active paper trades,
tick processing, partial exits at T1, breakeven stop ratchets,
terminal exits (T2, Stop, Time-Stop), and persistent event logging.
"""
from __future__ import annotations

import asyncio
import time
import structlog
from typing import Optional

from app.models.crypto import CryptoScalpSignal, SignalDirection
from app.crypto_scalp.models_execution import (
    CryptoScalpPositionState,
    CryptoScalpExitEventType,
    CryptoScalpExecutionMode,
    CryptoScalpExecutionConfig,
    CryptoScalpExecutionRecord,
    CryptoScalpExecutionEvent,
)
from app.crypto_scalp.paper_execution import paper_execution_provider
from app.crypto_scalp.persistence import (
    save_execution_record,
    save_execution_event,
    load_unclosed_execution_records,
)

logger = structlog.get_logger()


class CryptoScalpOutcomeTracker:
    """
    Manages active position lifecycles, ordered price evaluation,
    T1 partial close + BE ratchet, and terminal exit reconciliation.
    """

    def __init__(self, config: CryptoScalpExecutionConfig | None = None):
        self.config = config or CryptoScalpExecutionConfig()
        self.active_positions: dict[str, CryptoScalpExecutionRecord] = {}
        self._lock = asyncio.Lock()
        self._recovered = False

    async def recover_active_positions(self) -> int:
        """Recover unclosed positions from Supabase/cache on startup."""
        async with self._lock:
            try:
                unclosed = await load_unclosed_execution_records()
                for rec in unclosed:
                    self.active_positions[rec.trade_id] = rec
                self._recovered = True
                logger.info("crypto_scalp_active_positions_recovered", count=len(unclosed))
                return len(unclosed)
            except Exception as e:
                logger.warning("crypto_scalp_recovery_failed", error=str(e)[:200])
                return 0

    async def register_signal(
        self,
        signal: CryptoScalpSignal,
        spread: float = 0.0,
    ) -> CryptoScalpExecutionRecord:
        """
        Transition a newly fired CryptoScalpSignal into an ACTIVE paper position.
        Calculates position sizing and entry fill with friction.
        """
        async with self._lock:
            trade_id = f"trade_{signal.id}"

            # Idempotency check
            if trade_id in self.active_positions:
                return self.active_positions[trade_id]

            now_ms = int(time.time() * 1000)

            # 1. Position Sizing
            qty, notional_usd, risk_usd = paper_execution_provider.calculate_position_size(
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                symbol=signal.symbol,
            )

            # 2. Entry Fill Simulation (Ask for Long, Bid for Short + Slippage)
            fill = paper_execution_provider.calculate_fill(
                market_price=signal.entry_price,
                direction=signal.direction,
                is_entry=True,
                quantity=qty,
                spread=spread,
            )

            # 3. Create Execution Record
            trade = CryptoScalpExecutionRecord(
                trade_id=trade_id,
                signal_id=signal.id,
                symbol=signal.symbol,
                asset=signal.asset,
                direction=signal.direction,
                strategy=signal.strategy,
                strategy_name=signal.strategy_name,
                execution_mode=self.config.execution_mode,
                position_state=CryptoScalpPositionState.ACTIVE,
                signal_price=signal.entry_price,
                entry_fill_price=fill.fill_price,
                initial_stop_price=signal.stop_loss,
                current_stop_price=signal.stop_loss,
                target_1_price=signal.target_1,
                target_2_price=signal.target_2,
                quantity_initial=qty,
                quantity_remaining=qty,
                notional_usd=fill.notional_usd,
                initial_risk_usd=risk_usd,
                gross_pnl_usd=0.0,
                fees_usd=fill.fee_usd,
                slippage_usd=fill.slippage_usd,
                net_pnl_usd=round(-fill.fee_usd, 4),
                created_at_utc=signal.created_at_utc or now_ms,
            )

            # 4. Create Entry Fill Audit Event
            entry_event = CryptoScalpExecutionEvent(
                event_id=f"ev_entry_{trade_id}",
                trade_id=trade_id,
                signal_id=signal.id,
                event_type=CryptoScalpExitEventType.ENTRY_FILL,
                symbol=signal.symbol,
                direction=signal.direction,
                strategy=signal.strategy,
                timestamp_ms=now_ms,
                market_price=signal.entry_price,
                fill_price=fill.fill_price,
                quantity=qty,
                fee_usd=fill.fee_usd,
                slippage_usd=fill.slippage_usd,
                gross_pnl_usd=0.0,
                net_pnl_usd=round(-fill.fee_usd, 4),
                r_multiple=0.0,
                state_before=CryptoScalpPositionState.ACTIVE,
                state_after=CryptoScalpPositionState.ACTIVE,
                metadata_json={
                    "spread_usd": fill.spread_usd,
                    "notional_usd": fill.notional_usd,
                    "risk_usd": risk_usd,
                },
            )
            trade.events.append(entry_event)

            # 5. Store & Persist
            self.active_positions[trade_id] = trade
            asyncio.create_task(save_execution_event(entry_event))
            asyncio.create_task(save_execution_record(trade))

            logger.info(
                "crypto_scalp_trade_opened",
                trade_id=trade_id,
                symbol=trade.symbol,
                direction=trade.direction.value,
                entry_fill=fill.fill_price,
                qty=qty,
                risk_usd=risk_usd,
            )
            return trade

    async def process_tick(
        self,
        symbol: str,
        current_price: float,
        high: Optional[float] = None,
        low: Optional[float] = None,
        spread: float = 0.0,
        timestamp_ms: Optional[int] = None,
    ) -> list[CryptoScalpExecutionRecord]:
        """
        Evaluate all active positions for the given symbol against incoming market tick.
        Resolves partial exits at T1, breakeven ratchets, T2, stop losses, and time-stops.
        Returns list of trades that had state transitions in this tick.
        """
        now_ms = timestamp_ms or int(time.time() * 1000)
        bar_high = high if high is not None else current_price
        bar_low = low if low is not None else current_price
        modified_trades: list[CryptoScalpExecutionRecord] = []

        async with self._lock:
            active_ids = [t_id for t_id, t in self.active_positions.items() if t.symbol.upper() == symbol.upper()]

            for trade_id in active_ids:
                trade = self.active_positions.get(trade_id)
                if not trade:
                    continue

                transitioned = False

                # A. 30-Minute Time-Stop Check
                age_seconds = (now_ms - trade.created_at_utc) / 1000.0
                if age_seconds >= self.config.time_stop_seconds:
                    await self._apply_terminal_exit(
                        trade=trade,
                        exit_price=current_price,
                        exit_reason=CryptoScalpExitEventType.TIME_STOP,
                        spread=spread,
                        timestamp_ms=now_ms,
                    )
                    modified_trades.append(trade)
                    continue

                # B. Direction-Specific Price Evaluation
                if trade.direction == SignalDirection.LONG:
                    transitioned = await self._evaluate_long(
                        trade=trade,
                        current_price=current_price,
                        high=bar_high,
                        low=bar_low,
                        spread=spread,
                        timestamp_ms=now_ms,
                    )
                else:
                    transitioned = await self._evaluate_short(
                        trade=trade,
                        current_price=current_price,
                        high=bar_high,
                        low=bar_low,
                        spread=spread,
                        timestamp_ms=now_ms,
                    )

                if transitioned:
                    modified_trades.append(trade)

        # ── Evaluate Institutional Crypto Signal FSM Instances ──
        try:
            await self.process_fsm_tick(
                symbol=symbol,
                current_price=current_price,
                high=bar_high,
                low=bar_low,
                timestamp_ms=now_ms,
            )
        except Exception as fsm_err:
            logger.debug("crypto_fsm_tick_eval_failed", symbol=symbol, error=str(fsm_err))

        return modified_trades

    async def process_fsm_tick(
        self,
        symbol: str,
        current_price: float,
        high: Optional[float] = None,
        low: Optional[float] = None,
        timestamp_ms: Optional[int] = None,
    ) -> list[dict]:
        """
        Ordered priority evaluation for active Crypto Signal FSM instances:
          1. Check Trigger & Confirmation for ARMED/VALIDATED signals.
          2. Check Time-Stop / Runner Time-Stop for CONFIRMED/TARGET_1_HIT.
          3. Check Stop-Loss / Breakeven Stop.
          4. Check Target 1 (50% staged exit + SL ratchet to Entry).
          5. Check Target 2 (Runner terminal exit).
          6. Check +0.8R Breakeven Ratchet.
        """
        from app.crypto_scalp.fsm import crypto_signal_fsm
        from app.crypto_scalp.fill_reconciler import crypto_fill_reconciler
        from app.crypto_scalp.sse import crypto_sse_hub
        from decimal import Decimal

        now_ms = timestamp_ms or int(time.time() * 1000)
        d_price = Decimal(str(current_price))
        d_high = Decimal(str(high if high is not None else current_price))
        d_low = Decimal(str(low if low is not None else current_price))

        active_fsm = crypto_signal_fsm.list_active(symbol=symbol)
        events = []

        for sig in active_fsm:
            st = sig.fsm_state
            if st in ("TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT", "CLOSED", "EXPIRED", "INVALIDATED"):
                continue

            is_long = sig.direction == "LONG"

            # 1. Trigger & Confirmation
            if st in ("VALIDATED", "ARMED"):
                triggered = False
                if is_long and d_high >= sig.trigger:
                    triggered = True
                elif not is_long and d_low <= sig.trigger:
                    triggered = True

                if triggered:
                    crypto_signal_fsm.transition(sig.signal_id, "TRIGGERED", market_price=sig.trigger, reason="TRIGGER_LEVEL_HIT")
                    crypto_fill_reconciler.reconcile_entry(sig, fill_price=float(sig.trigger), quantity=sig.quantity or 0.01)
                    crypto_signal_fsm.transition(sig.signal_id, "CONFIRMED", market_price=sig.trigger, reason="ENTRY_CONFIRMED")
                    events.append({"signal_id": sig.signal_id, "event": "CONFIRMED", "price": float(sig.trigger)})

                    # Create and persist execution record when entry is confirmed so ledger shows the trade immediately
                    try:
                        from app.crypto_scalp.persistence import save_execution_record
                        from app.models.crypto import SignalDirection as SDS
                        from app.crypto_scalp.models_execution import CryptoScalpPositionState as PSS

                        trade_id = f"trade_{sig.signal_id}"
                        rec = crypto_fill_reconciler.get_record(sig.signal_id)
                        if rec:
                            # Create execution record matching the outcome_tracker format
                            from decimal import Decimal
                            qty = float(sig.quantity) if sig.quantity else 0.01
                            entry_fill = float(sig.trigger)

                            # Calculate risk
                            risk_pts = float(abs(sig.trigger - sig.stop_loss)) if sig.trigger and sig.stop_loss else 0.0
                            risk_usd = round(qty * risk_pts, 2)

                            execution_record = CryptoScalpExecutionRecord(
                                trade_id=trade_id,
                                signal_id=sig.signal_id,
                                symbol=sig.symbol,
                                asset=sig.asset,
                                direction=SignalDirection.LONG if sig.direction == "LONG" else SignalDirection.SHORT,
                                strategy=sig.strategy,
                                strategy_name=sig.strategy_name or sig.strategy,
                                execution_mode=CryptoScalpExecutionMode.PAPER,
                                position_state=CryptoScalpPositionState.ACTIVE,
                                signal_price=float(sig.trigger),
                                entry_fill_price=entry_fill,
                                initial_stop_price=float(sig.stop_loss),
                                current_stop_price=float(sig.current_stop_loss or sig.stop_loss),
                                target_1_price=float(sig.target_1),
                                target_2_price=float(sig.target_2),
                                quantity_initial=qty,
                                quantity_remaining=qty,
                                notional_usd=round(entry_fill * qty, 2),
                                initial_risk_usd=risk_usd,
                                gross_pnl_usd=0.0,
                                fees_usd=rec.total_fees_usd,
                                slippage_usd=rec.total_slippage_usd,
                                net_pnl_usd=-rec.total_fees_usd,
                                created_at_utc=sig.created_at_utc,
                            )

                            # Add entry event
                            from app.crypto_scalp.models_execution import CryptoScalpExitEventType
                            entry_event = CryptoScalpExecutionEvent(
                                event_id=f"ev_entry_{trade_id}",
                                trade_id=trade_id,
                                signal_id=sig.signal_id,
                                event_type=CryptoScalpExitEventType.ENTRY_FILL,
                                symbol=sig.symbol,
                                direction=SignalDirection.LONG if sig.direction == "LONG" else SignalDirection.SHORT,
                                strategy=sig.strategy,
                                timestamp_ms=int(time.time() * 1000),
                                market_price=entry_fill,
                                fill_price=entry_fill,
                                quantity=qty,
                                fee_usd=rec.total_fees_usd,
                                slippage_usd=rec.total_slippage_usd,
                                gross_pnl_usd=0.0,
                                net_pnl_usd=-rec.total_fees_usd,
                                r_multiple=0.0,
                                state_before=CryptoScalpPositionState.ACTIVE,
                                state_after=CryptoScalpPositionState.ACTIVE,
                            )
                            execution_record.events.append(entry_event)

                            # Add to active_positions so outcome_tracker can process future ticks
                            self.active_positions[trade_id] = execution_record

                            # Persist to database
                            asyncio.create_task(save_execution_record(execution_record))
                            asyncio.create_task(save_execution_event(entry_event))

                            logger.info(
                                "crypto_scalp_fsm_trade_registered",
                                trade_id=trade_id,
                                signal_id=sig.signal_id,
                                symbol=sig.symbol,
                                entry_fill=entry_fill,
                                qty=qty,
                            )
                    except Exception as e:
                        logger.warning("crypto_scalp_fsm_trade_registration_failed", signal_id=sig.signal_id, error=str(e)[:200])

                    try:
                        await crypto_sse_hub.broadcast("signal_confirmed", sig.model_dump(), priority="P0")
                    except Exception:
                        pass

            # 2. Ordered evaluation for CONFIRMED and TARGET_1_HIT
            elif st in ("CONFIRMED", "TARGET_1_HIT"):
                res = crypto_signal_fsm.evaluate_tick(sig, d_price, now_ms)
                if res == "BE_ACTIVATED":
                    crypto_signal_fsm.ratchet_breakeven(sig.signal_id, d_price)
                    events.append({"signal_id": sig.signal_id, "event": "BREAKEVEN_RATCHET", "price": float(d_price)})
                    try:
                        await crypto_sse_hub.broadcast("breakeven_ratchet", {"signal_id": sig.signal_id, "price": float(d_price)}, priority="P0")
                    except Exception:
                        pass
                elif res == "TARGET_1_HIT":
                    # FSM transition first (state integrity, runner clock, BE ratchet);
                    # the fill reconciler then owns the authoritative blended net R.
                    crypto_signal_fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=sig.target_1, reason="T1_HIT")
                    crypto_fill_reconciler.reconcile_t1_exit(sig, exit_fill_price=float(sig.target_1), exit_time_ms=now_ms)
                    events.append({"signal_id": sig.signal_id, "event": "TARGET_1_HIT", "price": float(sig.target_1), "rr": sig.realized_rr})

                    # Update execution record in active_positions
                    try:
                        trade_id = f"trade_{sig.signal_id}"
                        if trade_id in self.active_positions:
                            trade = self.active_positions[trade_id]
                            # Apply same logic as _apply_partial_exit_t1
                            close_qty = round(trade.quantity_initial * self.config.target_1_close_fraction, 4)
                            if close_qty <= 0 or close_qty > trade.quantity_remaining:
                                close_qty = trade.quantity_remaining
                            from app.crypto_scalp.paper_execution import paper_execution_provider
                            fill = paper_execution_provider.calculate_fill(
                                market_price=float(sig.target_1),
                                direction=trade.direction,
                                is_entry=False,
                                quantity=close_qty,
                                spread=0.0,
                            )
                            if trade.direction == SignalDirection.LONG:
                                gross_pnl_t1 = close_qty * (fill.fill_price - trade.entry_fill_price)
                            else:
                                gross_pnl_t1 = close_qty * (trade.entry_fill_price - fill.fill_price)
                            net_pnl_t1 = gross_pnl_t1 - fill.fee_usd

                            trade.quantity_closed_t1 = close_qty
                            trade.quantity_remaining = max(0.0, round(trade.quantity_remaining - close_qty, 4))
                            trade.position_state = CryptoScalpPositionState.PARTIALLY_CLOSED
                            trade.current_stop_price = trade.entry_fill_price
                            trade.t1_hit_at = now_ms
                            trade.gross_pnl_usd = round(trade.gross_pnl_usd + gross_pnl_t1, 4)
                            trade.fees_usd = round(trade.fees_usd + fill.fee_usd, 4)
                            trade.slippage_usd = round(trade.slippage_usd + fill.slippage_usd, 4)
                            trade.net_pnl_usd = round(trade.gross_pnl_usd - trade.fees_usd, 4)

                            t1_event = CryptoScalpExecutionEvent(
                                event_id=f"ev_t1_{trade_id}_{now_ms}",
                                trade_id=trade_id,
                                signal_id=sig.signal_id,
                                event_type=CryptoScalpExitEventType.T1_HIT,
                                symbol=trade.symbol,
                                direction=trade.direction,
                                strategy=trade.strategy,
                                timestamp_ms=now_ms,
                                market_price=float(sig.target_1),
                                fill_price=fill.fill_price,
                                quantity=close_qty,
                                fee_usd=fill.fee_usd,
                                slippage_usd=fill.slippage_usd,
                                gross_pnl_usd=round(gross_pnl_t1, 4),
                                net_pnl_usd=round(net_pnl_t1, 4),
                                r_multiple=round(net_pnl_t1 / max(1.0, trade.initial_risk_usd), 2),
                                state_before=CryptoScalpPositionState.ACTIVE,
                                state_after=CryptoScalpPositionState.PARTIALLY_CLOSED,
                                metadata_json={"new_stop_price": trade.current_stop_price},
                            )
                            trade.events.append(t1_event)
                            asyncio.create_task(save_execution_event(t1_event))
                            asyncio.create_task(save_execution_record(trade))
                    except Exception as e:
                        logger.warning("crypto_scalp_t1_update_failed", signal_id=sig.signal_id, error=str(e)[:200])

                    try:
                        await crypto_sse_hub.broadcast("target_1_hit", sig.model_dump(), priority="P0")
                    except Exception:
                        pass
                elif res in ("TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT"):
                    exit_p = float(sig.current_stop_loss or sig.stop_loss) if res == "STOP_LOSS_HIT" else (
                        float(sig.target_2) if res == "TARGET_2_HIT" else current_price
                    )
                    # FSM transition first, then the reconciler sets the authoritative
                    # blended net P&L / R (FSM no longer overwrites it with crude constants).
                    crypto_signal_fsm.transition(sig.signal_id, res, market_price=Decimal(str(exit_p)), reason=f"{res}_TRIGGERED")
                    crypto_fill_reconciler.reconcile_final_exit(sig, exit_fill_price=exit_p, exit_reason=res, exit_time_ms=now_ms)
                    events.append({"signal_id": sig.signal_id, "event": res, "price": exit_p, "rr": sig.realized_rr})

                    # Bridge the FSM/fill-reconciler ledger into the persisted
                    # executions ledger so the performance API reports real trades.
                    try:
                        from app.crypto_scalp.persistence import save_execution_record_from_reconciliation
                        rec = crypto_fill_reconciler.get_record(sig.signal_id)
                        if rec:
                            asyncio.create_task(save_execution_record_from_reconciliation(sig, rec, res))
                    except Exception:
                        pass

                    try:
                        await crypto_sse_hub.broadcast("signal_exit", {"signal_id": sig.signal_id, "status": res, "exit_price": exit_p, "rr": sig.realized_rr}, priority="P0")
                    except Exception:
                        pass

        return events

    async def _evaluate_long(
        self,
        trade: CryptoScalpExecutionRecord,
        current_price: float,
        high: float,
        low: float,
        spread: float,
        timestamp_ms: int,
    ) -> bool:
        """Evaluate Long position FSM transitions."""
        # 1. Ambiguity Policy Check (if bar crosses both T1 and Stop Loss in same tick)
        if trade.position_state == CryptoScalpPositionState.ACTIVE:
            t1_crossed = high >= trade.target_1_price
            sl_crossed = low <= trade.current_stop_price

            if t1_crossed and sl_crossed:
                if self.config.ambiguous_trigger_policy == "CONSERVATIVE":
                    # Conservatively assume stop hit first
                    await self._apply_terminal_exit(
                        trade=trade,
                        exit_price=trade.current_stop_price,
                        exit_reason=CryptoScalpExitEventType.INITIAL_STOP,
                        spread=spread,
                        timestamp_ms=timestamp_ms,
                    )
                    return True

        # 2. Stop Loss Check (Active = Initial SL, Partially Closed = Breakeven Stop)
        if low <= trade.current_stop_price:
            reason = (
                CryptoScalpExitEventType.INITIAL_STOP
                if trade.position_state == CryptoScalpPositionState.ACTIVE
                else CryptoScalpExitEventType.BREAKEVEN_STOP
            )
            await self._apply_terminal_exit(
                trade=trade,
                exit_price=trade.current_stop_price,
                exit_reason=reason,
                spread=spread,
                timestamp_ms=timestamp_ms,
            )
            return True

        # 3. Target 1 Partial Exit (only when state == ACTIVE)
        if trade.position_state == CryptoScalpPositionState.ACTIVE and high >= trade.target_1_price:
            await self._apply_partial_exit_t1(
                trade=trade,
                fill_price=trade.target_1_price,
                spread=spread,
                timestamp_ms=timestamp_ms,
            )
            # If high also breached target 2 in the same tick after T1 hit
            if high >= trade.target_2_price:
                await self._apply_terminal_exit(
                    trade=trade,
                    exit_price=trade.target_2_price,
                    exit_reason=CryptoScalpExitEventType.T2_HIT,
                    spread=spread,
                    timestamp_ms=timestamp_ms,
                )
            return True

        # 4. Target 2 Final Exit (when state == PARTIALLY_CLOSED)
        if trade.position_state == CryptoScalpPositionState.PARTIALLY_CLOSED and high >= trade.target_2_price:
            await self._apply_terminal_exit(
                trade=trade,
                exit_price=trade.target_2_price,
                exit_reason=CryptoScalpExitEventType.T2_HIT,
                spread=spread,
                timestamp_ms=timestamp_ms,
            )
            return True

        return False

    async def _evaluate_short(
        self,
        trade: CryptoScalpExecutionRecord,
        current_price: float,
        high: float,
        low: float,
        spread: float,
        timestamp_ms: int,
    ) -> bool:
        """Evaluate Short position FSM transitions."""
        # 1. Ambiguity Policy Check (if bar crosses both T1 and Stop Loss in same tick)
        if trade.position_state == CryptoScalpPositionState.ACTIVE:
            t1_crossed = low <= trade.target_1_price
            sl_crossed = high >= trade.current_stop_price

            if t1_crossed and sl_crossed:
                if self.config.ambiguous_trigger_policy == "CONSERVATIVE":
                    # Conservatively assume stop hit first
                    await self._apply_terminal_exit(
                        trade=trade,
                        exit_price=trade.current_stop_price,
                        exit_reason=CryptoScalpExitEventType.INITIAL_STOP,
                        spread=spread,
                        timestamp_ms=timestamp_ms,
                    )
                    return True

        # 2. Stop Loss Check (Active = Initial SL, Partially Closed = Breakeven Stop)
        if high >= trade.current_stop_price:
            reason = (
                CryptoScalpExitEventType.INITIAL_STOP
                if trade.position_state == CryptoScalpPositionState.ACTIVE
                else CryptoScalpExitEventType.BREAKEVEN_STOP
            )
            await self._apply_terminal_exit(
                trade=trade,
                exit_price=trade.current_stop_price,
                exit_reason=reason,
                spread=spread,
                timestamp_ms=timestamp_ms,
            )
            return True

        # 3. Target 1 Partial Exit (only when state == ACTIVE)
        if trade.position_state == CryptoScalpPositionState.ACTIVE and low <= trade.target_1_price:
            await self._apply_partial_exit_t1(
                trade=trade,
                fill_price=trade.target_1_price,
                spread=spread,
                timestamp_ms=timestamp_ms,
            )
            # If low also breached target 2 in the same tick after T1 hit
            if low <= trade.target_2_price:
                await self._apply_terminal_exit(
                    trade=trade,
                    exit_price=trade.target_2_price,
                    exit_reason=CryptoScalpExitEventType.T2_HIT,
                    spread=spread,
                    timestamp_ms=timestamp_ms,
                )
            return True

        # 4. Target 2 Final Exit (when state == PARTIALLY_CLOSED)
        if trade.position_state == CryptoScalpPositionState.PARTIALLY_CLOSED and low <= trade.target_2_price:
            await self._apply_terminal_exit(
                trade=trade,
                exit_price=trade.target_2_price,
                exit_reason=CryptoScalpExitEventType.T2_HIT,
                spread=spread,
                timestamp_ms=timestamp_ms,
            )
            return True

        return False

    async def _apply_partial_exit_t1(
        self,
        trade: CryptoScalpExecutionRecord,
        fill_price: float,
        spread: float,
        timestamp_ms: int,
    ) -> None:
        """
        Execute 50% partial exit at Target 1 and ratchet Stop Loss to Entry Breakeven.
        """
        close_qty = round(trade.quantity_initial * self.config.target_1_close_fraction, 4)
        if close_qty <= 0 or close_qty > trade.quantity_remaining:
            close_qty = trade.quantity_remaining

        # Fill calculation for partial exit
        fill = paper_execution_provider.calculate_fill(
            market_price=fill_price,
            direction=trade.direction,
            is_entry=False,
            quantity=close_qty,
            spread=spread,
        )

        # Realized gross PnL on T1 tranche
        if trade.direction == SignalDirection.LONG:
            gross_pnl_t1 = close_qty * (fill.fill_price - trade.entry_fill_price)
        else:
            gross_pnl_t1 = close_qty * (trade.entry_fill_price - fill.fill_price)

        net_pnl_t1 = gross_pnl_t1 - fill.fee_usd

        # Update Trade Record
        trade.quantity_closed_t1 = close_qty
        trade.quantity_remaining = max(0.0, round(trade.quantity_remaining - close_qty, 4))
        trade.position_state = CryptoScalpPositionState.PARTIALLY_CLOSED
        trade.current_stop_price = trade.entry_fill_price  # Ratchet to Breakeven
        trade.t1_hit_at = timestamp_ms
        trade.gross_pnl_usd = round(trade.gross_pnl_usd + gross_pnl_t1, 4)
        trade.fees_usd = round(trade.fees_usd + fill.fee_usd, 4)
        trade.slippage_usd = round(trade.slippage_usd + fill.slippage_usd, 4)
        trade.net_pnl_usd = round(trade.gross_pnl_usd - trade.fees_usd, 4)

        # 1. Event: T1 Hit
        t1_event = CryptoScalpExecutionEvent(
            event_id=f"ev_t1_{trade.trade_id}_{timestamp_ms}",
            trade_id=trade.trade_id,
            signal_id=trade.signal_id,
            event_type=CryptoScalpExitEventType.T1_HIT,
            symbol=trade.symbol,
            direction=trade.direction,
            strategy=trade.strategy,
            timestamp_ms=timestamp_ms,
            market_price=fill_price,
            fill_price=fill.fill_price,
            quantity=close_qty,
            fee_usd=fill.fee_usd,
            slippage_usd=fill.slippage_usd,
            gross_pnl_usd=round(gross_pnl_t1, 4),
            net_pnl_usd=round(net_pnl_t1, 4),
            r_multiple=round(net_pnl_t1 / max(1.0, trade.initial_risk_usd), 2),
            state_before=CryptoScalpPositionState.ACTIVE,
            state_after=CryptoScalpPositionState.PARTIALLY_CLOSED,
            metadata_json={"new_stop_price": trade.current_stop_price},
        )
        trade.events.append(t1_event)

        # 2. Event: Breakeven Ratchet
        be_event = CryptoScalpExecutionEvent(
            event_id=f"ev_be_{trade.trade_id}_{timestamp_ms}",
            trade_id=trade.trade_id,
            signal_id=trade.signal_id,
            event_type=CryptoScalpExitEventType.BREAKEVEN_RATCHET,
            symbol=trade.symbol,
            direction=trade.direction,
            strategy=trade.strategy,
            timestamp_ms=timestamp_ms,
            market_price=trade.entry_fill_price,
            fill_price=trade.entry_fill_price,
            quantity=0.0,
            fee_usd=0.0,
            slippage_usd=0.0,
            gross_pnl_usd=0.0,
            net_pnl_usd=0.0,
            r_multiple=0.0,
            state_before=CryptoScalpPositionState.PARTIALLY_CLOSED,
            state_after=CryptoScalpPositionState.PARTIALLY_CLOSED,
            metadata_json={"new_stop_price": trade.current_stop_price},
        )
        trade.events.append(be_event)

        asyncio.create_task(save_execution_event(t1_event))
        asyncio.create_task(save_execution_event(be_event))
        asyncio.create_task(save_execution_record(trade))

        logger.info(
            "crypto_scalp_t1_booked_and_ratcheted",
            trade_id=trade.trade_id,
            symbol=trade.symbol,
            closed_qty=close_qty,
            net_pnl_t1=round(net_pnl_t1, 2),
            new_stop=trade.current_stop_price,
        )

    async def _apply_terminal_exit(
        self,
        trade: CryptoScalpExecutionRecord,
        exit_price: float,
        exit_reason: CryptoScalpExitEventType,
        spread: float,
        timestamp_ms: int,
    ) -> None:
        """
        Execute final exit of remaining quantity, calculate Net Realized R,
        Execution Drag, duration, update state to CLOSED, and remove from active.
        """
        state_before = trade.position_state
        close_qty = trade.quantity_remaining

        fill = paper_execution_provider.calculate_fill(
            market_price=exit_price,
            direction=trade.direction,
            is_entry=False,
            quantity=close_qty,
            spread=spread,
        )

        # Realized gross PnL on remaining tranche
        if trade.direction == SignalDirection.LONG:
            final_gross = close_qty * (fill.fill_price - trade.entry_fill_price)
        else:
            final_gross = close_qty * (trade.entry_fill_price - fill.fill_price)

        final_net = final_gross - fill.fee_usd

        # Update Trade Record
        trade.quantity_closed_final = close_qty
        trade.quantity_remaining = 0.0
        trade.exit_price = fill.fill_price
        trade.exit_reason = exit_reason
        trade.position_state = CryptoScalpPositionState.CLOSED
        trade.gross_pnl_usd = round(trade.gross_pnl_usd + final_gross, 4)
        trade.fees_usd = round(trade.fees_usd + fill.fee_usd, 4)
        trade.slippage_usd = round(trade.slippage_usd + fill.slippage_usd, 4)
        trade.net_pnl_usd = round(trade.gross_pnl_usd - trade.fees_usd, 4)

        if exit_reason == CryptoScalpExitEventType.T2_HIT:
            trade.t2_hit_at = timestamp_ms
        elif exit_reason in (CryptoScalpExitEventType.INITIAL_STOP, CryptoScalpExitEventType.BREAKEVEN_STOP):
            trade.stop_hit_at = timestamp_ms

        # Duration
        trade.closed_at_utc = timestamp_ms
        duration_sec = max(0, int((timestamp_ms - trade.created_at_utc) / 1000))
        trade.duration_seconds = duration_sec
        mins = duration_sec // 60
        secs = duration_sec % 60
        trade.duration_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

        # Return % on Initial Risk
        risk_base = max(1.0, trade.initial_risk_usd)
        trade.net_return_pct = round((trade.net_pnl_usd / risk_base) * 100.0, 2)
        trade.r_multiple = round(trade.net_pnl_usd / risk_base, 2)

        # Theoretical R calculation
        if exit_reason == CryptoScalpExitEventType.T2_HIT:
            # 50% at 1.5R + 50% at 2.5R = 2.0R theoretical
            trade.theoretical_r = 2.0
        elif exit_reason == CryptoScalpExitEventType.BREAKEVEN_STOP:
            # 50% at 1.5R + 50% at 0.0R = 0.75R theoretical
            trade.theoretical_r = 0.75
        elif exit_reason == CryptoScalpExitEventType.INITIAL_STOP:
            trade.theoretical_r = -1.0
        elif exit_reason == CryptoScalpExitEventType.TIME_STOP:
            # Theoretical exit at market price without friction
            stop_dist = max(0.0001, abs(trade.signal_price - trade.initial_stop_price))
            move = (exit_price - trade.signal_price) if trade.direction == SignalDirection.LONG else (trade.signal_price - exit_price)
            raw_r = move / stop_dist
            if trade.quantity_closed_t1 > 0:
                trade.theoretical_r = round(0.5 * 1.5 + 0.5 * raw_r, 2)
            else:
                trade.theoretical_r = round(raw_r, 2)
        else:
            trade.theoretical_r = trade.r_multiple

        trade.execution_drag_r = round(trade.theoretical_r - trade.r_multiple, 2)
        from app.crypto_scalp.models_execution import format_detailed_exit_reason
        trade.exit_reason_detail = format_detailed_exit_reason(
            reason=exit_reason,
            symbol=trade.symbol,
            entry_fill=trade.entry_fill_price,
            exit_price=trade.exit_price,
            target_1=trade.target_1_price,
            target_2=trade.target_2_price,
            stop_loss=trade.initial_stop_price,
            r_multiple=trade.r_multiple,
            duration_str=trade.duration_str,
        )

        # Terminal Audit Event
        exit_event = CryptoScalpExecutionEvent(
            event_id=f"ev_exit_{trade.trade_id}_{timestamp_ms}",
            trade_id=trade.trade_id,
            signal_id=trade.signal_id,
            event_type=exit_reason,
            symbol=trade.symbol,
            direction=trade.direction,
            strategy=trade.strategy,
            timestamp_ms=timestamp_ms,
            market_price=exit_price,
            fill_price=fill.fill_price,
            quantity=close_qty,
            fee_usd=fill.fee_usd,
            slippage_usd=fill.slippage_usd,
            gross_pnl_usd=round(final_gross, 4),
            net_pnl_usd=round(final_net, 4),
            r_multiple=trade.r_multiple,
            state_before=state_before,
            state_after=CryptoScalpPositionState.CLOSED,
            metadata_json={
                "duration_seconds": duration_sec,
                "net_pnl_total": trade.net_pnl_usd,
                "theoretical_r": trade.theoretical_r,
                "execution_drag_r": trade.execution_drag_r,
            },
        )
        trade.events.append(exit_event)

        # Remove from active
        if trade.trade_id in self.active_positions:
            del self.active_positions[trade.trade_id]

        asyncio.create_task(save_execution_event(exit_event))
        asyncio.create_task(save_execution_record(trade))

        logger.info(
            "crypto_scalp_trade_closed",
            trade_id=trade.trade_id,
            symbol=trade.symbol,
            reason=exit_reason.value,
            exit_fill=fill.fill_price,
            net_pnl_usd=trade.net_pnl_usd,
            r_multiple=trade.r_multiple,
            drag_r=trade.execution_drag_r,
            duration=trade.duration_str,
        )


crypto_scalp_outcome_tracker = CryptoScalpOutcomeTracker()
