"""Unit tests for S6 Shared Event Engine (S6SPEC_v1.3)."""

import pytest
import polars as pl
import numpy as np
from datetime import datetime, timezone, timedelta

from app.quant.strategies.s6_config import create_default_config, S6TimeframeBranch
from app.quant.strategies.s6_events import (
    S6EventEngine,
    resample_to_completed_5m,
    compute_5m_features,
    CausalityViolation,
)
from scripts.fetch_fyers_history import generate_synthetic_history


class TestS6Events:

    @pytest.fixture
    def synthetic_data(self) -> pl.DataFrame:
        np.random.seed(42)
        return generate_synthetic_history(symbol="NIFTY", days=3, base_price=25000.0)

    def test_5m_resampling_alignment(self, synthetic_data: pl.DataFrame):
        """Verifies 5m bars have available_at = bar_open_time + 5m."""
        df_5m = resample_to_completed_5m(synthetic_data)
        assert len(df_5m) > 0
        assert "available_at" in df_5m.columns
        assert "bar_open_time" in df_5m.columns

        for row in df_5m.iter_rows(named=True):
            expected_avail = row["bar_open_time"] + timedelta(minutes=5)
            assert row["available_at"] == expected_avail

    def test_causality_guard_forming_candle(self, synthetic_data: pl.DataFrame):
        """At 09:23, the 09:20-09:25 5m bar is incomplete and CANNOT be exposed."""
        df_5m = resample_to_completed_5m(synthetic_data)
        config = create_default_config()
        engine = S6EventEngine(config)

        # First date in dataset
        d0 = df_5m["bar_open_time"][0]
        # Construct 09:23 timestamp
        t_0923 = d0.replace(hour=3, minute=53)  # UTC equivalent or local
        if hasattr(t_0923, "tzinfo") and t_0923.tzinfo:
            t_as_of = d0 + timedelta(minutes=8) # 8 mins after start -> 1st 5m bar is available, 2nd is forming
        else:
            t_as_of = d0 + timedelta(minutes=8)

        context_at_t = engine.get_context_at(df_5m, as_of=t_as_of)
        # All bars in context_at_t must satisfy available_at <= t_as_of
        for row in context_at_t.iter_rows(named=True):
            assert row["available_at"] <= t_as_of

    def test_shared_event_generation_t1_and_t4(self, synthetic_data: pl.DataFrame):
        """Verifies shared event engine detects compression, raw breakouts, and failures."""
        config_t1 = create_default_config(timeframe_branch=S6TimeframeBranch.T1_5M_1M)
        df_5m = resample_to_completed_5m(synthetic_data)
        df_5m = compute_5m_features(df_5m, config_t1)

        engine_t1 = S6EventEngine(config_t1)
        episodes = engine_t1.detect_compression_episodes(df_5m, instrument="NIFTY")
        assert isinstance(episodes, list)

        # Raw breakouts on 1m execution
        breakouts_1m = engine_t1.detect_raw_breakouts(
            df_exec=synthetic_data,
            df_5m=df_5m,
            episodes=episodes,
            timeframe="1m",
        )
        assert isinstance(breakouts_1m, list)

        # Failures monitored on 1m
        failures_1m = engine_t1.detect_failures(
            df_exec=synthetic_data,
            episodes=episodes,
            raw_breakouts=breakouts_1m,
        )
        assert isinstance(failures_1m, list)
        for f in failures_1m:
            assert f.direction in (1, -1)
            assert f.bars_since_breakout <= 5

        # Raw breakouts on 5m execution (T4)
        config_t4 = create_default_config(timeframe_branch=S6TimeframeBranch.T4_5M_5M)
        engine_t4 = S6EventEngine(config_t4)
        breakouts_5m = engine_t4.detect_raw_breakouts(
            df_exec=df_5m,
            df_5m=df_5m,
            episodes=episodes,
            timeframe="5m",
        )
        assert isinstance(breakouts_5m, list)
        for bo in breakouts_5m:
            assert bo.timeframe == "5m"
