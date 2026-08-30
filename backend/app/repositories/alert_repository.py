from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import AlertRuleDB, AlertHistoryDB
from app.models.alert import AlertPayload


class AlertRepository:
    """Async repository for Alert Rules and Alert History."""

    @staticmethod
    async def get_by_user(session: AsyncSession, user_id: UUID) -> list[AlertRuleDB]:
        """Fetch all alert rules for a user."""
        stmt = select(AlertRuleDB).where(AlertRuleDB.user_id == user_id).order_by(AlertRuleDB.created_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_all_active(session: AsyncSession) -> list[AlertRuleDB]:
        """Fetch all active alert rules across users for evaluation."""
        stmt = select(AlertRuleDB).where(AlertRuleDB.is_active == True)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(session: AsyncSession, rule_id: UUID) -> Optional[AlertRuleDB]:
        """Fetch a single alert rule by ID."""
        stmt = select(AlertRuleDB).where(AlertRuleDB.id == rule_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, user_id: UUID, payload: AlertPayload) -> AlertRuleDB:
        """Create a new alert rule."""
        rule = AlertRuleDB(
            user_id=user_id,
            name=payload.name,
            symbol=payload.symbol.upper(),
            alert_type=payload.alert_type,
            condition=payload.condition,
            threshold=payload.threshold,
            channel=payload.channel,
            webhook_url=payload.webhook_url,
            is_active=True,
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
        return rule

    @staticmethod
    async def toggle(session: AsyncSession, rule_id: UUID, user_id: UUID) -> Optional[AlertRuleDB]:
        """Toggle active/disabled state for a user's alert rule."""
        rule = await AlertRepository.get_by_id(session, rule_id)
        if rule is None or rule.user_id != user_id:
            return None
        rule.is_active = not rule.is_active
        await session.commit()
        await session.refresh(rule)
        return rule

    @staticmethod
    async def update_last_triggered(session: AsyncSession, rule_id: UUID) -> None:
        """Update last_triggered timestamp for a rule."""
        now = datetime.now(timezone.utc)
        stmt = update(AlertRuleDB).where(AlertRuleDB.id == rule_id).values(last_triggered=now)
        await session.execute(stmt)
        await session.commit()

    @staticmethod
    async def delete(session: AsyncSession, rule_id: UUID, user_id: UUID) -> bool:
        """Delete an alert rule."""
        rule = await AlertRepository.get_by_id(session, rule_id)
        if rule is None or rule.user_id != user_id:
            return False
        stmt = delete(AlertRuleDB).where(AlertRuleDB.id == rule_id)
        await session.execute(stmt)
        await session.commit()
        return True

    @staticmethod
    async def record_trigger(
        session: AsyncSession,
        user_id: UUID,
        alert_name: str,
        symbol: str,
        triggered_value: float,
        threshold_value: float,
        message: str,
        channel_dispatched: str = "IN_APP",
        alert_id: Optional[UUID] = None,
    ) -> AlertHistoryDB:
        """Record an alert trigger in the audit log."""
        log = AlertHistoryDB(
            alert_id=alert_id,
            user_id=user_id,
            alert_name=alert_name,
            symbol=symbol,
            triggered_value=triggered_value,
            threshold_value=threshold_value,
            message=message,
            channel_dispatched=channel_dispatched,
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log

    @staticmethod
    async def get_history(session: AsyncSession, user_id: UUID, limit: int = 50) -> list[AlertHistoryDB]:
        """Fetch alert trigger history for a user."""
        stmt = (
            select(AlertHistoryDB)
            .where(AlertHistoryDB.user_id == user_id)
            .order_by(AlertHistoryDB.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
