"""
Lot-Aware Realistic Paper Execution Adapter for Signal Centre
Models:
  - Dynamic lot sizing from InstrumentMaster
  - Bid-Ask spread impact & ATR slippage
  - Integration with app.services.paper_service
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Any
import structlog
from pydantic import BaseModel

from app.signals.contract_resolver import (
    calculate_position_sizing,
    chain_premium_of,
    resolve_sizing_for_contract,
    validate_underlying,
)
from app.signals.fsm import signal_fsm
from app.services.paper_service import paper_service, apply_friction
from app.models.paper import OrderPayload

logger = structlog.get_logger()

#: Price-domain OFF_DOMAIN: option premiums live <5000; index spot >5000.
#: A premium leg filled at spot scale (or vice versa) is the wrong instrument.
#: Same-domain fills must sit inside a 3% band of the chain mark.
OFF_DOMAIN_SPOT_THRESHOLD = 5000.0
OFF_DOMAIN_BAND_PCT = 0.03
#: Legacy alias (kept for compat; tightened from 10% to 3% band).
MAX_FILL_DEVIATION_FROM_CHAIN_MARK = 0.03

#: Intent TTL for PENDING orders (ms): stale PENDING auto-cancels to EXPIRED.
PENDING_INTENT_TTL_MS = 30_000


class SignalPaperExecutionResult(BaseModel):
    success: bool
    signal_id: str
    underlying: str
    strategy: str
    side: str
    quantity: int
    lots: int
    fill_price: float
    stop_loss: float
    target_1: float
    target_2: float
    order_id: str
    status: str
    message: str
    # P1 provenance: where the fill came from + chain mark at fill time.
    fill_source: str = "CHAIN"
    chain_mark_at_fill: float | None = None


class SignalPaperEngine:
    """
    Executes validated & confirmed signals in the paper trading portfolio.
    """

    async def execute_signal(
        self,
        signal_id: str,
        capital_override: Optional[float] = None,
        risk_percent: float = 2.0,
        lots_override: Optional[int] = None,
        quantity_override: Optional[int] = None,
        allow_closed_market: bool = False,
    ) -> SignalPaperExecutionResult:
        sig = signal_fsm.get(signal_id)
        if not sig:
            raise ValueError("Signal not found")

        u = validate_underlying(sig.underlying)
        opt = sig.option_contract or {}
        lot_size = int(opt.get("lot_size", 75 if u == "NIFTY" else (30 if u == "BANKNIFTY" else 10)))
        broker_sym = opt.get("broker_symbol", f"{u}_OPT")

        # Determine side
        side = "BUY"
        direction_label = "CE" if "CALL" in sig.direction else "PE"

        # ── Centralized Market Session Check ──
        # P1 SAFETY: never bypass session on execute — only close_signal_position
        # may allow closed-market square-offs. allow_closed_market is ignored here.
        from app.services.calendar_service import calendar_service
        perm = calendar_service.can_trade_now()
        if not perm.allowed:
            logger.warning("paper_execution_blocked_market_closed", signal_id=signal_id, reason=perm.reason)
            return SignalPaperExecutionResult(
                success=False,
                signal_id=signal_id,
                underlying=u,
                strategy=sig.strategy,
                side=f"BUY_{direction_label}",
                quantity=0,
                lots=0,
                fill_price=0.0,
                stop_loss=float(sig.stop_loss),
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                order_id="",
                status="REJECTED",
                message=f"MARKET_CLOSED: {perm.reason} (NSE trading hours: 09:15 - 15:30 IST)",
                fill_source="NONE",
                chain_mark_at_fill=None,
            )

        # Position Sizing — wallet-bound: size off live available margin, not initial capital.
        # This keeps risk-based sizing confined to what the wallet can actually deploy now
        # (initial_capital + realized + unrealized - used_margin).
        try:
            _summary = await paper_service.get_portfolio_summary()
            _live_available = float(_summary.available_margin)
        except Exception:
            _live_available = float(getattr(paper_service, "_initial_capital", 1000000.0))
        if capital_override and capital_override > 0:
            avail_cap = min(float(capital_override), _live_available)
        else:
            avail_cap = _live_available
        live_available_margin = _live_available

        raw_price = float(sig.spot_price)
        if raw_price <= 0:
            logger.warning("paper_execution_blocked_invalid_spot_price", signal_id=signal_id, spot=raw_price)
            return SignalPaperExecutionResult(
                success=False,
                signal_id=signal_id,
                underlying=u,
                strategy=sig.strategy,
                side=f"BUY_{direction_label}",
                quantity=0,
                lots=0,
                fill_price=0.0,
                stop_loss=float(sig.stop_loss),
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                order_id="",
                status="REJECTED",
                message="INVALID_PRICE: Spot price is non-positive",
            )

        # ─ Reference mark for the option premium ──
        # A REAL chain mark is the broker's truth; a Black-76 estimate is only
        # a labeled fallback. Either way the reference must sit on the same
        # tick grid as the fill, because the execution guard measures slippage
        # as |reference - fill| / fill. An unaligned chain mid (0.23 on a 0.05
        # tick) quantizes to a 0.25 fill, and comparing the two domains then
        # reports a phantom 8% "slippage" that rejects a perfectly tradeable
        # order purely on rounding - one tick on a low premium is a huge
        # percentage, so such contracts became unfillable for no real reason.
        #
        # Resolved BEFORE sizing so the option-buyer sizer and the fill price
        # share one premium reference. The mark gate itself stays fail-closed
        # below (a missing mark rejects the trade; no model price is a fill).
        from app.signals.fill_reconciler import option_fill_reconciler
        from app.signals.safety.decimal_types import normalize_price_to_tick
        tick_sz = opt.get("tick_size", "0.05") if isinstance(opt, dict) else "0.05"

        base_price = raw_price
        premium_mark_available = False
        if sig.option_contract:
            # Preference order is deliberate: the mark registry first (the exact
            # object the ledger later marks the position against, so entry and
            # valuation cannot drift), then the cached chain mid on the contract.
            # There is NO Black-76 substitute — a model price is not a fill.
            from app.signals.option_marks import option_mark_registry, option_mark_service

            mark = option_mark_registry.get_usable(broker_sym, allow_model=False)
            if mark is None or mark.price is None:
                try:
                    await option_mark_service.refresh_and_register([broker_sym])
                except Exception as me:
                    logger.warning("paper_execution_mark_fetch_failed", signal_id=signal_id, error=str(me)[:150])
                mark = option_mark_registry.get_usable(broker_sym, allow_model=False)

            if mark is not None and mark.price is not None:
                base_price = float(mark.price)
                premium_mark_available = True
            else:
                live_prem = chain_premium_of(sig.option_contract)
                if live_prem is not None:
                    base_price = float(live_prem)
                    premium_mark_available = True
            # Snap the reference onto the tradable grid before comparison.
            base_price = float(normalize_price_to_tick(base_price, tick_sz))

        # Sizing. Option legs (CE/PE per the contract dict) size in the PREMIUM
        # domain through the canonical option-buyer resolver: entry is the same
        # broker mark that prices the fill, and the stop is the signal stop
        # projected into premium terms. Passing the index-scale `sig.stop_loss`
        # against a premium entry made risk_points index-scale, so the math
        # produced 0 lots and the old `max(1, ...)` floor fabricated a 1-lot
        # trade. Non-option instruments keep the spot-domain
        # `calculate_position_sizing` path.
        if quantity_override and quantity_override > 0:
            final_qty = quantity_override
            final_lots = max(1, quantity_override // lot_size)
        elif lots_override and lots_override > 0:
            final_lots = lots_override
            final_qty = final_lots * lot_size
        else:
            _is_option_leg = False
            if sig.option_contract:
                _ctype = str(opt.get("option_type") or "").upper()
                _itype = str(opt.get("instrument_type") or "").upper()
                _is_option_leg = (
                    _ctype in ("CE", "PE", "CALL", "PUT")
                    or _itype in ("OPTION", "CE", "PE", "CALL", "PUT")
                    or "CE" in broker_sym.upper()
                    or "PE" in broker_sym.upper()
                )
            if _is_option_leg and premium_mark_available and base_price > 0:
                sizing = resolve_sizing_for_contract(
                    opt,
                    available_capital=avail_cap,
                    risk_percent=risk_percent,
                    option_entry_premium=base_price,
                    option_stop_premium=self._premium_stop_for(sig, base_price),
                    max_lots=50,
                )
                final_lots = max(0, int(sizing.get("lots") or 0))
                final_qty = final_lots * lot_size
                if final_lots < 1:
                    # No forced floor: the resolver's own risk-capital and 20%
                    # allocation gates just refused the smallest lot, so the
                    # wallet keeps its money instead of buying an oversized lot.
                    logger.warning(
                        "paper_execution_blocked_sizing",
                        signal_id=signal_id,
                        reason=sizing.get("reason"),
                        premium=base_price,
                    )
                    return SignalPaperExecutionResult(
                        success=False,
                        signal_id=signal_id,
                        underlying=u,
                        strategy=sig.strategy,
                        side=f"BUY_{direction_label}",
                        quantity=0,
                        lots=0,
                        fill_price=0.0,
                        stop_loss=float(sig.stop_loss),
                        target_1=float(sig.target_1),
                        target_2=float(sig.target_2),
                        order_id="",
                        status="REJECTED",
                        message=f"SIZING_REJECTED: {sizing.get('reason') or 'no lots fit the risk/allocation caps'}",
                        fill_source="NONE",
                        chain_mark_at_fill=float(base_price),
                    )
            else:
                # Spot-domain sizing: entry and stop share the spot scale. The
                # historical 1-lot floor stays; the wallet downsize loop below
                # and the INSUFFICIENT_FUNDS gate are the authority on whether
                # even that lot fits available margin.
                sizing = calculate_position_sizing(
                    available_capital=avail_cap,
                    risk_percent=risk_percent,
                    entry_price=base_price,
                    stop_loss=sig.stop_loss,
                    lot_size=lot_size,
                )
                final_lots = max(1, sizing["lots"])
                final_qty = final_lots * lot_size

        # ── FAIL CLOSED: a fill requires a real broker price ──
        if sig.option_contract and not premium_mark_available:
            logger.warning(
                "paper_execution_blocked_no_chain_mark",
                signal_id=signal_id,
                broker_symbol=broker_sym,
            )
            return SignalPaperExecutionResult(
                success=False,
                signal_id=signal_id,
                underlying=u,
                strategy=sig.strategy,
                side=f"BUY_{direction_label}",
                quantity=final_qty,
                lots=final_lots,
                fill_price=0.0,
                stop_loss=float(sig.stop_loss),
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                order_id="",
                status="REJECTED",
                message=(
                    f"CHAIN_MARK_UNAVAILABLE: no live FYERS quote for {broker_sym}. "
                    "Trade skipped — no model price is used to fill."
                ),
            )

        # Estimate the fill with the SAME friction the paper service applies
        # (SPREAD_BPS + SLIPPAGE_BPS), then snap to the contract's tick grid the
        # execution guard validates against. Previously this used an inline
        # 5 bps estimate while the service filled at 15 bps, so the guard
        # measured slippage against a price the ledger would never see.
        fill_price = float(normalize_price_to_tick(apply_friction(base_price, "BUY"), tick_sz))
        if fill_price <= 0:
            return SignalPaperExecutionResult(
                success=False,
                signal_id=signal_id,
                underlying=u,
                strategy=sig.strategy,
                side=f"BUY_{direction_label}",
                quantity=0,
                lots=0,
                fill_price=0.0,
                stop_loss=float(sig.stop_loss),
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                order_id="",
                status="REJECTED",
                message="INVALID_PRICE: Fill price is non-positive",
            )

        # ── Wallet limit: confine trade to available balance, auto-downsize to 1 lot ──
        # No per-trade % cap (full wallet usable), but required margin must fit live
        # available_margin. If requested lots don't fit, step down to the largest
        # affordable lots. If even 1 lot doesn't fit, reject with INSUFFICIENT_FUNDS.
        from app.quant.margin import calculate_required_margin as _calc_margin

        requested_lots = final_lots
        try:
            _summary = await paper_service.get_portfolio_summary()
            live_available_margin = float(_summary.available_margin)
        except Exception:
            pass
        inst_type = "OPTION_BUY" if ("CE" in broker_sym or "PE" in broker_sym) else "FUTURES"
        req_margin = _calc_margin(
            instrument_type=inst_type,  # type: ignore[arg-type]
            underlying=u,
            price=fill_price,
            quantity=final_qty,
            is_hedged=False,
        )
        while req_margin > live_available_margin and final_lots > 1:
            final_lots -= 1
            final_qty = final_lots * lot_size
            req_margin = _calc_margin(
                instrument_type=inst_type,  # type: ignore[arg-type]
                underlying=u,
                price=fill_price,
                quantity=final_qty,
                is_hedged=False,
            )
        if req_margin > live_available_margin:
            logger.warning(
                "paper_execution_blocked_insufficient_funds",
                signal_id=signal_id,
                required=req_margin,
                available=live_available_margin,
            )
            return SignalPaperExecutionResult(
                success=False,
                signal_id=signal_id,
                underlying=u,
                strategy=sig.strategy,
                side=f"BUY_{direction_label}",
                quantity=final_qty,
                lots=final_lots,
                fill_price=0.0,
                stop_loss=float(sig.stop_loss),
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                order_id="",
                status="REJECTED",
                message=(
                    f"INSUFFICIENT_FUNDS: Required ₹{req_margin:,.2f} for {final_lots} lot(s), "
                    f"Available ₹{live_available_margin:,.2f}. Trade skipped — confined to wallet balance."
                ),
            )
        downsized = final_lots < requested_lots
        if downsized:
            logger.info(
                "paper_execution_downsized_to_wallet",
                signal_id=signal_id,
                requested_lots=requested_lots,
                final_lots=final_lots,
                required=req_margin,
                available=live_available_margin,
            )

        # ── v3.0 Execution Guard & Deterministic Intent ──
        from app.signals.execution_intent import (
            make_execution_intent_id,
            make_fyers_order_tag,
            ExecutionIntent,
            IntentState,
            intent_ledger,
        )
        from app.signals.safety.execution_guard import final_execution_guard
        from app.signals.position import Position, position_registry

        # The id is a function of (signal_id, version, action, quantity, side,
        # symbol) ONLY — the live quote is deliberately excluded, so a retry
        # after the mark moves maps to the same intent (and the same
        # client_order_id) instead of minting a fresh one and double-filling.
        intent_id = make_execution_intent_id(
            signal_id=sig.signal_id,
            signal_version=getattr(sig, "strategy_version", 1),
            action=f"BUY_{direction_label}",
            position_id="",
            trigger_version=1,
            side=side,
            symbol=broker_sym,
            quantity=final_qty,
        )
        fyers_tag = make_fyers_order_tag(intent_id)

        # Check existing intent for duplicate dispatch (guard-14 ledger lookup)
        existing_intent = intent_ledger.get(intent_id)
        if existing_intent and existing_intent.state in (IntentState.SUBMITTED, IntentState.FILLED, IntentState.PARTIALLY_FILLED):
            # A FILLED intent is replayed as the original success: the broker
            # order id and fill price are immutable, and re-dispatching (or
            # re-registering the position) would double the book. Non-filled
            # in-flight intents keep the historical DUPLICATE_ORDER rejection.
            if existing_intent.state == IntentState.FILLED:
                replay = self._replay_filled_intent(existing_intent, sig, u, direction_label, lot_size)
                if replay is not None:
                    logger.info(
                        "execution_intent_duplicate_replayed",
                        intent_id=intent_id,
                        signal_id=signal_id,
                        order_id=replay.order_id,
                    )
                    return replay
            logger.warning("execution_intent_duplicate_rejected", intent_id=intent_id, signal_id=signal_id)
            return SignalPaperExecutionResult(
                success=False,
                signal_id=signal_id,
                underlying=u,
                strategy=sig.strategy,
                side=f"BUY_{direction_label}",
                quantity=final_qty,
                lots=final_lots,
                fill_price=0.0,
                stop_loss=float(sig.stop_loss),
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                order_id="",
                status="REJECTED",
                message=f"DUPLICATE_ORDER: Intent {intent_id} already submitted or filled",
                fill_source="NONE",
                chain_mark_at_fill=float(base_price),
            )

        # Run 15-check hierarchical execution guard (fail-closed defaults)
        try:
            from app.signals.safety.clocks import get_event_clock as _gec
            _drift = _gec(u).metrics.drift_ms
        except Exception:
            _drift = 0.0
        try:
            from app.signals.safety.feed_health_monitor import feed_health_monitor as _fhm
            _tel = _fhm.get_telemetry()
            _feed = "HEALTHY" if str(_tel.get("status")) == "LIVE" else str(_tel.get("status"))
            if _feed in ("CLOSED", "AUTH_REQUIRED", "CHAIN_UNAVAILABLE", "SYNCING"):
                from app.signals.safety.feed_circuit import feed_circuit as _fc
                _feed = "HEALTHY" if not _fc.is_degraded(u) else "FEED_DEGRADED"
        except Exception:
            _feed = "HEALTHY"
        guard_res = final_execution_guard(
            signal=sig,
            execution_intent_id=intent_id,
            order_price=fill_price,
            order_quantity=final_qty,
            latest_price=base_price,
            feed_health=_feed,
            market_session_state="OPEN" if perm.allowed else "CLOSED",
            contract_spec=sig.option_contract,
            max_slippage_pct=0.5,
            risk_approved=True,
            clock_drift_ms=float(_drift) if _drift is not None else 0.0,
            allow_closed_market=False,
            audit_available=True,
            db_available=True,
        )
        if not guard_res.passed:
            logger.warning("execution_guard_rejected", signal_id=signal_id, reason=guard_res.reason, check=guard_res.failed_check)
            return SignalPaperExecutionResult(
                success=False,
                signal_id=signal_id,
                underlying=u,
                strategy=sig.strategy,
                side=f"BUY_{direction_label}",
                quantity=final_qty,
                lots=final_lots,
                fill_price=0.0,
                stop_loss=float(sig.stop_loss),
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                order_id="",
                status="GUARD_REJECTED",
                message=f"GUARD_REJECTED: {guard_res.reason}",
            )

        # Register intent with GUARD_PASSED state
        current_intent = ExecutionIntent(
            execution_intent_id=intent_id,
            signal_id=sig.signal_id,
            signal_version=getattr(sig, "strategy_version", 1),
            action=f"BUY_{direction_label}",
            state=IntentState.GUARD_PASSED,
            broker_client_order_id=fyers_tag,
            instrument_symbol=broker_sym,
            side=side,
            intended_price=Decimal(str(fill_price)),
            intended_quantity=final_qty,
            guard_snapshot=guard_res.to_dict(),
        )
        intent_ledger.register(current_intent)
        sig.execution_intent_id = intent_id

        # Place order into Paper Trading Service (final hard safety boundary).
        # Idempotency: retrying the same signal returns the original fill
        # instead of doubling the position. The service prefers the live
        # quote when available; `price` is only the fallback estimate.
        current_intent.transition_to(IntentState.SUBMITTED, reason="DISPATCHED_TO_PAPER_SERVICE")
        order_payload = OrderPayload(
            symbol=broker_sym,
            underlying=u,
            side=side,
            order_type="MARKET",
            product="INTRADAY",
            quantity=final_qty,
            price=fill_price,
            client_order_id=fyers_tag,
        )
        paper_order = await paper_service.place_order(order_payload, allow_closed_market=False)

        if paper_order.status == "PENDING":
            # Intent TTL/cancel for PENDING: stale PENDING auto-expires.
            import time as _t
            _age_ms = 0
            try:
                _age_ms = int(_t.time() * 1000) - int(getattr(current_intent, "created_at_utc", int(_t.time() * 1000)))
            except Exception:
                _age_ms = 0
            if _age_ms > PENDING_INTENT_TTL_MS:
                try:
                    current_intent.transition_to(IntentState.EXPIRED, reason="PENDING_TTL_EXCEEDED")
                except Exception:
                    pass
            logger.warning("paper_order_unexpected_pending", signal_id=signal_id, order_id=paper_order.order_id)
            return SignalPaperExecutionResult(
                success=False,
                signal_id=signal_id,
                underlying=u,
                strategy=sig.strategy,
                side=f"BUY_{direction_label}",
                quantity=final_qty,
                lots=final_lots,
                fill_price=0.0,
                stop_loss=float(sig.stop_loss),
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                order_id=paper_order.order_id,
                status="PENDING",
                message="Order is resting (PENDING) — market has not touched it yet",
                fill_source="CHAIN",
                chain_mark_at_fill=float(base_price) if 'base_price' in locals() else None,
            )

        if paper_order.status == "REJECTED":
            logger.warning("paper_order_rejected_by_service", signal_id=signal_id, reason=paper_order.rejection_reason)
            return SignalPaperExecutionResult(
                success=False,
                signal_id=signal_id,
                underlying=u,
                strategy=sig.strategy,
                side=f"BUY_{direction_label}",
                quantity=final_qty,
                lots=final_lots,
                fill_price=0.0,
                stop_loss=float(sig.stop_loss),
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                order_id=paper_order.order_id,
                status="REJECTED",
                message=paper_order.rejection_reason or "Order rejected by paper service",
            )

        # ── Fill sanity: the service must have priced the same instrument ──
        # The paper service re-prices MARKET orders from its own live quote, and
        # its option path is supposed to consult the option chain (never the
        # underlying spot). If that ever regresses, or a caller hands it a symbol
        # it misresolves, it would return an index-scale number for a premium leg
        # and the ledger would book economics off the wrong instrument entirely.
        # Reject rather than reconcile: the service has already recorded this
        # fill against its own position, so accepting a different price here
        # would leave the portfolio and the audit ledger disagreeing.
        service_fill = float(paper_order.fill_price or 0.0)
        # Tightened OFF_DOMAIN: price-domain check (>5000) + 3% band.
        if sig.option_contract and service_fill > 0 and base_price > 0:
            _off_domain = ((service_fill > OFF_DOMAIN_SPOT_THRESHOLD) != (base_price > OFF_DOMAIN_SPOT_THRESHOLD))
            _dev = abs(service_fill - base_price) / base_price if base_price else 0.0
            if _off_domain or _dev > OFF_DOMAIN_BAND_PCT:
                logger.error(
                    "paper_fill_rejected_off_domain",
                    signal_id=signal_id,
                    broker_symbol=broker_sym,
                    chain_mark=base_price,
                    service_fill=service_fill,
                    deviation_pct=round(_dev * 100.0, 1),
                    off_domain=_off_domain,
                )
                return SignalPaperExecutionResult(
                    success=False,
                    signal_id=signal_id,
                    underlying=u,
                    strategy=sig.strategy,
                    side=f"BUY_{direction_label}",
                    quantity=final_qty,
                    lots=final_lots,
                    fill_price=0.0,
                    stop_loss=float(sig.stop_loss),
                    target_1=float(sig.target_1),
                    target_2=float(sig.target_2),
                    order_id=paper_order.order_id,
                    status="REJECTED",
                    message=(
                        f"OFF_DOMAIN_FILL: service filled {broker_sym} at ₹{service_fill:,.2f} "
                        f"against chain mark ₹{base_price:,.2f} ({_dev * 100.0:.1f}% off). "
                        "Not the same instrument — trade skipped."
                    ),
                    fill_source="CHAIN",
                    chain_mark_at_fill=float(base_price),
                )

        # Update FSM with order details — trust the service's actual fill
        # (live quote + friction) over this engine's pre-trade estimate, now
        # that it is confirmed to be the same instrument as the chain mark.
        actual_fill = float(paper_order.fill_price or fill_price)
        sig.paper_order = paper_order.model_dump()
        sig.actual_fill_price = Decimal(str(actual_fill))
        sig.entry_price = Decimal(str(actual_fill))
        sig.intended_qty = Decimal(str(final_qty))
        sig.remaining_qty = Decimal(str(final_qty))
        sig.lots = final_lots
        sig.quantity = final_qty

        # v3.0 Update Intent & Register Position
        current_intent.actual_fill_price = Decimal(str(actual_fill))
        current_intent.filled_quantity = final_qty
        current_intent.broker_order_id = paper_order.order_id
        current_intent.transition_to(IntentState.FILLED, reason="PAPER_ORDER_FILLED")

        new_pos = Position(
            signal_id=sig.signal_id,
            execution_intent_id=current_intent.execution_intent_id,
            broker_order_id=paper_order.order_id,
            underlying=u,
            instrument_symbol=broker_sym,
            side=side,
            lot_size=lot_size,
            entry_price=Decimal(str(actual_fill)),
            entry_quantity=final_qty,
            remaining_quantity=final_qty,
            t1_price=sig.target_1,
        )
        position_registry.register(new_pos)
        sig.position_id = new_pos.position_id

        # Register in Option Fill Reconciler
        try:
            from app.signals.fill_reconciler import option_fill_reconciler
            lot_sz = 75 if u == "NIFTY" else (30 if u == "BANKNIFTY" else 10)
            option_fill_reconciler.reconcile_entry(sig, actual_fill, final_qty, lot_sz)
        except Exception as re_err:
            logger.warning("reconcile_entry_init_failed", signal_id=signal_id, error=str(re_err))

        # Record fill provenance.
        try:
            if isinstance(sig.paper_order, dict):
                sig.paper_order["fill_source"] = "CHAIN"
                sig.paper_order["chain_mark_at_fill"] = float(base_price)
        except Exception:
            pass

        if sig.fsm_state == "TRIGGERED":
            signal_fsm.transition(sig.signal_id, "CONFIRMED", market_price=Decimal(str(actual_fill)), reason="PAPER_TRADE_EXECUTED",
                                  guard_snapshot={"trigger_proof": True, "paper_receipt": paper_order.order_id})
        elif sig.fsm_state in ("DETECTED", "VALIDATED", "ARMED"):
            # No skip edges: must pass through TRIGGERED first.
            ok_t, _ = signal_fsm.transition(sig.signal_id, "TRIGGERED", market_price=Decimal(str(actual_fill)), reason="PAPER_TRADE_TRIGGER_PROOF",
                                            guard_snapshot={"trigger_proof": True})
            if ok_t:
                signal_fsm.transition(sig.signal_id, "CONFIRMED", market_price=Decimal(str(actual_fill)), reason="PAPER_TRADE_EXECUTED",
                                      guard_snapshot={"trigger_proof": True, "paper_receipt": paper_order.order_id})

        # Record into Signal Audit Ledger
        try:
            from app.signals.audit_ledger import signal_audit_ledger
            # Ensure trade is registered in ledger first
            if not signal_audit_ledger.get(signal_id):
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
                    lots=final_lots,
                    status="CONFIRMED",
                )
            signal_audit_ledger.record_paper_executed(
                signal_id=signal_id,
                paper_order_id=paper_order.order_id,
                fill_price=actual_fill,
                quantity=final_qty,
                lots=final_lots,
                side=side,
                margin_used=actual_fill * final_qty,
            )
        except Exception as ae:
            logger.warning("audit_record_paper_failed", error=str(ae))

        logger.info("signal_paper_executed", signal_id=signal_id, order_id=paper_order.order_id, lots=final_lots, qty=final_qty)

        return SignalPaperExecutionResult(
            success=True,
            signal_id=signal_id,
            underlying=u,
            strategy=sig.strategy,
            side=f"BUY_{direction_label}",
            quantity=final_qty,
            lots=final_lots,
            fill_price=actual_fill,
            stop_loss=float(sig.stop_loss),
            target_1=float(sig.target_1),
            target_2=float(sig.target_2),
            order_id=paper_order.order_id,
            status=paper_order.status,
            message=(
                f"Filled {final_lots} Lots ({final_qty} Qty) {broker_sym} @ ₹{actual_fill:,.2f}"
                + (f" (downsized from {requested_lots} lot(s) to fit wallet ₹{live_available_margin:,.2f})" if downsized else "")
            ),
            fill_source="CHAIN",
            chain_mark_at_fill=float(base_price),
        )

    @staticmethod
    def _premium_stop_for(sig: Any, entry_premium: float) -> Optional[float]:
        """Project a signal's stop into premium terms for option-buyer sizing.

        Uses the canonical ``resolve_premium_risk_points`` (explicit premium
        stop > delta-gamma projection off the spot stop > conservative
        fallback). Returns None when no positive premium stop can be derived so
        the option-buyer resolver applies its own 35%-of-premium default.
        """
        try:
            from app.signals.transaction_costs import resolve_premium_risk_points

            try:
                spot_risk = abs(float(sig.trigger) - float(sig.stop_loss))
            except Exception:
                spot_risk = 0.0
            risk_pts = float(resolve_premium_risk_points(sig, float(entry_premium), spot_risk))
            if 0.0 < risk_pts < float(entry_premium):
                return round(float(entry_premium) - risk_pts, 4)
        except Exception:
            pass
        return None

    @staticmethod
    def _replay_filled_intent(
        existing_intent: Any,
        sig: Any,
        underlying: str,
        direction_label: str,
        lot_size: int,
    ) -> Optional[SignalPaperExecutionResult]:
        """Rebuild the original success result for an already-FILLED intent.

        Source preference: the paper service order (live state), then the
        persisted intent ledger record, then the signal's own ``paper_order`` /
        registered Position. Returns None when no filled state can be proven,
        in which case the caller keeps the historical duplicate rejection.
        """
        fill_price = 0.0
        quantity = 0
        order_id = ""
        # The engine's success results label every fill CHAIN (the mark that
        # priced it); replay must return the same provenance as the original.
        fill_source = "CHAIN"
        chain_mark = None

        # 1. Paper service: the authoritative order record for this client id.
        try:
            client_id = str(existing_intent.broker_client_order_id or "")
            broker_id = str(existing_intent.broker_order_id or "")
            for order in paper_service.get_orders():
                if str(getattr(order, "status", "")) != "FILLED":
                    continue
                matched = client_id and str(getattr(order, "client_order_id", "") or "") == client_id
                matched = matched or (broker_id and str(getattr(order, "order_id", "") or "") == broker_id)
                if matched:
                    fill_price = float(order.fill_price or 0.0)
                    quantity = int(order.quantity or 0)
                    order_id = str(order.order_id or "")
                    break
        except Exception:
            pass

        # 2. The persisted intent record (survives a service restart).
        if fill_price <= 0:
            try:
                fill_price = float(existing_intent.actual_fill_price or 0.0)
            except Exception:
                fill_price = 0.0
        if quantity <= 0:
            try:
                quantity = int(existing_intent.filled_quantity or 0)
            except Exception:
                quantity = 0
        if not order_id:
            order_id = str(existing_intent.broker_order_id or "")

        # 3. FSM paper_order / registered Position.
        po = sig.paper_order if isinstance(getattr(sig, "paper_order", None), dict) else None
        if po:
            if fill_price <= 0:
                try:
                    fill_price = float(po.get("fill_price") or 0.0)
                except Exception:
                    fill_price = 0.0
            if quantity <= 0:
                try:
                    quantity = int(po.get("quantity") or 0)
                except Exception:
                    quantity = 0
            if not order_id:
                order_id = str(po.get("order_id") or "")
            if chain_mark is None:
                try:
                    _cm = po.get("chain_mark_at_fill")
                    chain_mark = float(_cm) if _cm is not None else None
                except Exception:
                    chain_mark = None
        if fill_price <= 0 or quantity <= 0 or not order_id:
            try:
                from app.signals.position import position_registry

                pos = position_registry.get_by_signal(sig.signal_id)
                if pos is not None:
                    if fill_price <= 0:
                        fill_price = float(pos.entry_price or 0.0)
                    if quantity <= 0:
                        quantity = int(pos.entry_quantity or 0)
                    if not order_id:
                        order_id = str(pos.broker_order_id or "")
            except Exception:
                pass

        if fill_price <= 0 or quantity <= 0 or not order_id:
            return None

        lots = quantity // lot_size if lot_size > 0 else 0
        if lots < 1:
            lots = max(1, int(getattr(sig, "lots", 0) or 0))
        return SignalPaperExecutionResult(
            success=True,
            signal_id=sig.signal_id,
            underlying=underlying,
            strategy=sig.strategy,
            side=f"BUY_{direction_label}",
            quantity=quantity,
            lots=lots,
            fill_price=fill_price,
            stop_loss=float(sig.stop_loss),
            target_1=float(sig.target_1),
            target_2=float(sig.target_2),
            order_id=order_id,
            status="FILLED",
            message=(
                f"DUPLICATE_REPLAY: intent {existing_intent.execution_intent_id} already filled "
                f"as {order_id} ({lots} Lots / {quantity} Qty @ ₹{fill_price:,.2f})"
            ),
            fill_source=fill_source or "CHAIN",
            chain_mark_at_fill=chain_mark,
        )

    async def close_signal_position(
        self,
        signal_id: str,
        exit_price: Optional[float] = None,
        reason: str = "TARGET_HIT",
        quantity_to_close: Optional[int] = None,
        allow_closed_market: bool = False,
    ) -> Optional[Any]:
        """
        Closes full or partial open paper position for a signal and records the actual profit and loss audit.

        Settlement is gated on the paper service actually filling the exit
        order: a rejected/unfilled exit leaves the virtual position, the audit
        record and the signal FSM untouched. An already-settled audit row
        short-circuits to a no-op (close-once).
        """
        sig = signal_fsm.get(signal_id)
        if not sig or not sig.paper_order:
            return None

        from app.signals.audit_ledger import SETTLED_STATUSES, signal_audit_ledger

        broker_sym = sig.paper_order.get("symbol")
        qty = sig.paper_order.get("quantity")
        if not broker_sym or not qty:
            return None

        # ── Close-once: a settled audit row is terminal. No exit order, no
        # audit rewrite, no registry mutation. (record_square_off is guarded
        # too, but this avoids even dispatching an exit for a settled signal.)
        _audit_rec = signal_audit_ledger.get(signal_id)
        if _audit_rec is not None and _audit_rec.status in SETTLED_STATUSES:
            logger.info("paper_close_already_settled", signal_id=signal_id, status=_audit_rec.status)
            return _audit_rec

        pos_id = f"{broker_sym}_INTRADAY"
        # Locked, side-effect-free read under the service lock (no network MTM
        # during settlement). Replaces direct `paper_service._positions` access.
        pos = await paper_service.get_position_snapshot(pos_id)

        # Resolve exit price if missing — prefer the live position LTP
        # (VirtualPosition.ltp; there is no `current_price` field).
        # FAIL CLOSED: when neither the position LTP nor a fresh broker mark
        # exists the audit-only path settles flat (entry fill) with
        # economics_unavailable + NO_MARK; with an open virtual position the
        # exit order is dispatched and the settlement gate below refuses to
        # book anything unless the service confirms a FILLED exit.
        _flat_no_mark = False
        if exit_price is None:
            live_ltp = getattr(pos, "ltp", None) if pos else None
            if live_ltp and float(live_ltp) > 0:
                exit_price = float(live_ltp)
            elif sig.option_contract:
                from app.signals.option_marks import option_mark_registry
                mark = option_mark_registry.get_usable(broker_sym, allow_model=False)
                if mark is not None and mark.price is not None:
                    exit_price = float(mark.price)
                else:
                    entry_ref = float(sig.actual_fill_price or sig.entry_price or 0.0)
                    logger.warning(
                        "exit_price_unavailable_settling_flat",
                        signal_id=signal_id,
                        broker_symbol=broker_sym,
                        entry_ref=entry_ref,
                    )
                    exit_price = entry_ref
                    _flat_no_mark = True
            else:
                exit_price = float(sig.actual_fill_price or sig.trigger or 0.0)

        # Allow closed market execution for square-off / cleanup reasons
        permit_closed = allow_closed_market or reason in (
            "MARKET_CLOSED", "EOD_SQUAREOFF", "DELETED_BY_USER", "TIME_STOP_EXCEEDED", "RUNNER_TTL_EXCEEDED"
        )

        # Partial only when this close leaves residual quantity open (e.g. 50%
        # staged T1 on a multi-lot position). A single-lot T1 closes everything
        # and must settle via record_square_off, not linger as a runner.
        # Reference quantity prefers the live paper position, else the audit record.
        is_partial = False
        if pos is not None and pos.is_open:
            exit_side = "SELL" if pos.side == "BUY" else "BUY"
            pos_qty_before = pos.quantity
            final_close_qty = quantity_to_close if (quantity_to_close and quantity_to_close <= pos.quantity) else pos.quantity
            if reason == "TARGET_1_HIT" and final_close_qty < pos_qty_before:
                is_partial = True

            exit_payload = OrderPayload(
                symbol=pos.symbol,
                underlying=pos.underlying,
                side=exit_side,
                order_type="MARKET",
                product=pos.product,
                quantity=final_close_qty,
                price=exit_price,
            )
            exit_order = await paper_service.place_order(exit_payload, allow_closed_market=permit_closed)

            # ── Settlement gate: only a confirmed fill books a close. ──
            # A rejected/unfilled exit must not settle the audit row or close
            # the registry position while the virtual position remains open.
            if exit_order.status != "FILLED":
                logger.warning(
                    "paper_exit_not_filled_settlement_skipped",
                    signal_id=signal_id,
                    symbol=broker_sym,
                    order_id=exit_order.order_id,
                    status=exit_order.status,
                    detail=exit_order.rejection_reason,
                )
                return self._exit_not_filled_result(sig, exit_order)

            logger.info("paper_position_closed", signal_id=signal_id, symbol=broker_sym, exit_price=exit_price, qty=final_close_qty, reason=reason)
        elif reason == "TARGET_1_HIT" and quantity_to_close:
            audit_ref = signal_audit_ledger.get(signal_id)
            ref_qty = (audit_ref.quantity or 0) if audit_ref else 0
            if quantity_to_close < ref_qty:
                is_partial = True

        if is_partial:
            rec = signal_audit_ledger.record_state_transition(
                signal_id=signal_id,
                to_state="TARGET_1_HIT",
                market_price=exit_price,
                reason=reason,
            )
        else:
            _exit_reason = "NO_MARK" if _flat_no_mark else reason
            rec = signal_audit_ledger.record_square_off(
                signal_id=signal_id,
                exit_price=exit_price,
                exit_reason=_exit_reason,
            )
            # Flat settlements set economics_unavailable + NO_MARK.
            try:
                if _flat_no_mark and rec is not None:
                    rec.economics_unavailable = True
                    if not rec.exit_reason or rec.exit_reason == reason:
                        rec.exit_reason = "NO_MARK"
            except Exception:
                pass

        # ── Signal-domain Position lifecycle ──
        # Mirror a successful full close into the position registry so the
        # registered Position and the portfolio Greeks ledger stop carrying
        # exposure for a settled trade. close_position() is idempotent; T1
        # partial closes keep the runner Position open by design.
        if not is_partial:
            try:
                from app.signals.position import position_registry
                reg_pos = position_registry.get(sig.position_id) if sig.position_id else None
                if reg_pos is None:
                    reg_pos = position_registry.get_by_signal(signal_id)
                if reg_pos is not None:
                    position_registry.close_position(reg_pos.position_id, reason=reason)
            except Exception as pe:
                logger.warning("position_registry_close_failed", signal_id=signal_id, error=str(pe))
        return rec

    def _exit_not_filled_result(self, sig: Any, order: Any) -> SignalPaperExecutionResult:
        """Explicit failure for a close whose exit order did not fill.

        Preserves the service's own status/rejection vocabulary so callers can
        surface the exact boundary rejection while the virtual position, the
        audit record and the signal FSM remain exactly as they were.
        """
        qty = int(getattr(order, "quantity", 0) or 0)
        lots = int(getattr(sig, "lots", 0) or 0)
        if lots <= 0:
            lot_size = int((sig.option_contract or {}).get("lot_size", 0) or 0)
            lots = max(1, qty // lot_size) if lot_size > 0 else 0
        status = str(getattr(order, "status", "REJECTED") or "REJECTED")
        return SignalPaperExecutionResult(
            success=False,
            signal_id=sig.signal_id,
            underlying=sig.underlying,
            strategy=sig.strategy,
            side=str(getattr(order, "side", "SELL") or "SELL"),
            quantity=qty,
            lots=lots,
            fill_price=0.0,
            stop_loss=float(sig.stop_loss),
            target_1=float(sig.target_1),
            target_2=float(sig.target_2),
            order_id=str(getattr(order, "order_id", "") or ""),
            status=status,
            message=getattr(order, "rejection_reason", None) or f"EXIT_NOT_FILLED: {status}",
            fill_source="NONE",
            chain_mark_at_fill=None,
        )


signal_paper_engine = SignalPaperEngine()

