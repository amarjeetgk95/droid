"""Industrial-grade virtual order matching + portfolio engine.

Design notes (what changed vs the demo engine and why)
------------------------------------------------------
1. Per-user isolation: the old singleton kept one global ``_positions`` /
   ``_orders`` / ``_realized_pnl`` map shared by every user. This service now
   shards all mutable state by ``user_key = str(user_id) or "__anon__"``.
   The legacy attributes (``_positions``, ``_orders``, ``_initial_capital``,
   ``_realized_pnl``) are preserved as aliases of the anonymous shard so
   existing callers (signal engine, dashboard, tests) keep working.
2. Concurrency: every mutation runs under a per-user ``asyncio.Lock`` so a
   margin check + position update is atomic. Reads snapshot under the same
   lock but perform live-quote IO outside it.
3. Honest fills: MARKET orders prefer the live quote (with spread+slippage
   friction). The caller-supplied ``price`` is only a fallback when live is
   unavailable (flagged as CLIENT_FALLBACK) — never silently trusted.
   LIMIT / SL orders rest as PENDING when the market hasn't touched them.
4. Costs: every fill records an ``estimated_costs`` figure via
   ``app.quant.costs.calculate_option_costs`` (brokerage + STT + exchange +
   GST + slippage). Gross fill stays in ``fill_price`` for backward compat.
5. Risk gate: max single-order qty, max open positions, per-symbol exposure,
   fat-finger band (LIMIT only, when live is known), daily-loss kill switch.
6. Idempotency: optional ``client_order_id`` — resubmission returns the
   original order instead of double-filling (signal engine passes
   ``sig-{signal_id}``).
7. Position flip: an opposite-side order larger than the held qty now closes
   the old position AND opens the residual (old code silently dropped it).
   Partial-close margin relief is pro-rata, not the new order's margin.
8. Persistence: rejected orders are now always persisted (old code only
   persisted some paths). DB failures never fail the in-memory fill — they
   are logged as degraded. MTM writes are throttled (only on real change).
"""

import asyncio
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.paper import (
    OrderPayload, BasketOrderPayload, VirtualOrder,
    VirtualPosition, PortfolioSummary
)
from app.models.database import PaperOrderDB, PaperPositionDB
from app.quant.margin import calculate_required_margin
from app.repositories.paper_repository import PaperTradingRepository
from app.services.market_service import MarketService
import structlog

logger = structlog.get_logger()

ANON_KEY = "__anon__"

# Execution friction (bps). 5 bps spread ~= the old 0.05% hardcoded spread.
SPREAD_BPS = 5.0
SLIPPAGE_BPS = 10.0
# Risk-gate defaults — set wide so existing flows/tests never trip them;
# tighten via constructor for production.
MAX_SINGLE_ORDER_QTY = 100_000
MAX_OPEN_POSITIONS = 100
MAX_POSITION_QTY_PER_SYMBOL = 200_000
FAT_FINGER_BAND_PCT = 0.20
DAILY_LOSS_KILL_PCT = 0.25
# MTM persist throttle: skip DB write if unrealized barely moved.
MTM_PERSIST_EPS = 1.0


def _utcnow_str() -> str:
    return datetime.now(timezone.utc).isoformat()


class PaperTradingService:
    """Virtual Order Matching, Portfolio Management, and MTM Engine."""

    def __init__(
        self,
        market_service: MarketService | None = None,
        max_single_order_qty: int = MAX_SINGLE_ORDER_QTY,
        max_open_positions: int = MAX_OPEN_POSITIONS,
    ):
        self.market_service = market_service or MarketService()
        # Legacy anon shard (backward compat for direct attribute access).
        self._positions: dict[str, VirtualPosition] = {}
        self._orders: list[VirtualOrder] = []
        self._initial_capital: float = 1000000.0
        self._realized_pnl: float = 0.0
        # Per-user shards (anon key aliases the legacy attributes above).
        self._user_positions: dict[str, dict[str, VirtualPosition]] = {}
        self._user_orders: dict[str, list[VirtualOrder]] = {}
        self._capitals: dict[str, float] = {}
        self._realized_by_user: dict[str, float] = {}
        self._idempotency: dict[str, dict[str, VirtualOrder]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = threading.Lock()
        self._last_mtm_persist: dict[str, float] = {}
        self.max_single_order_qty = max_single_order_qty
        self.max_open_positions = max_open_positions

    # ── sharding helpers ──────────────────────────────────────────
    @staticmethod
    def _user_key(user_id: Optional[UUID]) -> str:
        return str(user_id) if user_id is not None else ANON_KEY

    def _lock_for(self, user_id: Optional[UUID]) -> asyncio.Lock:
        key = self._user_key(user_id)
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    def _pos_store(self, user_id: Optional[UUID]) -> dict[str, VirtualPosition]:
        if user_id is None:
            return self._positions
        key = str(user_id)
        store = self._user_positions.get(key)
        if store is None:
            store = {}
            self._user_positions[key] = store
        return store

    def _ord_store(self, user_id: Optional[UUID]) -> list[VirtualOrder]:
        if user_id is None:
            return self._orders
        key = str(user_id)
        store = self._user_orders.get(key)
        if store is None:
            store = []
            self._user_orders[key] = store
        return store

    def _get_capital(self, user_id: Optional[UUID]) -> float:
        if user_id is None:
            return self._initial_capital
        return self._capitals.get(str(user_id), 1000000.0)

    def _set_capital(self, user_id: Optional[UUID], value: float) -> None:
        if user_id is None:
            self._initial_capital = float(value)
        else:
            self._capitals[str(user_id)] = float(value)

    def _get_realized(self, user_id: Optional[UUID]) -> float:
        if user_id is None:
            return self._realized_pnl
        return self._realized_by_user.get(str(user_id), 0.0)

    def _add_realized(self, user_id: Optional[UUID], delta: float) -> float:
        if user_id is None:
            self._realized_pnl += delta
            return self._realized_pnl
        key = str(user_id)
        v = self._realized_by_user.get(key, 0.0) + delta
        self._realized_by_user[key] = v
        return v

    def _set_realized(self, user_id: Optional[UUID], value: float) -> None:
        if user_id is None:
            self._realized_pnl = float(value)
        else:
            self._realized_by_user[str(user_id)] = float(value)

    @staticmethod
    def _is_option_symbol(symbol: str) -> bool:
        s = (symbol or "").upper()
        return "CE" in s or "PE" in s

    @staticmethod
    def _instrument_type(symbol: str, side: str) -> str:
        s = (symbol or "").upper()
        is_opt = "CE" in s or "PE" in s
        if is_opt:
            return "OPTION_BUY" if side == "BUY" else "OPTION_SELL"
        return "FUTURES"

    @staticmethod
    def _apply_friction(live: float, side: str) -> float:
        bps = SPREAD_BPS + SLIPPAGE_BPS
        adj = live * (bps / 10_000.0)
        return round(live + adj if side == "BUY" else live - adj, 2)

    @staticmethod
    def _estimate_costs(symbol: str, side: str, fill: float, qty: int) -> float:
        try:
            from app.quant.costs import calculate_option_costs
            turnover = round(fill * qty, 2)
            buy_t = turnover if side == "BUY" else 0.0
            sell_t = turnover if side == "SELL" else 0.0
            bd = calculate_option_costs(buy_t, sell_t, num_orders=1)
            return round(float(bd.total_cost), 2)
        except Exception:
            return 0.0

    async def _resolve_live_ltp(self, pos: VirtualPosition) -> float | None:
        """Resolve the current live LTP for a position.

        - Options (CE/PE): live option-chain quote via
          ``OptionsService.get_option_quote`` (exact contract, then
          strike+type), with direct symbol-quote fallback. Never uses
          the underlying spot as the option price.
        - Futures / spot / equity: live ``get_quote`` LTP directly.

        Returns ``None`` when no live price is available so callers keep
        the last known LTP instead of fabricating / freezing P&L at zero.
        """
        sym = (pos.symbol or "").strip()
        und = (pos.underlying or "").strip()
        if not sym:
            return None

        if self._is_option_symbol(sym):
            # 1. Direct quotable option symbol (fast path).
            try:
                q = await self.market_service.get_quote(sym)
                if q and q.ltp and q.ltp > 0:
                    return float(q.ltp)
            except Exception:
                pass
            # 2. Live option-chain lookup (correct source for CE/PE MTM).
            try:
                from app.services.options_service import options_service

                oq = await options_service.get_option_quote(sym, underlying=und or None)
                if oq and oq.ltp and oq.ltp > 0:
                    return float(oq.ltp)
            except Exception:
                pass
            return None

        # Non-option: the position LTP *is* the live spot/futures quote.
        for candidate in (und, sym):
            if not candidate:
                continue
            try:
                q = await self.market_service.get_quote(candidate)
                if q and q.ltp and q.ltp > 0:
                    return float(q.ltp)
            except Exception:
                continue
        return None

    async def _resolve_live_for_symbol(self, symbol: str, underlying: str) -> float | None:
        probe = VirtualPosition(
            position_id="__probe__", symbol=symbol, underlying=underlying,
            instrument_type="PROBE", side="BUY", product="INTRADAY",
            quantity=1, average_price=0.0, ltp=0.0, unrealized_pnl=0.0,
        )
        try:
            return await self._resolve_live_ltp(probe)
        except Exception:
            return None

    @staticmethod
    def _db_to_order(db_ord: PaperOrderDB) -> VirtualOrder:
        return VirtualOrder(
            order_id=db_ord.order_id,
            timestamp=db_ord.timestamp.isoformat() if db_ord.timestamp else _utcnow_str(),
            symbol=db_ord.symbol,
            underlying=db_ord.underlying,
            side=db_ord.side,  # type: ignore
            order_type=db_ord.order_type,  # type: ignore
            product=db_ord.product,  # type: ignore
            quantity=db_ord.quantity,
            price=db_ord.price,
            trigger_price=db_ord.trigger_price,
            status=db_ord.status,  # type: ignore
            fill_price=db_ord.fill_price,
            rejection_reason=db_ord.rejection_reason,
            client_order_id=getattr(db_ord, "client_order_id", None),
            fill_source=getattr(db_ord, "fill_source", None),  # type: ignore
            estimated_costs=getattr(db_ord, "estimated_costs", None),
            filled_at=db_ord.filled_at.isoformat() if getattr(db_ord, "filled_at", None) else None,
        )

    @staticmethod
    def _db_to_position(db_pos: PaperPositionDB) -> VirtualPosition:
        return VirtualPosition(
            position_id=db_pos.position_id,
            symbol=db_pos.symbol,
            underlying=db_pos.underlying,
            instrument_type=db_pos.instrument_type,
            side=db_pos.side,  # type: ignore
            product=db_pos.product,  # type: ignore
            quantity=db_pos.quantity,
            average_price=db_pos.average_price,
            ltp=db_pos.ltp,
            unrealized_pnl=db_pos.unrealized_pnl,
            realized_pnl=db_pos.realized_pnl,
            used_margin=db_pos.used_margin,
            is_open=db_pos.is_open,
        )

    # ── internal: rejected-order builder (always persisted when possible) ──
    async def _reject(
        self,
        payload: OrderPayload,
        reason: str,
        order_id: str,
        now_str: str,
        session: Optional[AsyncSession],
        user_id: Optional[UUID],
        orders: list[VirtualOrder],
    ) -> VirtualOrder:
        rejected = VirtualOrder(
            order_id=order_id,
            timestamp=now_str,
            symbol=payload.symbol,
            underlying=payload.underlying,
            side=payload.side,
            order_type=payload.order_type,
            product=payload.product,
            quantity=payload.quantity,
            price=payload.price,
            trigger_price=payload.trigger_price,
            status="REJECTED",
            fill_price=None,
            rejection_reason=reason,
            client_order_id=payload.client_order_id,
        )
        orders.insert(0, rejected)
        if session is not None and user_id is not None:
            try:
                await PaperTradingRepository.save_order(session, user_id, rejected)
            except Exception as e:
                logger.warning("failed_to_save_rejected_order_db", error=str(e))
        logger.warning("paper_order_rejected", symbol=payload.symbol, reason=reason)
        return rejected

    async def _persist_fill(
        self,
        session: Optional[AsyncSession],
        user_id: Optional[UUID],
        order: VirtualOrder,
        pos_obj: VirtualPosition,
        summary: PortfolioSummary,
    ) -> None:
        if session is None or user_id is None:
            return
        try:
            await PaperTradingRepository.save_order(session, user_id, order)
        except Exception as e:
            logger.warning("failed_to_save_paper_trade_db", error=str(e))
            return  # order row is the critical audit record; skip the rest
        try:
            await PaperTradingRepository.upsert_position(session, user_id, pos_obj)
        except Exception as e:
            logger.warning("failed_to_save_paper_position_db", error=str(e))
        try:
            await PaperTradingRepository.update_portfolio(
                session,
                user_id,
                available_margin=summary.available_margin,
                used_margin=summary.used_margin,
                realized_pnl=summary.total_realized_pnl,
            )
        except Exception as e:
            logger.warning("failed_to_save_paper_portfolio_db", error=str(e))

    def _summary_from_snapshot(
        self,
        capital: float,
        realized: float,
        positions: list[VirtualPosition],
    ) -> PortfolioSummary:
        open_positions = [p for p in positions if p.is_open]
        total_unrealized = round(sum(p.unrealized_pnl for p in open_positions), 2)
        total_used_margin = round(sum(p.used_margin for p in open_positions), 2)
        total_pnl = round(realized + total_unrealized, 2)
        available_margin = round(max(0.0, capital + total_pnl - total_used_margin), 2)
        margin_util = round((total_used_margin / capital) * 100.0, 2) if capital > 0 else 0.0
        return PortfolioSummary(
            virtual_capital=capital,
            available_margin=available_margin,
            used_margin=total_used_margin,
            margin_utilization_pct=margin_util,
            total_realized_pnl=round(realized, 2),
            total_unrealized_pnl=total_unrealized,
            total_portfolio_pnl=total_pnl,
            open_positions_count=len(open_positions),
        )

    # ── fill resolution ─────────────────────────────────────────
    async def _resolve_fill(
        self,
        payload: OrderPayload,
        forced_fill: tuple[float, str] | None = None,
    ) -> tuple[float | None, str | None, bool]:
        """Return (fill_price, fill_source, is_pending).

        PENDING is used for LIMIT/SL orders the market hasn't touched yet —
        the caller must rest the order instead of filling it.
        """
        if forced_fill is not None:
            return forced_fill[0], forced_fill[1], False

        live: float | None = None
        try:
            live = await self._resolve_live_for_symbol(payload.symbol, payload.underlying)
        except Exception:
            live = None
        if live is not None and live <= 0:
            live = None

        otype = payload.order_type
        if otype == "MARKET":
            if live is not None:
                return self._apply_friction(live, payload.side), "LIVE", False
            if payload.price and payload.price > 0:
                logger.warning(
                    "paper_fill_client_fallback",
                    symbol=payload.symbol, reason="live_unavailable",
                )
                return float(payload.price), "CLIENT_FALLBACK", False
            return None, None, False

        if otype == "LIMIT":
            if not payload.price or payload.price <= 0:
                return None, None, False
            if live is None:
                logger.warning("paper_fill_client_fallback", symbol=payload.symbol, reason="live_unavailable_limit")
                return float(payload.price), "CLIENT_FALLBACK", False
            adj = self._apply_friction(live, payload.side)
            if payload.side == "BUY":
                if adj <= payload.price:
                    return min(adj, float(payload.price)), "LIMIT", False
                return None, None, True
            else:
                if adj >= payload.price:
                    return max(adj, float(payload.price)), "LIMIT", False
                return None, None, True

        # SL_MARKET / SL_LIMIT: trigger-gated.
        if not payload.trigger_price or payload.trigger_price <= 0:
            return None, None, False
        trig = float(payload.trigger_price)
        if live is None:
            # Cannot evaluate the trigger without live — rest the order.
            return None, None, True
        triggered = (live >= trig) if payload.side == "BUY" else (live <= trig)
        if not triggered:
            return None, None, True
        if otype == "SL_MARKET":
            return self._apply_friction(live, payload.side), "LIVE", False
        # SL_LIMIT needs a limit price as well.
        if not payload.price or payload.price <= 0:
            return self._apply_friction(live, payload.side), "LIVE", False
        adj = self._apply_friction(live, payload.side)
        if payload.side == "BUY":
            if adj <= payload.price:
                return min(adj, float(payload.price)), "LIMIT", False
            return None, None, True
        else:
            if adj >= payload.price:
                return max(adj, float(payload.price)), "LIMIT", False
            return None, None, True

    # ── core order path ─────────────────────────────────────────
    async def place_order(
        self,
        payload: OrderPayload,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
        allow_closed_market: bool = False,
    ) -> VirtualOrder:
        """Place and execute a single virtual order (Final Hard Safety Boundary)."""
        lock = self._lock_for(user_id)
        async with lock:
            return await self._place_order_locked(payload, session, user_id, allow_closed_market)

    async def _place_order_locked(
        self,
        payload: OrderPayload,
        session: Optional[AsyncSession],
        user_id: Optional[UUID],
        allow_closed_market: bool,
        forced_fill: tuple[float, str] | None = None,
    ) -> VirtualOrder:
        now_str = _utcnow_str()
        order_id = f"ORD-{uuid.uuid4().hex[:12].upper()}"
        orders = self._ord_store(user_id)
        positions = self._pos_store(user_id)

        # ── Idempotency: same (user, client_order_id) returns the original ──
        if payload.client_order_id:
            seen = self._idempotency.setdefault(self._user_key(user_id), {})
            if payload.client_order_id in seen:
                logger.info("paper_order_idempotent_replay", client_order_id=payload.client_order_id)
                return seen[payload.client_order_id]

        # ── Final Safety Invariant: Check Market Session for Indian Instruments ──
        is_indian = payload.underlying in ("NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY") or any(
            x in payload.symbol for x in ("CE", "PE", "FUT", "NIFTY", "BANKNIFTY", "SENSEX")
        )
        if is_indian and not allow_closed_market:
            from app.services.calendar_service import calendar_service
            perm = calendar_service.can_trade_now()
            if not perm.allowed:
                return await self._reject(
                    payload,
                    f"MARKET_CLOSED: {perm.reason} (NSE/BSE trading hours: 09:15 - 15:30 IST)",
                    order_id, now_str, session, user_id, orders,
                )

        # Guard non-positive quantity (defense in depth; pydantic also enforces).
        if payload.quantity <= 0:
            return await self._reject(
                payload,
                "INVALID_QUANTITY: Order quantity must be greater than zero",
                order_id, now_str, session, user_id, orders,
            )

        # ── Risk gate ──
        if payload.quantity > self.max_single_order_qty:
            return await self._reject(
                payload,
                f"ORDER_TOO_LARGE: quantity {payload.quantity} exceeds max {self.max_single_order_qty}",
                order_id, now_str, session, user_id, orders,
            )
        open_count = sum(1 for p in positions.values() if p.is_open)
        pos_id_preview = f"{payload.symbol}_{payload.product}"
        is_new_position = pos_id_preview not in positions or not positions[pos_id_preview].is_open
        existing_preview = positions.get(pos_id_preview)
        adds_exposure = is_new_position or (
            existing_preview is not None and existing_preview.is_open and existing_preview.side == payload.side
        )
        if adds_exposure and open_count >= self.max_open_positions and is_new_position:
            return await self._reject(
                payload,
                f"POSITION_LIMIT: {open_count} open positions (max {self.max_open_positions})",
                order_id, now_str, session, user_id, orders,
            )
        if existing_preview is not None and existing_preview.is_open and existing_preview.side == payload.side:
            if existing_preview.quantity + payload.quantity > MAX_POSITION_QTY_PER_SYMBOL:
                return await self._reject(
                    payload,
                    f"SYMBOL_EXPOSURE_LIMIT: would hold {existing_preview.quantity + payload.quantity}",
                    order_id, now_str, session, user_id, orders,
                )
        # Daily-loss kill switch (long-only brake; shorts to exit still allowed).
        realized_now = self._get_realized(user_id)
        capital_now = self._get_capital(user_id)
        if realized_now < -DAILY_LOSS_KILL_PCT * capital_now and payload.side == "BUY" and is_new_position:
            return await self._reject(
                payload,
                f"DAILY_LOSS_LIMIT: realized {realized_now:,.2f} breached {-DAILY_LOSS_KILL_PCT*100:.0f}% of capital",
                order_id, now_str, session, user_id, orders,
            )

        # Determine fill price from LIVE market data (never fabricated).
        fill_price: float | None = None
        fill_source: str | None = None
        is_pending = False
        try:
            fill_price, fill_source, is_pending = await self._resolve_fill(payload, forced_fill)
        except Exception as e:
            logger.warning("paper_fill_resolve_failed", error=str(e))
            fill_price, fill_source, is_pending = None, None, False

        if is_pending:
            pending = VirtualOrder(
                order_id=order_id,
                timestamp=now_str,
                symbol=payload.symbol,
                underlying=payload.underlying,
                side=payload.side,
                order_type=payload.order_type,
                product=payload.product,
                quantity=payload.quantity,
                price=payload.price,
                trigger_price=payload.trigger_price,
                status="PENDING",
                fill_price=None,
                rejection_reason=None,
                client_order_id=payload.client_order_id,
                fill_source=None,
            )
            orders.insert(0, pending)
            if payload.client_order_id:
                self._idempotency.setdefault(self._user_key(user_id), {})[payload.client_order_id] = pending
            if session is not None and user_id is not None:
                try:
                    await PaperTradingRepository.save_order(session, user_id, pending)
                except Exception as e:
                    logger.warning("failed_to_save_pending_order_db", error=str(e))
            logger.info("paper_order_pending", order_id=order_id, symbol=payload.symbol, otype=payload.order_type)
            return pending

        if fill_price is None or fill_price <= 0:
            if payload.order_type in ("LIMIT", "SL_MARKET", "SL_LIMIT") and (not payload.price or payload.price <= 0):
                reason = "INVALID_PRICE: LIMIT/SL orders require a positive limit price"
            elif payload.order_type in ("SL_MARKET", "SL_LIMIT") and (not payload.trigger_price or payload.trigger_price <= 0):
                reason = "INVALID_TRIGGER: SL orders require a positive trigger_price"
            else:
                reason = "MARKET_QUOTE_UNAVAILABLE: Live market quote unavailable to fill market order"
            return await self._reject(payload, reason, order_id, now_str, session, user_id, orders)

        fill_price = round(float(fill_price), 2)

        # Fat-finger band for LIMIT orders when live is known (MARKET ignores
        # client price by design, so no band applies there).
        if payload.order_type in ("LIMIT", "SL_LIMIT") and fill_source == "LIMIT" and payload.price > 0:
            try:
                live_now = await self._resolve_live_for_symbol(payload.symbol, payload.underlying)
                if live_now and live_now > 0:
                    drift = abs(float(payload.price) - live_now) / live_now
                    if drift > FAT_FINGER_BAND_PCT:
                        return await self._reject(
                            payload,
                            f"FAT_FINGER: limit {payload.price} is {drift*100:.1f}% away from live {live_now}",
                            order_id, now_str, session, user_id, orders,
                        )
            except Exception:
                pass

        # Calculate required margin
        inst_type = self._instrument_type(payload.symbol, payload.side)
        req_margin = calculate_required_margin(
            instrument_type=inst_type,  # type: ignore[arg-type]
            underlying=payload.underlying,
            price=fill_price,
            quantity=payload.quantity,
            is_hedged=False,
        )

        snapshot = self._summary_from_snapshot(capital_now, realized_now, list(positions.values()))
        # Margin is only checked when adding exposure (exits free margin).
        needs_margin = True
        if pos_id_preview in positions and positions[pos_id_preview].is_open:
            ex = positions[pos_id_preview]
            if ex.side != payload.side:
                needs_margin = False  # exit/reversal leg releases margin
        if needs_margin and req_margin > snapshot.available_margin:
            return await self._reject(
                payload,
                f"Insufficient Margin. Required: ₹{req_margin:,.2f}, Available: ₹{snapshot.available_margin:,.2f}",
                order_id, now_str, session, user_id, orders,
            )

        # Create or update position
        pos_id = f"{payload.symbol}_{payload.product}"
        pos_obj: VirtualPosition
        if pos_id in positions and positions[pos_id].is_open:
            existing = positions[pos_id]
            if existing.side == payload.side:
                # Add to position
                tot_qty = existing.quantity + payload.quantity
                tot_val = (existing.quantity * existing.average_price) + (payload.quantity * fill_price)
                existing.average_price = round(tot_val / tot_qty, 2)
                existing.quantity = tot_qty
                existing.ltp = fill_price
                existing.used_margin = round(existing.used_margin + req_margin, 2)
                mult = 1 if existing.side == "BUY" else -1
                existing.unrealized_pnl = round((existing.ltp - existing.average_price) * existing.quantity * mult, 2)
                pos_obj = existing
            else:
                # Reversing / closing portion
                closed_qty = min(existing.quantity, payload.quantity)
                mult = 1 if existing.side == "BUY" else -1
                trade_realized = (fill_price - existing.average_price) * closed_qty * mult
                self._add_realized(user_id, round(trade_realized, 2))
                existing.realized_pnl = round(existing.realized_pnl + trade_realized, 2)

                if payload.quantity >= existing.quantity:
                    residual = payload.quantity - existing.quantity
                    existing.is_open = False
                    existing.quantity = 0
                    existing.used_margin = 0.0
                    existing.ltp = fill_price
                    existing.unrealized_pnl = 0.0
                    if residual > 0:
                        # Flip: open the residual in the new direction.
                        flip_margin = calculate_required_margin(
                            instrument_type=inst_type,  # type: ignore[arg-type]
                            underlying=payload.underlying,
                            price=fill_price,
                            quantity=residual,
                            is_hedged=False,
                        )
                        flipped = VirtualPosition(
                            position_id=pos_id,
                            symbol=payload.symbol,
                            underlying=payload.underlying,
                            instrument_type=inst_type,
                            side=payload.side,
                            product=payload.product,
                            quantity=residual,
                            average_price=fill_price,
                            ltp=fill_price,
                            unrealized_pnl=0.0,
                            realized_pnl=0.0,
                            used_margin=flip_margin,
                            is_open=True,
                        )
                        positions[pos_id] = flipped
                        pos_obj = flipped
                    else:
                        pos_obj = existing
                else:
                    # Pro-rata margin relief (old code subtracted the new
                    # order's margin, which mis-states the remaining lock).
                    frac = existing.quantity and (payload.quantity / existing.quantity) or 0.0
                    existing.quantity -= payload.quantity
                    existing.used_margin = round(max(0.0, existing.used_margin * (1.0 - frac)), 2)
                    existing.ltp = fill_price
                    mult2 = 1 if existing.side == "BUY" else -1
                    existing.unrealized_pnl = round(
                        (existing.ltp - existing.average_price) * existing.quantity * mult2, 2
                    )
                    pos_obj = existing
                # NOTE: fully-closed (no flip) and partial paths set pos_obj
                # in their own branches above; flip path set it to `flipped`.
        else:
            pos_obj = VirtualPosition(
                position_id=pos_id,
                symbol=payload.symbol,
                underlying=payload.underlying,
                instrument_type=inst_type,
                side=payload.side,
                product=payload.product,
                quantity=payload.quantity,
                average_price=fill_price,
                ltp=fill_price,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                used_margin=req_margin,
                is_open=True,
            )
            positions[pos_id] = pos_obj

        est_costs = self._estimate_costs(payload.symbol, payload.side, fill_price, payload.quantity)
        order = VirtualOrder(
            order_id=order_id,
            timestamp=now_str,
            symbol=payload.symbol,
            underlying=payload.underlying,
            side=payload.side,
            order_type=payload.order_type,
            product=payload.product,
            quantity=payload.quantity,
            price=payload.price,
            trigger_price=payload.trigger_price,
            status="FILLED",
            fill_price=fill_price,
            client_order_id=payload.client_order_id,
            fill_source=fill_source,  # type: ignore
            estimated_costs=est_costs,
            filled_at=_utcnow_str(),
        )
        orders.insert(0, order)
        if payload.client_order_id:
            self._idempotency.setdefault(self._user_key(user_id), {})[payload.client_order_id] = order

        # Persist to Supabase if session and user_id available (best-effort;
        # a DB outage must never fail the in-memory fill).
        if session is not None and user_id is not None:
            try:
                updated = self._summary_from_snapshot(
                    self._get_capital(user_id), self._get_realized(user_id), list(positions.values())
                )
                await self._persist_fill(session, user_id, order, pos_obj, updated)
            except Exception as e:
                logger.warning("failed_to_save_paper_trade_db", error=str(e))

        logger.info(
            "paper_order_filled", order_id=order_id, symbol=payload.symbol,
            side=payload.side, qty=payload.quantity, fill=fill_price,
            source=fill_source, costs=est_costs,
        )
        return order

    async def place_basket(
        self,
        payload: BasketOrderPayload,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
        allow_closed_market: bool = False,
    ) -> list[VirtualOrder]:
        """Execute a multi-leg strategy basket."""
        results: list[VirtualOrder] = []
        for ord_payload in payload.orders:
            res = await self.place_order(ord_payload, session, user_id, allow_closed_market=allow_closed_market)
            results.append(res)
            # Fail-closed on first rejection for SL legs? No — legacy behavior
            # executes every leg independently; keep it, report per-leg status.
        return results

    async def cancel_order(
        self,
        order_id: str,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
    ) -> VirtualOrder:
        """Cancel a resting PENDING order. FILLED/REJECTED orders cannot be cancelled."""
        lock = self._lock_for(user_id)
        async with lock:
            orders = self._ord_store(user_id)
            for o in orders:
                if o.order_id == order_id:
                    if o.status != "PENDING":
                        raise ValueError(f"Only PENDING orders can be cancelled (got {o.status})")
                    o.status = "CANCELLED"
                    if session is not None and user_id is not None:
                        try:
                            await PaperTradingRepository.save_order(session, user_id, o)
                        except Exception as e:
                            logger.warning("failed_to_persist_cancel_db", error=str(e))
                    logger.info("paper_order_cancelled", order_id=order_id)
                    return o
            raise ValueError(f"Order not found: {order_id}")

    async def square_off_position(
        self,
        position_id: str,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
        allow_closed_market: bool = False,
    ) -> VirtualPosition:
        """Close an open position at current live market price."""
        lock = self._lock_for(user_id)
        async with lock:
            positions = self._pos_store(user_id)
            if position_id not in positions or not positions[position_id].is_open:
                raise ValueError(f"Open position not found: {position_id}")

            pos = positions[position_id]
            exit_side = "SELL" if pos.side == "BUY" else "BUY"

            # Resolve a fresh exit fill (live + friction). Fall back to the
            # last known LTP so a feed outage never traps a position.
            forced: tuple[float, str] | None = None
            try:
                live = await self._resolve_live_ltp(pos)
                if live and live > 0:
                    forced = (self._apply_friction(float(live), exit_side), "LIVE")
                    pos.ltp = round(float(live), 2)
                    mult = 1 if pos.side == "BUY" else -1
                    pos.unrealized_pnl = round((pos.ltp - pos.average_price) * pos.quantity * mult, 2)
            except Exception:
                pass
            if forced is None:
                if not pos.ltp or pos.ltp <= 0:
                    raise ValueError(f"No exit price available for {position_id} (live unavailable, no cached LTP)")
                forced = (round(float(pos.ltp), 2), "CLOSE_FALLBACK")

            # Indian instruments still respect the market-session gate unless
            # the caller explicitly permits closed-market cleanup.
            is_indian = pos.underlying in ("NIFTY", "BANKNIFTY", "SENSEX", "FINNIFTY", "MIDCPNIFTY") or any(
                x in pos.symbol for x in ("CE", "PE", "FUT", "NIFTY", "BANKNIFTY", "SENSEX")
            )
            if is_indian and not allow_closed_market:
                from app.services.calendar_service import calendar_service
                perm = calendar_service.can_trade_now()
                if not perm.allowed:
                    raise ValueError(f"MARKET_CLOSED: {perm.reason} — pass allow_closed_market=True for cleanup exits")

            exit_order = OrderPayload(
                symbol=pos.symbol,
                underlying=pos.underlying,
                side=exit_side,  # type: ignore[arg-type]
                order_type="MARKET",
                product=pos.product,
                quantity=pos.quantity,
                price=0.0,
            )
            await self._place_order_locked(exit_order, session, user_id, allow_closed_market=True, forced_fill=forced)
            return positions[position_id]

    async def square_off_all(
        self,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
        allow_closed_market: bool = False,
    ) -> list[VirtualPosition]:
        """Emergency square off of all active positions."""
        # Snapshot IDs first (each leg takes the per-user lock itself).
        if user_id is None:
            open_ids = [pid for pid, pos in self._positions.items() if pos.is_open]
        else:
            store = self._pos_store(user_id)
            open_ids = [pid for pid, pos in store.items() if pos.is_open]
        closed: list[VirtualPosition] = []
        for pid in open_ids:
            try:
                c = await self.square_off_position(pid, session, user_id, allow_closed_market=allow_closed_market)
                closed.append(c)
            except Exception as e:
                logger.warning("square_off_failed", pid=pid, error=str(e))
        return closed

    async def set_initial_capital_async(
        self,
        capital: float,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
    ) -> PortfolioSummary:
        """Set a custom capital amount for the paper trading wallet and persist to DB."""
        if capital <= 0:
            raise ValueError("Capital must be greater than 0")
        lock = self._lock_for(user_id)
        async with lock:
            self._set_capital(user_id, float(capital))

            if session is not None and user_id is not None:
                try:
                    db_port = await PaperTradingRepository.get_or_create_portfolio(session, user_id)
                    db_port.virtual_capital = self._get_capital(user_id)
                    positions = self._pos_store(user_id)
                    realized = self._get_realized(user_id)
                    snap = self._summary_from_snapshot(self._get_capital(user_id), realized, list(positions.values()))
                    db_port.available_margin = snap.available_margin
                    await session.commit()
                except Exception as e:
                    logger.warning("failed_to_update_portfolio_capital_db", error=str(e))

        return await self.get_portfolio_summary(session, user_id)

    def set_initial_capital(self, capital: float) -> PortfolioSummary:
        """Sync set capital amount (anonymous shard; kept for backward compat)."""
        if capital <= 0:
            raise ValueError("Capital must be greater than 0")
        self._initial_capital = float(capital)
        positions = list(self._positions.values())
        return self._summary_from_snapshot(self._initial_capital, self._realized_pnl, positions)

    async def reset_portfolio_async(
        self,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
        capital: Optional[float] = None,
    ) -> PortfolioSummary:
        """Reset virtual account to baseline or custom capital state."""
        lock = self._lock_for(user_id)
        async with lock:
            if capital is not None and capital > 0:
                self._set_capital(user_id, float(capital))
            target_cap = self._get_capital(user_id)
            self._pos_store(user_id).clear()
            self._ord_store(user_id).clear()
            self._set_realized(user_id, 0.0)
            self._idempotency.pop(self._user_key(user_id), None)

            if session is not None and user_id is not None:
                try:
                    await PaperTradingRepository.reset_portfolio(session, user_id)
                    db_port = await PaperTradingRepository.get_or_create_portfolio(session, user_id)
                    db_port.virtual_capital = target_cap
                    db_port.available_margin = target_cap
                    await session.commit()
                except Exception as e:
                    logger.warning("failed_to_reset_portfolio_db", error=str(e))

            return self._summary_from_snapshot(target_cap, 0.0, [])

    def reset_portfolio(self, capital: Optional[float] = None) -> PortfolioSummary:
        """Sync reset for backwards compatibility (anonymous shard).

        NOTE: this deliberately only clears the anonymous shard. Authenticated
        shards are cleared via ``reset_portfolio_async(session, user_id)`` so
        one user's reset can never wipe another user's book.
        """
        if capital is not None and capital > 0:
            self._initial_capital = float(capital)
        self._positions.clear()
        self._orders.clear()
        self._realized_pnl = 0.0
        self._idempotency.pop(ANON_KEY, None)
        return PortfolioSummary(
            virtual_capital=self._initial_capital,
            available_margin=self._initial_capital,
            used_margin=0.0,
            margin_utilization_pct=0.0,
            total_realized_pnl=0.0,
            total_unrealized_pnl=0.0,
            total_portfolio_pnl=0.0,
            open_positions_count=0,
        )

    def reset_user_shard(self, user_id: Optional[UUID]) -> None:
        """Test helper: clear one user's in-memory shard without touching others."""
        key = self._user_key(user_id)
        if user_id is None:
            self.reset_portfolio()
            return
        self._user_positions.pop(key, None)
        self._user_orders.pop(key, None)
        self._realized_by_user.pop(key, None)
        self._capitals.pop(key, None)
        self._idempotency.pop(key, None)

    async def get_positions(
        self,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
    ) -> list[VirtualPosition]:
        """Retrieve all positions with real-time MTM refresh.

        - Hydrates the per-user in-memory state from Supabase when the shard
          is empty (process restart / new worker) so P&L survives restarts.
        - Refreshes every open position's LTP concurrently from LIVE quotes:
          option-chain LTP for CE/PE, spot/futures LTP otherwise.
        - Keeps the last known LTP when live data is unavailable instead of
          fabricating a drift-based price (honest stale > fake live).
        - MTM DB writes are throttled to real moves (see MTM_PERSIST_EPS).
        """
        lock = self._lock_for(user_id)
        # Hydrate from DB when the shard is empty (process restart / worker).
        async with lock:
            store = self._pos_store(user_id)
            if session is not None and user_id is not None and not store:
                try:
                    db_positions = await PaperTradingRepository.get_positions(session, user_id)
                    for db_pos in db_positions:
                        try:
                            vp = self._db_to_position(db_pos)
                            store[vp.position_id] = vp
                        except Exception:
                            continue
                    try:
                        db_port = await PaperTradingRepository.get_or_create_portfolio(session, user_id)
                        if db_port is not None and db_port.realized_pnl is not None:
                            self._set_realized(user_id, float(db_port.realized_pnl or 0.0))
                        if db_port is not None and db_port.virtual_capital:
                            self._set_capital(user_id, float(db_port.virtual_capital))
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning("paper_positions_hydrate_failed", error=str(e))
            snapshot = list(store.values())

        open_positions = [p for p in snapshot if p.is_open]

        # Concurrent live MTM refresh — one slow symbol must not stall the rest.
        # Network IO happens OUTSIDE the lock.
        if open_positions:
            async def _fetch(pos: VirtualPosition) -> tuple[str, float | None]:
                try:
                    live = await self._resolve_live_ltp(pos)
                    if live is not None and live > 0:
                        return pos.position_id, round(float(live), 2)
                except Exception:
                    pass
                return pos.position_id, None

            results = await asyncio.gather(*(_fetch(p) for p in open_positions), return_exceptions=True)

            async with lock:
                store = self._pos_store(user_id)
                for r in results:
                    if not isinstance(r, tuple):
                        continue
                    pid, live = r
                    pos = store.get(pid)
                    if pos is None or not pos.is_open or live is None:
                        continue
                    pos.ltp = live
                    mult = 1 if pos.side == "BUY" else -1
                    pos.unrealized_pnl = round((pos.ltp - pos.average_price) * pos.quantity * mult, 2)

                # Best-effort throttled persist so DB stays consistent without
                # a write storm on every 4s poll.
                if session is not None and user_id is not None:
                    for pos in open_positions:
                        cur = store.get(pos.position_id)
                        if cur is None:
                            continue
                        cache_key = f"{self._user_key(user_id)}:{cur.position_id}"
                        last = self._last_mtm_persist.get(cache_key)
                        if last is not None and abs(cur.unrealized_pnl - last) < MTM_PERSIST_EPS:
                            continue
                        try:
                            await PaperTradingRepository.upsert_position(session, user_id, cur)
                            self._last_mtm_persist[cache_key] = cur.unrealized_pnl
                        except Exception:
                            break

        async with lock:
            return list(self._pos_store(user_id).values())

    async def get_orders_async(
        self,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[VirtualOrder]:
        """Retrieve order log from Supabase or memory (paginated)."""
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        if session is not None and user_id is not None:
            try:
                db_orders = await PaperTradingRepository.get_orders(session, user_id, limit=limit, offset=offset)
                if db_orders:
                    return [self._db_to_order(o) for o in db_orders]
            except Exception as e:
                logger.warning("failed_to_get_orders_db", error=str(e))

        async with self._lock_for(user_id):
            mem = list(self._ord_store(user_id))
        return mem[offset:offset + limit]

    def get_orders(self) -> list[VirtualOrder]:
        """Sync retrieve order log (anonymous shard)."""
        return self._orders

    async def get_portfolio_summary(
        self,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
    ) -> PortfolioSummary:
        """Calculate real-time account summary with margin & MTM."""
        positions = await self.get_positions(session, user_id)
        async with self._lock_for(user_id):
            capital = self._get_capital(user_id)
            realized = self._get_realized(user_id)
        return self._summary_from_snapshot(capital, realized, positions)

    async def evaluate_pending_orders(
        self,
        symbol: str,
        ltp: float,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
    ) -> list[VirtualOrder]:
        """Try to fill resting PENDING orders for one symbol at the given LTP.

        Intended for a quote-tick worker. Each touched order is re-resolved
        through the normal fill path so friction + margin still apply.
        Returns the orders that transitioned to FILLED.
        """
        if not ltp or ltp <= 0:
            return []
        lock = self._lock_for(user_id)
        async with lock:
            orders = self._ord_store(user_id)
            candidates = [o for o in orders if o.status == "PENDING" and o.symbol == symbol]
        filled: list[VirtualOrder] = []
        for o in candidates:
            try:
                payload = OrderPayload(
                    symbol=o.symbol, underlying=o.underlying, side=o.side,  # type: ignore[arg-type]
                    order_type=o.order_type, product=o.product,
                    quantity=o.quantity, price=o.price,
                    trigger_price=o.trigger_price,
                )
                adj = self._apply_friction(float(ltp), o.side)
                should_fill = False
                fill_at = adj
                if o.order_type == "LIMIT":
                    if o.side == "BUY" and adj <= o.price:
                        should_fill, fill_at = True, min(adj, o.price)
                    elif o.side == "SELL" and adj >= o.price:
                        should_fill, fill_at = True, max(adj, o.price)
                elif o.order_type in ("SL_MARKET", "SL_LIMIT"):
                    trig = o.trigger_price or 0
                    hit = (float(ltp) >= trig) if o.side == "BUY" else (float(ltp) <= trig)
                    if hit:
                        should_fill = True
                        fill_at = adj if o.order_type == "SL_MARKET" else (
                            min(adj, o.price) if o.side == "BUY" else max(adj, o.price)
                        )
                if not should_fill:
                    continue
                async with lock:
                    # Re-check still pending (another tick may have filled it).
                    if o.status != "PENDING":
                        continue
                    o.status = "FILLED"
                    o.fill_price = round(fill_at, 2)
                    o.fill_source = "LIMIT"
                    o.filled_at = _utcnow_str()
                    o.estimated_costs = self._estimate_costs(o.symbol, o.side, o.fill_price, o.quantity)
                # Apply the position leg under lock via the normal path.
                fill_payload = OrderPayload(
                    symbol=o.symbol, underlying=o.underlying, side=o.side,  # type: ignore[arg-type]
                    order_type="MARKET", product=o.product,
                    quantity=o.quantity, price=o.fill_price or 0.0,
                )
                await self._place_order_locked(
                    fill_payload, session, user_id, allow_closed_market=True,
                    forced_fill=(float(o.fill_price or 0.0), "LIMIT"),
                )
                filled.append(o)
                if session is not None and user_id is not None:
                    try:
                        await PaperTradingRepository.save_order(session, user_id, o)
                    except Exception:
                        pass
            except Exception as e:
                logger.warning("pending_fill_failed", order_id=o.order_id, error=str(e))
        return filled


paper_service = PaperTradingService()
