"""Session Gap Detection Engine for Indian Trading Calendars."""

from __future__ import annotations
from datetime import date, datetime, timezone
from typing import List, Set
from zoneinfo import ZoneInfo
import polars as pl
import structlog

from app.historical_data.calendar.india import indian_calendar, IST_TZ
from app.historical_data.models.gap import DataGap

logger = structlog.get_logger(__name__)


class HistoricalGapDetector:
    """Detects missing trading session candles according to official exchange schedules."""

    def __init__(self, calendar=indian_calendar):
        self.calendar = calendar

    def detect_gaps(
        self,
        df: pl.DataFrame,
        dataset_id: str,
        start_date: date,
        end_date: date,
        timeframe: str = "1m",
    ) -> List[DataGap]:
        """Scan DataFrame for missing candles against official calendar schedule."""
        if timeframe.lower() not in ("1m", "1", "1min"):
            # Detailed intraday gap accounting is anchored to 1m baseline
            return []

        trading_days = self.calendar.get_trading_days(start_date, end_date)
        if not trading_days:
            return []

        # Extract set of existing candle timestamps converted to IST
        existing_ts_set: Set[datetime] = set()
        if not df.is_empty():
            ts_list = df["timestamp"].to_list()
            for ts in ts_list:
                if isinstance(ts, datetime):
                    ist_ts = ts.astimezone(IST_TZ) if ts.tzinfo else ts.replace(tzinfo=timezone.utc).astimezone(IST_TZ)
                    # Strip seconds/microseconds for clean 1m matching
                    ist_ts = ist_ts.replace(second=0, microsecond=0)
                    existing_ts_set.add(ist_ts)

        detected_gaps: List[DataGap] = []

        for day in trading_days:
            expected_timestamps = self.calendar.get_expected_1m_timestamps(day)
            expected_count = len(expected_timestamps)
            if expected_count == 0:
                continue

            missing_ts = [ts for ts in expected_timestamps if ts not in existing_ts_set]
            actual_count = expected_count - len(missing_ts)

            if missing_ts:
                gap = DataGap(
                    gap_id=f"gap_{dataset_id}_{day.strftime('%Y%m%d')}",
                    dataset_id=dataset_id,
                    trading_date=day,
                    expected_candles=expected_count,
                    actual_candles=actual_count,
                    missing_candles=len(missing_ts),
                    first_missing_ts=min(missing_ts).astimezone(timezone.utc),
                    last_missing_ts=max(missing_ts).astimezone(timezone.utc),
                    status="OPEN",
                )
                detected_gaps.append(gap)

        return detected_gaps


# Global gap detector instance
gap_detector = HistoricalGapDetector()
