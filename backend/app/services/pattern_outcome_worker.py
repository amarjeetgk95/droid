"""Background worker for labeling pattern outcomes."""

import asyncio
from datetime import datetime, timezone
import structlog
from app.core.config import settings
from app.core.database import get_async_session_factory, is_database_configured
from app.repositories.pattern_outcome_repository import PatternOutcomeRepository
from app.services.market_service import MarketService
from app.services.regime_service import regime_service

logger = structlog.get_logger()


class PatternOutcomeWorker:
    """Background worker that labels pattern outcomes by fetching forward price data."""

    def __init__(self):
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._market_service = MarketService()
        self._interval_seconds = getattr(settings, "pattern_outcome_worker_interval", 3600)  # default 1 hour

    async def start(self) -> None:
        if self._running:
            return
        if not is_database_configured():
            logger.info("pattern_outcome_worker_skipped", reason="database_not_configured")
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("pattern_outcome_worker_started", interval_seconds=self._interval_seconds)

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("pattern_outcome_worker_stopped")

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._interval_seconds)
                await self._process_unlabeled()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("pattern_outcome_worker_error", error=str(e))

    async def _process_unlabeled(self) -> None:
        """Fetch and label outcomes for unlabeled patterns."""
        factory = get_async_session_factory()
        if not factory:
            return

        session = factory()
        try:
            # Get all symbols that have unlabeled patterns
            from sqlalchemy import select, distinct
            from app.models.database import PatternOutcomeDB

            stmt = select(distinct(PatternOutcomeDB.symbol)).where(
                PatternOutcomeDB.outcome_labeled_at.is_(None)
            )
            result = await session.execute(stmt)
            symbols = [row[0] for row in result.all()]

            if not symbols:
                return

            logger.info("pattern_outcome_worker_processing", symbols=symbols)

            total_labeled = 0
            for symbol in symbols:
                try:
                    unlabeled = await PatternOutcomeRepository.get_unlabeled(session, symbol, limit=50)
                    if not unlabeled:
                        continue

                    for record in unlabeled:
                        try:
                            outcomes = await self._compute_outcomes_from_candles(
                                record.symbol,
                                record.detection_timestamp,
                                record.timeframe,
                                record.trigger_price,
                                record.invalidation_level,
                                record.target_level,
                                record.bias,
                            )
                            if outcomes:
                                await PatternOutcomeRepository.update_outcomes(
                                    session=session,
                                    outcome_id=record.id,
                                    outcome_1d=outcomes.get("1d"),
                                    outcome_3d=outcomes.get("3d"),
                                    outcome_5d=outcomes.get("5d"),
                                    hit_target_before_invalidation=outcomes.get("hit_target"),
                                    outcome_source="background_worker",
                                )
                                total_labeled += 1
                        except Exception as e:
                            logger.warning(
                                "pattern_outcome_label_fail",
                                symbol=record.symbol,
                                record_id=str(record.id),
                                error=str(e),
                            )
                except Exception as e:
                    logger.warning("pattern_outcome_symbol_fail", symbol=symbol, error=str(e))

            if total_labeled > 0:
                logger.info("pattern_outcome_worker_labeled", count=total_labeled)
                # Refresh materialized view
                try:
                    await PatternOutcomeRepository.refresh_materialized_view(session)
                except Exception as e:
                    logger.warning("pattern_outcome_view_refresh_fail", error=str(e))

        finally:
            await session.close()

    async def _compute_outcomes_from_candles(
        self,
        symbol: str,
        detection_time: datetime,
        timeframe: str,
        trigger_price: float,
        invalidation_level: float,
        target_level: float,
        bias: str,
    ) -> dict:
        """Compute forward outcomes by fetching candles after detection."""
        try:
            from datetime import timedelta

            days_needed = 5
            end_time = detection_time + timedelta(days=days_needed + 2)  # buffer for weekends

            candles = await self._market_service.get_candles(
                symbol, timeframe="1D", start=detection_time, end=end_time
            )

            if len(candles) < 2:
                return {}

            # Find the first candle after detection (open of next day)
            next_day_open = candles[1].open if len(candles) > 1 else candles[0].close

            outcomes = {}
            hit_target = False

            for horizon_days, horizon_label in [(1, "1d"), (3, "3d"), (5, "5d")]:
                if len(candles) > horizon_days:
                    horizon_close = candles[horizon_days].close
                    pct_change = ((horizon_close - next_day_open) / next_day_open) * 100
                    outcomes[horizon_label] = round(pct_change, 2)

                    # Check if target or invalidation was hit first
                    if bias == "BULLISH":
                        if not hit_target and horizon_close >= target_level:
                            hit_target = True
                        elif horizon_close <= invalidation_level:
                            hit_target = False
                    else:  # BEARISH
                        if not hit_target and horizon_close <= target_level:
                            hit_target = True
                        elif horizon_close >= invalidation_level:
                            hit_target = False

            outcomes["hit_target"] = hit_target
            return outcomes
        except Exception as e:
            logger.warning("outcome_compute_fail", symbol=symbol, error=str(e))
            return {}


pattern_outcome_worker = PatternOutcomeWorker()