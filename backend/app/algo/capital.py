"""
Capital Engine — §44-48

available = limit - deployed - reserved_pending
Atomic reservation with SERIALIZABLE / SELECT FOR UPDATE
Bounded lock wait 50ms, no indefinite queue.

DB is authoritative. Redis optional for coordination only.
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from decimal import Decimal
from dataclasses import dataclass
from uuid import UUID, uuid4
import structlog

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.algo.money import D

logger = structlog.get_logger()

LOCK_WAIT_MS = 50
MAX_RETRIES = 1


@dataclass
class CapitalSnapshot:
    account_id: UUID
    limit: Decimal
    deployed: Decimal
    reserved_pending: Decimal
    available: Decimal
    utilization_pct: Decimal


class CapitalEngine:
    """
    Transactionally protected capital reservations.
    Caller must pass an AsyncSession bound to DB.
    """

    async def get_snapshot(
        self,
        session: AsyncSession,
        account_id: UUID,
    ) -> CapitalSnapshot:
        # Use FOR UPDATE on capital_config to serialize? For snapshot we just read
        from app.algo.models import AlgoCapitalConfig, AlgoPositionDB, AlgoCapitalReservation  # local import

        # Lock capital row for consistency
        res = await session.execute(
            select(AlgoCapitalConfig).where(AlgoCapitalConfig.account_id == account_id).with_for_update(read=False)
        )
        cfg = res.scalar_one_or_none()
        limit = D(cfg.investment_limit) if cfg else D(3000)

        # Deployed = sum of open positions' capital_allocated / margin_used
        res2 = await session.execute(
            select(func.coalesce(func.sum(AlgoPositionDB.margin_used), 0)).where(
                AlgoPositionDB.account_id == account_id, AlgoPositionDB.is_open == True
            )
        )
        deployed = D(res2.scalar() or 0)

        res3 = await session.execute(
            select(func.coalesce(func.sum(AlgoCapitalReservation.amount), 0)).where(
                AlgoCapitalReservation.account_id == account_id,
                AlgoCapitalReservation.status == "RESERVED",
            )
        )
        reserved = D(res3.scalar() or 0)

        available = limit - deployed - reserved
        if available < D(0):
            available = D(0)
        util = ( (deployed + reserved) / limit * D(100) ) if limit > 0 else D(0)

        return CapitalSnapshot(
            account_id=account_id,
            limit=limit,
            deployed=deployed,
            reserved_pending=reserved,
            available=available,
            utilization_pct=util,
        )

    async def reserve(
        self,
        session: AsyncSession,
        account_id: UUID,
        client_order_id: UUID,
        amount: Decimal | float | str,
        lock_timeout_ms: int = LOCK_WAIT_MS,
    ) -> tuple[bool, str | None, UUID | None]:
        """
        Atomic reserve with bounded lock wait.
        Returns (success, reason, reservation_id)
        Pattern: BEGIN → Lock → Read → Validate → Reserve → Commit
        Do not hold locks while waiting for external systems (§47).
        """
        amt = D(amount)
        if amt <= D(0):
            return False, "INVALID_AMOUNT", None

        # Set lock timeout for this transaction
        try:
            await session.execute(text(f"SET LOCAL lock_timeout = '{lock_timeout_ms}ms'"))
        except Exception:
            pass  # sqlite / fallback — ignore

        reservation_id = uuid4()
        try:
            from app.algo.models import AlgoCapitalConfig, AlgoCapitalReservation

            # Acquire row lock
            res = await session.execute(
                select(AlgoCapitalConfig).where(AlgoCapitalConfig.account_id == account_id).with_for_update()
            )
            cfg = res.scalar_one_or_none()
            if cfg is None:
                # auto-create default config
                cfg = AlgoCapitalConfig(account_id=account_id, investment_limit=D(3000))
                session.add(cfg)
                await session.flush()
                limit = D(3000)
            else:
                limit = D(cfg.investment_limit)

            # Recompute snapshot under lock
            from sqlalchemy import func, select as sel
            from app.algo.models import AlgoPositionDB
            r2 = await session.execute(
                sel(func.coalesce(func.sum(AlgoPositionDB.margin_used), 0)).where(
                    AlgoPositionDB.account_id == account_id, AlgoPositionDB.is_open == True
                )
            )
            deployed = D(r2.scalar() or 0)
            r3 = await session.execute(
                sel(func.coalesce(func.sum(AlgoCapitalReservation.amount), 0)).where(
                    AlgoCapitalReservation.account_id == account_id,
                    AlgoCapitalReservation.status == "RESERVED",
                )
            )
            reserved = D(r3.scalar() or 0)
            available = limit - deployed - reserved

            if amt > available:
                return False, f"INSUFFICIENT_CAPITAL: need {amt} available {available} (limit {limit} deployed {deployed} reserved {reserved})", None

            # Also check max_capital_per_trade
            max_per_trade = D(cfg.max_capital_per_trade) if cfg.max_capital_per_trade else None
            if max_per_trade is not None and amt > max_per_trade:
                return False, f"EXCEEDS_MAX_CAPITAL_PER_TRADE: {amt} > {max_per_trade}", None

            row = AlgoCapitalReservation(
                account_id=account_id,
                reservation_id=reservation_id,
                client_order_id=client_order_id,
                amount=amt,
                status="RESERVED",
            )
            session.add(row)
            await session.flush()
            return True, None, reservation_id

        except Exception as e:
            msg = str(e).lower()
            if "lock timeout" in msg or "could not obtain lock" in msg or "lock_not_available" in msg:
                logger.warning("capital_lock_contention", account_id=str(account_id))
                return False, "LOCK_CONTENTION", None
            logger.error("capital_reserve_error", error=str(e))
            return False, f"CAPITAL_RESERVE_ERROR:{e}", None

    async def reserve_with_retry(
        self,
        session: AsyncSession,
        account_id: UUID,
        client_order_id: UUID,
        amount: Decimal | float | str,
    ) -> tuple[bool, str | None, UUID | None]:
        ok, reason, rid = await self.reserve(session, account_id, client_order_id, amount)
        if ok or reason != "LOCK_CONTENTION":
            return ok, reason, rid
        # One retry with jitter §48
        await asyncio.sleep(random.uniform(0.01, 0.05))
        # Need fresh transaction — caller should handle; we attempt second try on same session
        try:
            await session.rollback()
        except Exception:
            pass
        return await self.reserve(session, account_id, client_order_id, amount)

    async def release(self, session: AsyncSession, reservation_id: UUID) -> bool:
        from app.algo.models import AlgoCapitalReservation
        res = await session.execute(select(AlgoCapitalReservation).where(AlgoCapitalReservation.reservation_id == reservation_id))
        row = res.scalar_one_or_none()
        if not row or row.status != "RESERVED":
            return False
        row.status = "RELEASED"  # type: ignore
        row.released_at = datetime.now(timezone.utc)  # type: ignore
        await session.flush()
        return True

    async def consume(self, session: AsyncSession, reservation_id: UUID) -> bool:
        from app.algo.models import AlgoCapitalReservation
        res = await session.execute(select(AlgoCapitalReservation).where(AlgoCapitalReservation.reservation_id == reservation_id))
        row = res.scalar_one_or_none()
        if not row or row.status != "RESERVED":
            return False
        row.status = "CONSUMED"  # type: ignore
        await session.flush()
        return True

    async def check_limit_reduction(self, session: AsyncSession, account_id: UUID, new_limit: Decimal) -> dict:
        """
        §77: If new_limit < deployed → LIMIT_EXCEEDED, block new entries but don't force close.
        """
        snap = await self.get_snapshot(session, account_id)
        deployed = snap.deployed + snap.reserved_pending
        status = "OK"
        if D(new_limit) < deployed:
            status = "LIMIT_EXCEEDED"
        return {"status": status, "deployed": str(deployed), "new_limit": str(D(new_limit)), "available": str(D(new_limit) - deployed)}


capital_engine = CapitalEngine()
