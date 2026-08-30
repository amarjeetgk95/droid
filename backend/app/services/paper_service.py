import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.paper import (
    OrderPayload, BasketOrderPayload, VirtualOrder,
    VirtualPosition, PortfolioSummary
)
from app.models.database import PaperOrderDB, PaperPositionDB, PaperPortfolioDB
from app.quant.margin import calculate_required_margin
from app.repositories.paper_repository import PaperTradingRepository
from app.core.database import get_async_session_factory
from app.services.market_service import MarketService
import structlog

logger = structlog.get_logger()


class PaperTradingService:
    """Virtual Order Matching, Portfolio Management, and MTM Engine backed by Supabase."""

    def __init__(self, market_service: MarketService | None = None):
        self.market_service = market_service or MarketService()
        self._initial_capital: float = 1000000.0
        self._realized_pnl: float = 0.0
        self._positions: dict[str, VirtualPosition] = {}
        self._orders: list[VirtualOrder] = []

    @staticmethod
    def _db_to_order(db_ord: PaperOrderDB) -> VirtualOrder:
        return VirtualOrder(
            order_id=db_ord.order_id,
            timestamp=db_ord.timestamp.isoformat() if db_ord.timestamp else datetime.now(timezone.utc).isoformat(),
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

    async def place_order(
        self,
        payload: OrderPayload,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
    ) -> VirtualOrder:
        """Place and execute a single virtual order."""
        now_str = datetime.now(timezone.utc).isoformat()
        order_id = f"ORD-{uuid.uuid4().hex[:6].upper()}"

        # Determine fill price
        fill_price = payload.price
        if fill_price <= 0:
            try:
                quote = await self.market_service.get_quote(payload.underlying)
                fill_price = round(quote.ltp * 0.015, 2) if "CE" in payload.symbol or "PE" in payload.symbol else quote.ltp
            except Exception:
                fill_price = 150.0

        # Calculate required margin
        inst_type = "OPTION_BUY" if payload.side == "BUY" and ("CE" in payload.symbol or "PE" in payload.symbol) else "OPTION_SELL" if payload.side == "SELL" and ("CE" in payload.symbol or "PE" in payload.symbol) else "FUTURES"
        req_margin = calculate_required_margin(
            instrument_type=inst_type,
            underlying=payload.underlying,
            price=fill_price,
            quantity=payload.quantity,
            is_hedged=False,
        )

        portfolio = await self.get_portfolio_summary(session, user_id)
        if req_margin > portfolio.available_margin:
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
                rejection_reason=f"Insufficient Margin. Required: ₹{req_margin:,.2f}, Available: ₹{portfolio.available_margin:,.2f}",
            )
            self._orders.insert(0, rejected)
            if session and user_id:
                try:
                    await PaperTradingRepository.save_order(session, user_id, rejected)
                except Exception as e:
                    logger.warning("failed_to_save_rejected_order_db", error=str(e))
            return rejected

        # Create or update position
        pos_id = f"{payload.symbol}_{payload.product}"
        pos_obj: VirtualPosition
        if pos_id in self._positions and self._positions[pos_id].is_open:
            existing = self._positions[pos_id]
            if existing.side == payload.side:
                # Add to position
                tot_qty = existing.quantity + payload.quantity
                tot_val = (existing.quantity * existing.average_price) + (payload.quantity * fill_price)
                existing.average_price = round(tot_val / tot_qty, 2)
                existing.quantity = tot_qty
                existing.used_margin += req_margin
            else:
                # Reversing / closing portion
                closed_qty = min(existing.quantity, payload.quantity)
                mult = 1 if existing.side == "BUY" else -1
                trade_realized = (fill_price - existing.average_price) * closed_qty * mult
                self._realized_pnl += trade_realized
                existing.realized_pnl += trade_realized

                if payload.quantity >= existing.quantity:
                    existing.is_open = False
                    existing.quantity = 0
                    existing.used_margin = 0.0
                else:
                    existing.quantity -= payload.quantity
                    existing.used_margin = max(0.0, existing.used_margin - req_margin)
            pos_obj = existing
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
            self._positions[pos_id] = pos_obj

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
        )
        self._orders.insert(0, order)

        # Persist to Supabase if session and user_id available
        if session and user_id:
            try:
                await PaperTradingRepository.save_order(session, user_id, order)
                await PaperTradingRepository.upsert_position(session, user_id, pos_obj)
                updated_summary = await self.get_portfolio_summary(session, user_id)
                await PaperTradingRepository.update_portfolio(
                    session,
                    user_id,
                    available_margin=updated_summary.available_margin,
                    used_margin=updated_summary.used_margin,
                    realized_pnl=updated_summary.total_realized_pnl,
                )
            except Exception as e:
                logger.warning("failed_to_save_paper_trade_db", error=str(e))

        return order

    async def place_basket(
        self,
        payload: BasketOrderPayload,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
    ) -> list[VirtualOrder]:
        """Execute a multi-leg strategy basket."""
        results: list[VirtualOrder] = []
        for ord_payload in payload.orders:
            res = await self.place_order(ord_payload, session, user_id)
            results.append(res)
        return results

    async def square_off_position(
        self,
        position_id: str,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
    ) -> VirtualPosition:
        """Close an open position at current market price."""
        if position_id not in self._positions or not self._positions[position_id].is_open:
            raise ValueError(f"Open position not found: {position_id}")

        pos = self._positions[position_id]
        exit_side = "SELL" if pos.side == "BUY" else "BUY"

        exit_order = OrderPayload(
            symbol=pos.symbol,
            underlying=pos.underlying,
            side=exit_side,
            order_type="MARKET",
            product=pos.product,
            quantity=pos.quantity,
            price=pos.ltp,
        )
        await self.place_order(exit_order, session, user_id)
        return self._positions[position_id]

    async def square_off_all(
        self,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
    ) -> list[VirtualPosition]:
        """Emergency square off of all active positions."""
        closed: list[VirtualPosition] = []
        open_ids = [pid for pid, pos in self._positions.items() if pos.is_open]
        for pid in open_ids:
            try:
                c = await self.square_off_position(pid, session, user_id)
                closed.append(c)
            except Exception as e:
                logger.warning("square_off_failed", pid=pid, error=str(e))
        return closed

    async def reset_portfolio_async(
        self,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
    ) -> PortfolioSummary:
        """Reset virtual account to baseline state."""
        self._positions.clear()
        self._orders.clear()
        self._realized_pnl = 0.0

        if session and user_id:
            try:
                await PaperTradingRepository.reset_portfolio(session, user_id)
            except Exception as e:
                logger.warning("failed_to_reset_portfolio_db", error=str(e))

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

    def reset_portfolio(self) -> PortfolioSummary:
        """Sync reset for backwards compatibility."""
        self._positions.clear()
        self._orders.clear()
        self._realized_pnl = 0.0
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

    async def get_positions(
        self,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
    ) -> list[VirtualPosition]:
        """Retrieve all active and closed positions."""
        # Refresh MTM against current prices
        for pos in self._positions.values():
            if pos.is_open:
                try:
                    quote = await self.market_service.get_quote(pos.underlying)
                    drift = (quote.change / quote.previous_close) * 0.5
                    pos.ltp = round(max(0.5, pos.average_price * (1.0 + drift)), 2)
                    mult = 1 if pos.side == "BUY" else -1
                    pos.unrealized_pnl = round((pos.ltp - pos.average_price) * pos.quantity * mult, 2)
                except Exception:
                    pass

        return list(self._positions.values())

    async def get_orders_async(
        self,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
        limit: int = 50,
    ) -> list[VirtualOrder]:
        """Retrieve order log from Supabase or memory."""
        if session and user_id:
            try:
                db_orders = await PaperTradingRepository.get_orders(session, user_id, limit=limit)
                if db_orders:
                    return [self._db_to_order(o) for o in db_orders]
            except Exception as e:
                logger.warning("failed_to_get_orders_db", error=str(e))

        return self._orders

    def get_orders(self) -> list[VirtualOrder]:
        """Sync retrieve order log."""
        return self._orders

    async def get_portfolio_summary(
        self,
        session: Optional[AsyncSession] = None,
        user_id: Optional[UUID] = None,
    ) -> PortfolioSummary:
        """Calculate real-time account summary with margin & MTM."""
        positions = await self.get_positions(session, user_id)
        open_positions = [p for p in positions if p.is_open]

        total_unrealized = round(sum(p.unrealized_pnl for p in open_positions), 2)
        total_used_margin = round(sum(p.used_margin for p in open_positions), 2)
        total_pnl = round(self._realized_pnl + total_unrealized, 2)

        available_margin = round(max(0.0, self._initial_capital + total_pnl - total_used_margin), 2)
        margin_util = round((total_used_margin / self._initial_capital) * 100.0, 2) if self._initial_capital > 0 else 0.0

        return PortfolioSummary(
            virtual_capital=self._initial_capital,
            available_margin=available_margin,
            used_margin=total_used_margin,
            margin_utilization_pct=margin_util,
            total_realized_pnl=round(self._realized_pnl, 2),
            total_unrealized_pnl=total_unrealized,
            total_portfolio_pnl=total_pnl,
            open_positions_count=len(open_positions),
        )


paper_service = PaperTradingService()
