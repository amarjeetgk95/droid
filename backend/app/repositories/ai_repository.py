from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import AIReportDB
from app.models.ai import AIInsightResponse, AIHistoryItem


class AIRepository:
    """Async repository for AI Intelligence Reports in Supabase PostgreSQL."""

    @staticmethod
    async def save_report(
        session: AsyncSession,
        report: AIInsightResponse,
        user_id: Optional[UUID] = None,
    ) -> AIReportDB:
        """Save a generated AI analysis report."""
        raw_json = report.model_dump(mode="json")
        db_record = AIReportDB(
            symbol=report.symbol.upper(),
            provider=report.provider_used,
            market_bias=report.market_bias,
            confidence=report.confidence,
            timestamp=report.timestamp,
            summary=report.executive_summary,
            raw_json=raw_json,
            user_id=user_id,
        )
        session.add(db_record)
        await session.commit()
        await session.refresh(db_record)
        return db_record

    @staticmethod
    async def get_history(
        session: AsyncSession,
        symbol: str,
        limit: int = 20,
    ) -> list[AIHistoryItem]:
        """Fetch historical AI reports for a symbol as summary items."""
        stmt = (
            select(AIReportDB)
            .where(AIReportDB.symbol == symbol.upper())
            .order_by(AIReportDB.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [
            AIHistoryItem(
                id=str(r.id)[:8],
                symbol=r.symbol,
                timestamp=r.timestamp,
                market_bias=r.market_bias,  # type: ignore
                confidence=r.confidence,
                executive_summary=r.summary,
            )
            for r in rows
        ]
