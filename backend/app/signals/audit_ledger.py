"""
Institutional Signal Audit Ledger & Trade Performance Engine
Provides comprehensive lifecycle auditing for quantitative signals:
  - ARMED -> CONFIRMED -> PAPER_EXECUTED -> TARGET_HIT / STOP_LOSS_HIT -> SQUARED_OFF
  - Exact realized Profit and Loss (INR ₹, points, and %)
  - Slippage & Spread audit
  - Portfolio attribution & Strategy performance analytics
"""
from __future__ import annotations

import time
from typing import Any, Optional
import structlog

from app.signals.audit_models import (
    AUDIT_TO_FSM_STATUS,
    FSM_TO_AUDIT_STATUS as FSM_TO_AUDIT_STATUS,
    SETTLED_STATUSES,
    AuditStateEvent,
    AuditTradeRecord,
    format_timestamp_ist as format_timestamp_ist,
)
from app.signals.audit_settlement import AuditSettlementMixin

logger = structlog.get_logger()


class SignalAuditLedger(AuditSettlementMixin):
    """
    Authoritative append-only in-memory ledger for Signal & Paper Trade Audit with PnL reconciliation.
    """

    def __init__(self, max_records: int = 5000):
        self._trades: dict[str, AuditTradeRecord] = {}  # signal_id -> AuditTradeRecord
        self._max_records = max_records
        import threading
        self._lock = threading.RLock()

    # NOTE: get/delete_trade are defined once at the end of the class
    # (with Supabase deletion + logging). Do not re-add duplicates here.

    def record_signal_created(
        self,
        signal_id: str,
        underlying: str,
        strategy: str,
        direction: str,
        timeframe: str,
        spot_price: float,
        trigger: float,
        stop_loss: float,
        target_1: float,
        target_2: float,
        confidence: float = 80.0,
        option_contract: Optional[dict] = None,
        lots: int = 1,
        status: str = "ARMED",
        risk_reward_t1: float = 1.5,
        risk_reward_t2: float = 3.0,
        is_scalp: bool = False,
        signal_type: str = "INTRADAY",
    ) -> AuditTradeRecord:
        opt = option_contract or {}
        lot_sz = int(opt.get("lot_size", 75 if underlying == "NIFTY" else (30 if underlying == "BANKNIFTY" else 10)))
        qty = lots * lot_sz

        # Inherit from active FSM signal if already registered
        fsm_sig = None
        try:
            from app.signals.fsm import signal_fsm
            fsm_sig = signal_fsm.get(signal_id)
        except Exception as e:
            logger.debug("audit_fsm_inherit_lookup_failed", signal_id=signal_id, error=str(e)[:150])

        actual_is_scalp = is_scalp or (fsm_sig.is_scalp if fsm_sig else False)
        actual_sig_type = signal_type if signal_type != "INTRADAY" else (fsm_sig.signal_type if fsm_sig else "INTRADAY")
        actual_rr_t1 = risk_reward_t1 if risk_reward_t1 != 1.5 else (fsm_sig.risk_reward_t1 if fsm_sig else 1.5)
        actual_rr_t2 = risk_reward_t2 if risk_reward_t2 != 3.0 else (fsm_sig.risk_reward_t2 if fsm_sig else 3.0)

        rec = AuditTradeRecord(
            signal_id=signal_id,
            underlying=underlying,
            strategy=strategy,
            direction=direction,
            timeframe=timeframe,
            option_symbol=opt.get("broker_symbol") or opt.get("symbol"),
            option_type=opt.get("option_type", "CE" if "CALL" in direction else "PE"),
            option_strike=float(opt.get("strike", 0.0)) if opt.get("strike") else None,
            expiry=str(opt.get("expiry") or opt.get("expiry_date") or "") or None,
            lot_size=lot_sz,
            lots=lots,
            quantity=qty,
            spot_price_at_creation=spot_price,
            trigger_price=trigger,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            risk_points=abs(trigger - stop_loss),
            confidence=confidence,
            status="CONFIRMED" if status == "CONFIRMED" else "ARMED",
            risk_reward_t1=actual_rr_t1,
            risk_reward_t2=actual_rr_t2,
            is_scalp=actual_is_scalp,
            signal_type=actual_sig_type,
        )
        rec.state_history.append(
            AuditStateEvent(
                from_state="DETECTED",
                to_state=rec.status,
                market_price=spot_price,
                reason="SIGNAL_REGISTERED",
            )
        )
        self._trades[signal_id] = rec
        self._schedule_persist(rec)
        return rec

    def _schedule_persist(self, rec: AuditTradeRecord) -> None:
        """Safely schedule asynchronous upsert to Supabase PostgreSQL."""
        try:
            import asyncio
            from app.signals.signals_persistence import persist_executed_signal
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(persist_executed_signal(rec))
            except RuntimeError:
                pass
        except Exception as e:
            logger.warning("audit_schedule_persist_err", signal_id=getattr(rec, "signal_id", "unknown"), error=str(e))

    def record_state_transition(
        self,
        signal_id: str,
        to_state: str,
        market_price: Optional[float] = None,
        reason: str = "",
    ) -> Optional[AuditTradeRecord]:
        """Record lifecycle transition in AuditTradeRecord and sync to Supabase.

        Settled-guard: settled WON/LOST/CLOSED/VOID return ALREADY_SETTLED
        without history append (no overwrite of settled economics).
        """
        rec = self._trades.get(signal_id)
        now_ms = int(time.time() * 1000)
        if not rec:
            return None

        # Settled guard — return without history append.
        if rec.status in SETTLED_STATUSES:
            logger.debug("audit_already_settled_skip", signal_id=signal_id, status=rec.status, to_state=to_state)
            # Attach sentinel for callers that check settled-noop.
            try:
                rec.reconciliation_details = getattr(rec, "reconciliation_details", None)  # type: ignore[attr-defined]
            except Exception as e:
                logger.debug("audit_reconciliation_sentinel_failed", signal_id=signal_id, error=str(e)[:150])
            return rec

        from_state = rec.status
        # Guard: do not overwrite settled states or downgrade EXECUTED back to CONFIRMED
        if rec.status in ("WON", "LOST", "CLOSED") and to_state not in ("WON", "LOST", "CLOSED"):
            pass
        elif rec.status == "EXECUTED" and to_state == "CONFIRMED":
            pass
        else:
            rec.status = to_state
            # Store both FSM + ledger status.
            try:
                rec.fsm_state = AUDIT_TO_FSM_STATUS.get(to_state, to_state)
            except Exception as e:
                logger.debug("audit_fsm_state_mirror_failed", signal_id=signal_id, to_state=to_state, error=str(e)[:150])

        rec.updated_at_utc = now_ms
        if market_price is not None:
            is_opt = bool(rec.option_symbol or rec.option_type or rec.option_strike)
            if not (is_opt and market_price > 5000.0):
                rec.current_price = market_price
        if to_state in ("TARGET_1_HIT", "TARGET_2_HIT", "WON", "RUNNER_TIME_STOP_HIT"):
            rec.is_winner = True
        elif to_state in ("STOP_LOSS_HIT", "LOST", "TIME_STOP_HIT"):
            rec.is_winner = False

        rec.state_history.append(
            AuditStateEvent(
                timestamp_utc=now_ms,
                from_state=from_state,
                to_state=to_state,
                market_price=market_price,
                reason=reason or f"TRANSITION_TO_{to_state}",
            )
        )
        self._schedule_persist(rec)
        return rec

    def record_paper_executed(
        self,
        signal_id: str,
        paper_order_id: str,
        fill_price: float,
        quantity: int,
        lots: int,
        side: str = "BUY",
        margin_used: Optional[float] = None,
    ) -> Optional[AuditTradeRecord]:
        rec = self._trades.get(signal_id)
        now_ms = int(time.time() * 1000)
        if not rec:
            return None

        rec.paper_order_id = paper_order_id
        rec.paper_side = side
        rec.actual_fill_price = fill_price
        rec.quantity = quantity
        rec.lots = lots
        rec.executed_at_utc = now_ms
        if rec.option_symbol or (rec.option_strike and rec.option_type):
            # Slippage is only measurable against a real reference price for the
            # same contract. An option fill can never be compared to the index
            # trigger, and a Black-76 reference is not a market observation — so
            # with no chain mark the field stays unset instead of fabricated.
            from app.signals.option_marks import option_mark_registry
            mark = option_mark_registry.get_usable(rec.option_symbol, allow_model=False)
            rec.slippage_points = (
                round(abs(fill_price - float(mark.price)), 2)
                if mark is not None and mark.price is not None
                else None
            )
        else:
            rec.slippage_points = round(abs(fill_price - rec.trigger_price), 2)
        rec.margin_used = margin_used or (fill_price * quantity)
        rec.status = "EXECUTED"
        rec.updated_at_utc = now_ms

        rec.state_history.append(
            AuditStateEvent(
                timestamp_utc=now_ms,
                from_state="CONFIRMED",
                to_state="EXECUTED",
                market_price=fill_price,
                reason=f"PAPER_ORDER_FILLED {paper_order_id}",
            )
        )
        logger.info("audit_paper_executed", signal_id=signal_id, order_id=paper_order_id, fill_price=fill_price)

        # Asynchronously persist to Supabase
        self._schedule_persist(rec)
        return rec

    def update_live_quote(self, underlying: str, current_price: float) -> list[AuditTradeRecord]:
        """
        Recalculates mark-to-market unrealized PnL, point change, and live duration
        for all open signals/trades of the given underlying in real time.
        """
        now_ms = int(time.time() * 1000)
        from app.signals.contract_resolver import validate_underlying
        try:
            target_u = validate_underlying(underlying)
        except Exception:
            target_u = underlying.upper().strip()

        updated: list[AuditTradeRecord] = []

        # Single mark authority: entry, MTM, trigger and exit all price off the
        # same object so a chain entry fill is never MTM'd by a spot-derived model.
        from app.signals.option_marks import option_mark_service

        for rec in self._trades.values():
            try:
                rec_u = validate_underlying(rec.underlying)
            except Exception:
                rec_u = rec.underlying.upper().strip()

            if rec_u != target_u:
                continue

            if rec.status in ("ARMED", "TRIGGERED", "CONFIRMED", "EXECUTED", "TARGET_1_HIT"):
                curr_p = round(float(current_price), 2)
                side = (rec.paper_side or "BUY").upper()
                is_bullish = ("CALL" in rec.direction or "BULLISH" in rec.direction) and not ("PUT" in rec.direction or "BEARISH" in rec.direction)
                is_option = bool(rec.option_symbol or rec.option_type or rec.option_strike)

                if rec.status == "ARMED":
                    # No capital deployed: show no MTM. For option trades keep
                    # current_price empty so the UI never renders spot as a premium.
                    rec.current_price = None if is_option else curr_p
                    rec.unrealized_pnl_points = 0.0
                    rec.unrealized_pnl_inr = 0.0
                    rec.unrealized_pnl_pct = 0.0
                    rec.total_pnl_inr = 0.0
                    rec.is_winner = None
                else:
                    # No fill = no position = no MTM. Never fall back to the
                    # spot trigger as a fake premium entry (fabricates P&L).
                    if is_option and rec.actual_fill_price is None:
                        rec.current_price = None
                        rec.unrealized_pnl_points = None
                        rec.unrealized_pnl_inr = None
                        rec.unrealized_pnl_pct = None
                        rec.total_pnl_inr = None
                        rec.is_winner = None
                    else:
                        # Entry reference: fill price if executed, else trigger price
                        entry_price = rec.actual_fill_price or rec.trigger_price
                        qty = rec.quantity or (rec.lots * rec.lot_size)

                        _mtm_ok = True
                        if is_option:
                            # ── ONE MARK AUTHORITY ──
                            # Entry fill, MTM, trigger evaluation and exit must all
                            # price off the same object. Chain mark first (a real
                            # broker print), else a *labeled* Black-76 model mark,
                            # else fail closed. The old code recomputed a premium
                            # from spot here while the entry came from a chain
                            # quote — two bases, one record, drifting P&L.
                            # Fail closed: a model mark may NEVER price a live position.
                            mark = option_mark_service.mark_for_record(rec, spot=curr_p, allow_model=False)

                            if not mark.is_usable:
                                # Fail closed: no price, no P&L. Retaining the
                                # previous mark (stale) beats inventing one.
                                _mtm_ok = False
                                rec.mark_source = mark.source
                                rec.mark_age_ms = None
                                rec.mark_note = mark.note
                                rec.economics_unavailable = True
                                logger.warning(
                                    "economics_unavailable_mtm_skipped",
                                    signal_id=rec.signal_id,
                                    option_symbol=rec.option_symbol,
                                    note=str(mark.note or ""),
                                )
                            else:
                                # A spot-scale "fill" is corruption, not data. It
                                # is repaired from the SAME authority that prices
                                # the MTM, so both agree by construction.
                                if entry_price is None or entry_price > 5000.0:
                                    entry_price = mark.price
                                    rec.actual_fill_price = entry_price
                                    logger.warning(
                                        "fill_price_repaired_from_mark",
                                        signal_id=rec.signal_id,
                                        mark_source=mark.source,
                                        repaired=entry_price,
                                    )

                                # Display the premium, never the spot index price.
                                rec.current_price = round(float(mark.price), 2)
                                rec.mark_source = mark.source
                                rec.mark_age_ms = mark.age_ms()
                                rec.mark_note = mark.note
                                rec.economics_unavailable = False
                                pts_diff = (mark.price - entry_price) if side == "BUY" else (entry_price - mark.price)
                                if side == "BUY" and pts_diff < -entry_price:
                                    pts_diff = -entry_price
                        else:
                            rec.current_price = curr_p
                            rec.mark_source = "INDEX_SPOT"
                            rec.mark_age_ms = None
                            rec.mark_note = None
                            rec.economics_unavailable = False
                            pts_diff = (curr_p - entry_price) if is_bullish else (entry_price - curr_p)

                        if _mtm_ok:
                            unrealized_inr = round(pts_diff * qty, 2)
                            margin = rec.margin_used or (entry_price * qty)
                            if is_option and side == "BUY" and unrealized_inr < -margin:
                                unrealized_inr = -margin
                            unrealized_pct = round((unrealized_inr / margin * 100.0), 2) if margin > 0 else 0.0
                            if is_option and side == "BUY":
                                unrealized_pct = max(-100.0, unrealized_pct)

                            rec.unrealized_pnl_points = round(pts_diff, 2)
                            rec.unrealized_pnl_inr = unrealized_inr
                            rec.unrealized_pnl_pct = unrealized_pct
                            rec.total_pnl_inr = unrealized_inr
                            rec.is_winner = unrealized_inr > 0

                dur_s, dur_str = rec.compute_live_duration(now_ms)
                rec.live_duration_seconds = dur_s
                rec.live_duration_str = dur_str
                rec.holding_time_str = dur_str
                rec.holding_time_seconds = dur_s
                rec.updated_at_utc = now_ms
                updated.append(rec)

        return updated

    def update_live_quotes_batch(self, quotes: dict[str, float]) -> None:
        """Batch update open trades across multiple underlyings."""
        for u, price in quotes.items():
            if price and price > 0:
                self.update_live_quote(u, float(price))

    def get_open_option_symbols(self, underlying: Optional[str] = None) -> list[str]:
        """Collect all distinct option contract broker symbols currently open for MTM updates."""
        from app.signals.contract_resolver import validate_underlying
        target_u = None
        if underlying:
            try:
                target_u = validate_underlying(underlying)
            except Exception:
                target_u = underlying.upper().strip()

        symbols: set[str] = set()
        for rec in self._trades.values():
            if rec.status not in ("ARMED", "TRIGGERED", "CONFIRMED", "EXECUTED", "TARGET_1_HIT"):
                continue
            if target_u:
                try:
                    rec_u = validate_underlying(rec.underlying)
                except Exception:
                    rec_u = rec.underlying.upper().strip()
                if rec_u != target_u:
                    continue
            sym = str(rec.option_symbol or "").strip()
            if not sym:
                try:
                    from app.signals.live_contract_cache import live_contract_cache
                    from datetime import date
                    u = str(rec.underlying or "").upper()
                    strike = int(float(rec.option_strike or 0))
                    otype = str(rec.option_type or "").upper()
                    exp = rec.expiry
                    if exp and strike > 0 and otype in ("CE", "PE"):
                        exp_date = date.fromisoformat(str(exp)) if isinstance(exp, str) and len(str(exp)) == 10 else None
                        if exp_date:
                            info = live_contract_cache.lookup(u, exp_date, strike, otype)
                            if info and info.broker_symbol:
                                sym = info.broker_symbol
                                rec.option_symbol = sym
                except Exception as e:
                    logger.debug("audit_option_symbol_lookup_failed", signal_id=rec.signal_id, error=str(e)[:150])
            if sym:
                symbols.add(sym)
        return list(symbols)

    def sync_with_fsm(self, fsm_mgr: Any = None) -> None:
        """Ensure all active signals in FSM are mirrored in the audit ledger."""
        if fsm_mgr is None:
            try:
                from app.signals.fsm import signal_fsm
                fsm_mgr = signal_fsm
            except Exception:
                return

        for sig in fsm_mgr._signals.values():
            if sig.signal_id not in self._trades:
                rec = self.record_signal_created(
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
                    status=sig.fsm_state if sig.fsm_state in ("CONFIRMED", "ARMED") else "ARMED",
                )
                if sig.paper_order and sig.paper_order.get("status") == "FILLED":
                    fill_p = float(sig.paper_order.get("price") or sig.paper_order.get("fill_price") or sig.spot_price)
                    qty = int(sig.paper_order.get("quantity") or rec.quantity)
                    lots = int(sig.paper_order.get("lots") or rec.lots)
                    self.record_paper_executed(
                        signal_id=sig.signal_id,
                        paper_order_id=sig.paper_order.get("order_id", "ORD-SYNC"),
                        fill_price=fill_p,
                        quantity=qty,
                        lots=lots,
                        side=sig.paper_order.get("side", "BUY"),
                    )

    def sync_with_paper_service(self, paper_svc: Any = None) -> None:
        """Synchronize open positions from PaperTradingService with audit ledger.

        Join on signal_id/position_id/intent_id — never bare underlying.
        A bare underlying join (all NIFTY trades match one NIFTY position)
        cross-contaminates fills and fabricates P&L.
        """
        if paper_svc is None:
            try:
                from app.services.paper_service import paper_service
                paper_svc = paper_service
            except Exception:
                return

        for pos_id, pos in getattr(paper_svc, "_positions", {}).items():
            if not pos.is_open:
                continue
            pos_signal = getattr(pos, "signal_id", None)
            pos_order = getattr(pos, "order_id", None) or getattr(pos, "broker_order_id", None)
            for rec in self._trades.values():
                if rec.status not in ("CONFIRMED", "EXECUTED", "TRIGGERED", "ARMED", "TARGET_1_HIT"):
                    continue
                # Exact joins only.
                match = False
                if pos_signal and rec.signal_id == pos_signal:
                    match = True
                elif pos_order and rec.paper_order_id and rec.paper_order_id == pos_order:
                    match = True
                elif rec.option_symbol and getattr(pos, "symbol", None) and rec.option_symbol == pos.symbol:
                    # Symbol match alone is insufficient unless the position
                    # carries the same signal linkage or the ledger row is the
                    # unique open row for that symbol.
                    same_symbol_open = [r for r in self._trades.values()
                                        if r.option_symbol == pos.symbol and r.status in ("CONFIRMED", "EXECUTED", "TRIGGERED", "TARGET_1_HIT")]
                    if len(same_symbol_open) == 1 and same_symbol_open[0].signal_id == rec.signal_id:
                        match = True
                if not match:
                    continue
                rec.status = "EXECUTED"
                try:
                    rec.fsm_state = "CONFIRMED"
                except Exception as e:
                    logger.debug("audit_paper_sync_fsm_mirror_failed", signal_id=rec.signal_id, error=str(e)[:150])
                rec.actual_fill_price = pos.average_price
                # Never shrink the trade quantity to the position's residual
                # after a T1 partial. `record_square_off`'s gross fallback
                # prices the whole original position, and the reconciler net
                # (the canonical source) is quantity-independent, so rewriting
                # this field mid-life made the final booked PnL depend on
                # whether a sync happened to run between T1 and the exit.
                if int(pos.quantity or 0) >= int(rec.quantity or 0):
                    rec.quantity = pos.quantity
                rec.current_price = pos.ltp
                rec.unrealized_pnl_inr = pos.unrealized_pnl
                rec.total_pnl_inr = pos.unrealized_pnl
                break

    def seed_initial_audited_records_if_empty(self) -> None:
        """Disabled: Never seed fake or synthetic trades into the authoritative audit ledger."""
        # Clean up any leftover demo trades
        demo_ids = {"SIG-NIFTY-BKO-01", "SIG-BNF-TRP-02", "SIG-SNX-MRV-03", "SIG-NIFTY-ORB-04"}
        for did in demo_ids:
            self._trades.pop(did, None)
        return

    def get(self, signal_id: str) -> Optional[AuditTradeRecord]:
        with self._lock:
            return self._trades.get(signal_id)

    def void_trade(
        self,
        signal_id: str,
        reason: str = "VOID_CORRUPT_HISTORY",
        quarantine_economics: bool = False,
    ) -> bool:
        """Quarantine a trade: kept as evidence but excluded from every P&L
        aggregate and from the served ledger. Never deletes economics data —
        unless ``quarantine_economics`` is set for CORRUPT rows, where the
        untrustworthy values (spot-scale fill, catastrophic P&L, non-positive
        exit) are withdrawn so they can never be re-aggregated. The record
        itself is always kept."""
        with self._lock:
            rec = self._trades.get(signal_id)
            if not rec:
                return False
            now_ms = int(time.time() * 1000)
            from_state = rec.status
            rec.status = "VOID"
            rec.outcome_label = reason
            rec.is_winner = None
            rec.unrealized_pnl_inr = 0.0
            rec.unrealized_pnl_points = 0.0
            rec.unrealized_pnl_pct = 0.0
            if quarantine_economics:
                rec.actual_fill_price = None
                rec.actual_pnl_inr = None
                rec.actual_pnl_points = None
                rec.actual_pnl_pct = None
                rec.theoretical_pnl_inr = None
                rec.theoretical_pnl_points = None
                if rec.exit_price is not None and rec.exit_price <= 0.0:
                    rec.exit_price = None
                rec.economics_unavailable = True
                rec.total_pnl_inr = None
            else:
                rec.total_pnl_inr = rec.actual_pnl_inr
            rec.updated_at_utc = now_ms
            rec.state_history.append(
                AuditStateEvent(
                    timestamp_utc=now_ms,
                    from_state=from_state,
                    to_state="VOID",
                    market_price=rec.exit_price,
                    reason=reason,
                )
            )
        self._schedule_persist(rec)
        logger.info("audit_trade_voided", signal_id=signal_id, from_state=from_state, reason=reason)
        return True

    def delete_trade(self, signal_id: str) -> bool:
        """Delete trade record from memory and schedule deletion from Supabase."""
        with self._lock:
            if signal_id not in self._trades:
                return False
            del self._trades[signal_id]
        try:
            import asyncio
            from app.signals.signals_persistence import delete_persisted_signal
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(delete_persisted_signal(signal_id))
            except RuntimeError:
                pass
        except Exception as e:
            logger.debug("audit_delete_schedule_failed", signal_id=signal_id, error=str(e)[:150])
        logger.info("audit_trade_deleted", signal_id=signal_id)
        return True

    def list_trades(
        self,
        underlying: Optional[str] = None,
        strategy: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditTradeRecord]:
        trades = list(self._trades.values())
        if underlying and underlying != "ALL":
            trades = [t for t in trades if t.underlying == underlying.upper()]
        if strategy and strategy != "ALL":
            trades = [t for t in trades if t.strategy == strategy.upper()]
        if status and status != "ALL":
            trades = [t for t in trades if t.status == status.upper()]
        # Newest first
        trades.sort(key=lambda t: t.created_at_utc, reverse=True)
        return trades[:limit]

    def get_summary_metrics(self) -> dict[str, Any]:
        """Compute aggregated portfolio PnL and accuracy statistics including live unrealized MTM."""
        demo_ids = {"SIG-NIFTY-BKO-01", "SIG-BNF-TRP-02", "SIG-SNX-MRV-03", "SIG-NIFTY-ORB-04"}
        all_t = [
            t for t in self._trades.values()
            if not str(t.signal_id).lower().startswith(("sig-test-", "sig-wallet-", "test-", "sig-persist-sanitize"))
            and t.signal_id not in demo_ids
            and t.status != "VOID"
        ]
        closed_t = [
            t for t in all_t
            if t.status in ("WON", "LOST", "CLOSED", "TARGET_2_HIT", "STOP_LOSS_HIT", "RUNNER_TIME_STOP_HIT", "TIME_STOP_HIT")
        ]
        open_t = [t for t in all_t if t.status in ("ARMED", "TRIGGERED", "CONFIRMED", "EXECUTED", "TARGET_1_HIT")]

        def _trade_is_winner(t: AuditTradeRecord) -> bool:
            if t.is_winner is True:
                return True
            if t.is_winner is False:
                return False
            if t.status in ("TARGET_1_HIT", "TARGET_2_HIT", "WON", "RUNNER_TIME_STOP_HIT"):
                return True
            if (t.actual_pnl_inr or 0.0) > 0:
                return True
            return False

        def _trade_is_loser(t: AuditTradeRecord) -> bool:
            if t.is_winner is False:
                return True
            if t.is_winner is True:
                return False
            if t.status in ("STOP_LOSS_HIT", "LOST", "TIME_STOP_HIT"):
                return True
            if (t.actual_pnl_inr or 0.0) < 0:
                return True
            return False

        total_closed = len(closed_t)
        winners = [t for t in closed_t if _trade_is_winner(t)]
        losers = [t for t in closed_t if _trade_is_loser(t)]

        win_rate = round((len(winners) / total_closed * 100.0), 1) if total_closed > 0 else 0.0
        net_realized_pnl = round(sum(t.actual_pnl_inr or 0.0 for t in closed_t), 2)
        net_unrealized_pnl = round(sum(t.unrealized_pnl_inr or 0.0 for t in open_t), 2)
        total_pnl = round(net_realized_pnl + net_unrealized_pnl, 2)

        gross_profit = round(sum(t.actual_pnl_inr or 0.0 for t in winners), 2)
        gross_loss = round(abs(sum(t.actual_pnl_inr or 0.0 for t in losers)), 2)

        live_winners = [t for t in open_t if (t.unrealized_pnl_inr or 0.0) > 0]
        live_losers = [t for t in open_t if (t.unrealized_pnl_inr or 0.0) < 0]
        # Active exposure is ONLY capital committed to actually open/filled market positions.
        # ARMED signals have zero capital deployed (no order filled yet).
        open_executed_t = [t for t in all_t if t.status in ("EXECUTED", "TARGET_1_HIT", "TRIGGERED")]

        def _calc_active_exposure(t: AuditTradeRecord) -> float:
            is_opt = bool(t.option_symbol or t.option_type or t.option_strike)
            qty = t.quantity or (t.lots * t.lot_size)
            fill_p = t.actual_fill_price
            if is_opt:
                # No fabricated premium: an open option position with no real fill
                # contributes zero exposed capital rather than a guess.
                if fill_p is None or fill_p > 5000.0:
                    return 0.0
                return round(float(fill_p) * qty, 2)
            else:
                return round(float(fill_p or t.trigger_price or 0.0) * qty, 2)

        total_active_exposure = round(sum(_calc_active_exposure(t) for t in open_executed_t), 2)

        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)
        max_win = max([t.actual_pnl_inr or 0.0 for t in winners], default=0.0)
        max_loss = min([t.actual_pnl_inr or 0.0 for t in losers], default=0.0)

        avg_pnl = round(net_realized_pnl / total_closed, 2) if total_closed > 0 else 0.0
        avg_holding = round(sum(t.holding_time_seconds or 0 for t in closed_t) / total_closed, 0) if total_closed > 0 else 0

        # Strategy breakdown
        strat_breakdown: dict[str, dict] = {}
        for t in all_t:
            s_entry = strat_breakdown.setdefault(t.strategy, {"total": 0, "wins": 0, "losses": 0, "net_pnl": 0.0})
            s_entry["total"] += 1
            if _trade_is_winner(t):
                s_entry["wins"] += 1
            elif _trade_is_loser(t):
                s_entry["losses"] += 1
            s_pnl = t.actual_pnl_inr if t.actual_pnl_inr is not None else (t.unrealized_pnl_inr or 0.0)
            s_entry["net_pnl"] = round(s_entry["net_pnl"] + s_pnl, 2)

        for v in strat_breakdown.values():
            dec = v["wins"] + v["losses"]
            v["win_rate"] = round((v["wins"] / dec * 100.0), 1) if dec > 0 else 0.0

        # Underlying breakdown
        under_breakdown: dict[str, dict] = {}
        for t in all_t:
            u_entry = under_breakdown.setdefault(t.underlying, {"total": 0, "wins": 0, "losses": 0, "net_pnl": 0.0})
            u_entry["total"] += 1
            if _trade_is_winner(t):
                u_entry["wins"] += 1
            elif _trade_is_loser(t):
                u_entry["losses"] += 1
            s_pnl = t.actual_pnl_inr if t.actual_pnl_inr is not None else (t.unrealized_pnl_inr or 0.0)
            u_entry["net_pnl"] = round(u_entry["net_pnl"] + s_pnl, 2)

        for v in under_breakdown.values():
            dec = v["wins"] + v["losses"]
            v["win_rate"] = round((v["wins"] / dec * 100.0), 1) if dec > 0 else 0.0

        return {
            "total_signals_audited": len(all_t),
            "open_trades": len(open_t),
            "closed_trades": total_closed,
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "win_rate_pct": win_rate,
            "net_realized_pnl_inr": net_realized_pnl,
            "net_unrealized_pnl_inr": net_unrealized_pnl,
            "total_pnl_inr": total_pnl,
            "live_winning_trades": len(live_winners),
            "live_losing_trades": len(live_losers),
            "total_active_exposure_inr": total_active_exposure,
            "gross_profit_inr": gross_profit,
            "gross_loss_inr": gross_loss,
            "profit_factor": profit_factor,
            "max_win_inr": max_win,
            "max_loss_inr": max_loss,
            "avg_trade_pnl_inr": avg_pnl,
            "avg_holding_time_seconds": avg_holding,
            "strategy_breakdown": strat_breakdown,
            "underlying_breakdown": under_breakdown,
            "realtime_sync_ts": int(time.time() * 1000),
        }


signal_audit_ledger = SignalAuditLedger()


def flush() -> bool:
    """Flush ledger to local state + DB on shutdown (registered via atexit)."""
    try:
        from app.signals.signals_persistence import save_signals_state_local
        return bool(save_signals_state_local())
    except Exception:
        return False


try:
    import atexit as _atexit
    _atexit.register(flush)
except Exception as e:
    logger.debug("audit_atexit_register_failed", error=str(e)[:150])
