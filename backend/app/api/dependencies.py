"""Shared helpers for the API route layer.

These were byte-identical copies living in individual routers
(``app.api.algo``, ``app.api.paper``): the optional user-id parse, the
canonical 401 gate, per-user algo account resolution, and the capital-config
load. A single implementation keeps response and error semantics from drifting
between routers.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.algo.algo_service import algo_account_service
from app.algo.models import AlgoAccount, AlgoCapitalConfig
from app.core.security import AuthUser


def parse_user_uuid(user: Optional[AuthUser]) -> Optional[UUID]:
    """Parse ``AuthUser.user_id`` into a UUID; None when absent or malformed."""
    if not user or not user.user_id:
        return None
    try:
        return UUID(user.user_id)
    except Exception:
        return None


def require_user_uuid(user: Optional[AuthUser]) -> UUID:
    """Return the caller's UUID or raise the canonical 401."""
    uid = parse_user_uuid(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication required")
    return uid


async def get_or_create_account(
    session: Optional[AsyncSession], user_id: UUID
) -> AlgoAccount:
    """Resolve the caller's algo account (DB-backed, else deterministic synthetic).

    Delegates to ``AlgoAccountService.get_or_create_account`` so the default
    capital config, kill-switch row, and synthetic fallback remain exactly as
    they were before the extraction.
    """
    return await algo_account_service.get_or_create_account(session, user_id)


async def get_capital_config(
    session: AsyncSession, account_id: UUID
) -> Optional[AlgoCapitalConfig]:
    """Load the account's capital config row, or None when absent."""
    res = await session.execute(
        select(AlgoCapitalConfig).where(AlgoCapitalConfig.account_id == account_id)
    )
    return res.scalar_one_or_none()
