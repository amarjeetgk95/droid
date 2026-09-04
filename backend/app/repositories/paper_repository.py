from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import PaperPortfolioDB, PaperOrderDB, PaperPositionDB
from app.models.paper import VirtualOrder, VirtualPosition


class PaperTradingRepository:
    """Async repository for Paper Trading Portfolios, Orders, and Positions."""

    @staticmethod
    async def get_or_create_portfolio(session: AsyncSession, user_id: UUID) -> PaperPortfolioDB:
        """Get or initialize user virtual portfolio balance."""
        stmt = select(PaperPortfolioDB).where(PaperPortfolioDB.user_id == user_id)
        result = await session.execute(stmt)
        portfolio = result.scalar_one_or_none()
        if portfolio is None:
            portfolio = PaperPortfolioDB(
                user_id=user_id,
                virtual_capital=1000000.0,
                available_margin=1000000.0,
                used_margin=0.0,
                realized_pnl=0.0,
            )
            session.add(portfolio)
            await session.commit()
            await session.refresh(portfolio)
        return portfolio

    @staticmethod
    async def update_portfolio(
        session: AsyncSession,
        user_id: UUID,
        available_margin: Optional[float] = None,
        used_margin: Optional[float] = None,
        realized_pnl: Optional[float] = None,
    ) -> PaperPortfolioDB:
        """Update portfolio margin and realized PnL."""
        portfolio = await PaperTradingRepository.get_or_create(session, user_id)
        if available_margin is not None:
            portfolio.available_margin = available_margin
        if used_margin is not None:
            portfolio.used_margin = used_margin
        if realized_pnl is not None:
            portfolio.realized_pnl = realized_pnl
        await session.commit()
        await session.refresh(portfolio)
        return portfolio

    @staticmethod
    async def get_or_create(session: AsyncSession, user_id: UUID) -> PaperPortfolioDB:
        return await PaperTradingRepository.get_or_create_portfolio(session, user_id)

    @staticmethod
    async def reset_portfolio(session: AsyncSession, user_id: UUID) -> PaperPortfolioDB:
        """Reset virtual capital to baseline and clear open positions."""
        portfolio = await PaperTradingRepository.get_or_create(session, user_id)
        portfolio.virtual_capital = 1000000.0
        portfolio.available_margin = 1000000.0
        portfolio.used_margin = 0.0
        portfolio.realized_pnl = 0.0

        # Close all positions
        stmt = delete(PaperPositionDB).where(PaperPositionDB.user_id == user_id)
        await session.execute(stmt)
        await session.commit()
        await session.refresh(portfolio)
        return portfolio

    @staticmethod
    async def save_order(session: AsyncSession, user_id: UUID, order: VirtualOrder) -> PaperOrderDB:
        """Save a virtual order record."""
        db_order = PaperOrderDB(
            order_id=order.order_id,
            user_id=user_id,
            symbol=order.symbol,
            underlying=order.underlying,
            side=order.side,
            order_type=order.order_type,
            product=order.product,
            quantity=order.quantity,
            price=order.price,
            trigger_price=order.trigger_price,
            status=order.status,
            fill_price=order.fill_price,
            rejection_reason=order.rejection_reason,
            timestamp=datetime.now(timezone.utc),
        )
        session.add(db_order)
        await session.commit()
        await session.refresh(db_order)
        return db_order

    @staticmethod
    async def get_orders(session: AsyncSession, user_id: UUID, limit: int = 50) -> list[PaperOrderDB]:
        """Fetch virtual order history for a user."""
        stmt = (
            select(PaperOrderDB)
            .where(PaperOrderDB.user_id == user_id)
            .order_by(PaperOrderDB.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_positions(session: AsyncSession, user_id: UUID, open_only: bool = False) -> list[PaperPositionDB]:
        """Fetch virtual positions for a user."""
        stmt = select(PaperPositionDB).where(PaperPositionDB.user_id == user_id)
        if open_only:
            stmt = stmt.where(PaperPositionDB.is_open == True)
        stmt = stmt.order_by(PaperPositionDB.updated_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def upsert_position(session: AsyncSession, user_id: UUID, position: VirtualPosition) -> PaperPositionDB:
        """Insert or update a virtual position."""
        stmt = select(PaperPositionDB).where(
            PaperPositionDB.user_id == user_id,
            PaperPositionDB.position_id == position.position_id,
        )
        result = await session.execute(stmt)
        db_pos = result.scalar_one_or_none()

        if db_pos is None:
            db_pos = PaperPositionDB(
                position_id=position.position_id,
                user_id=user_id,
                symbol=position.symbol,
                underlying=position.underlying,
                instrument_type=position.instrument_type,
                side=position.side,
                product=position.product,
                quantity=position.quantity,
                average_price=position.average_price,
                ltp=position.ltp,
                unrealized_pnl=position.unrealized_pnl,
                realized_pnl=position.realized_pnl,
                used_margin=position.used_margin,
                is_open=position.is_open,
            )
            session.add(db_pos)
        else:
            db_pos.quantity = position.quantity
            db_pos.average_price = position.average_price
            db_pos.ltp = position.ltp
            db_pos.unrealized_pnl = position.unrealized_pnl
            db_pos.realized_pnl = position.realized_pnl
            db_pos.used_margin = position.used_margin
            db_pos.is_open = position.is_open

        await session.commit()
        await session.refresh(db_pos)
        return db_pos
