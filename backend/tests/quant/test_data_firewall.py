"""Unit tests for DataQualityFirewall (Tier 0)."""

import pytest
import polars as pl
from datetime import datetime, timezone, timedelta

from app.quant.data.data_firewall import DataQualityFirewall


class TestDataQualityFirewall:

    def test_clean_session_data(self):
        """Standard market session data should pass with 100% score."""
        fw = DataQualityFirewall(session_only=True)
        # Create 10 bars from 09:15 to 09:24 IST (03:45 to 03:54 UTC) on a Monday
        base_time = datetime(2026, 9, 21, 3, 45, tzinfo=timezone.utc)
        timestamps = [base_time + timedelta(minutes=i) for i in range(10)]
        df = pl.DataFrame({
            "timestamp": timestamps,
            "open": [80000.0 + i for i in range(10)],
            "high": [80010.0 + i for i in range(10)],
            "low": [79990.0 + i for i in range(10)],
            "close": [80005.0 + i for i in range(10)],
            "volume": [500.0] * 10,
        })

        clean_df, report = fw.inspect_and_clean(df, instrument="SENSEX")
        assert report.status == "PASSED"
        assert report.score == 100.0
        assert len(clean_df) == 10
        assert report.invalid_ohlc_bars == 0
        assert report.duplicates_removed == 0

    def test_duplicate_timestamp_removal(self):
        """Duplicate timestamps must be detected and removed."""
        fw = DataQualityFirewall(session_only=True)
        base_time = datetime(2026, 9, 21, 3, 45, tzinfo=timezone.utc)
        timestamps = [base_time, base_time, base_time + timedelta(minutes=1)]
        df = pl.DataFrame({
            "timestamp": timestamps,
            "open": [80000.0, 80001.0, 80005.0],
            "high": [80010.0, 80011.0, 80015.0],
            "low": [79990.0, 79991.0, 79995.0],
            "close": [80005.0, 80006.0, 80010.0],
            "volume": [100.0, 100.0, 100.0],
        })

        clean_df, report = fw.inspect_and_clean(df)
        assert report.duplicates_removed == 1
        assert len(clean_df) == 2

    def test_invalid_ohlc_geometry(self):
        """Bars where low > open or high < close must be filtered out."""
        fw = DataQualityFirewall(session_only=True)
        base_time = datetime(2026, 9, 21, 3, 45, tzinfo=timezone.utc)
        df = pl.DataFrame({
            "timestamp": [base_time, base_time + timedelta(minutes=1)],
            "open": [80000.0, 80000.0],
            "high": [80010.0, 79980.0],  # Invalid: high < open/close
            "low": [79990.0, 80005.0],   # Invalid: low > open
            "close": [80005.0, 80000.0],
            "volume": [100.0, 100.0],
        })

        clean_df, report = fw.inspect_and_clean(df)
        assert report.invalid_ohlc_bars == 1
        assert len(clean_df) == 1

    def test_session_boundary_filtering(self):
        """Bars outside 09:15 - 15:30 IST or weekend bars must be dropped."""
        fw = DataQualityFirewall(session_only=True)
        # 03:00 UTC = 08:30 IST (pre-market, drop)
        # 03:45 UTC = 09:15 IST (market open, keep)
        # 11:00 UTC = 16:30 IST (post-market, drop)
        # Sunday 03:45 UTC (weekend, drop)
        t_pre = datetime(2026, 9, 21, 3, 0, tzinfo=timezone.utc)
        t_open = datetime(2026, 9, 21, 3, 45, tzinfo=timezone.utc)
        t_post = datetime(2026, 9, 21, 11, 0, tzinfo=timezone.utc)
        t_sun = datetime(2026, 9, 20, 3, 45, tzinfo=timezone.utc)

        df = pl.DataFrame({
            "timestamp": [t_pre, t_open, t_post, t_sun],
            "open": [80000.0] * 4,
            "high": [80010.0] * 4,
            "low": [79990.0] * 4,
            "close": [80005.0] * 4,
            "volume": [100.0] * 4,
        })

        clean_df, report = fw.inspect_and_clean(df)
        assert len(clean_df) == 1
        assert clean_df["timestamp"][0] == t_open
