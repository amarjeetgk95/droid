"""Unit tests for Feature Engine v02 extensions.

Verifies structural levels, absorption metrics, directional streak,
and causality guarantees.
"""

import pytest
import polars as pl
import numpy as np
from datetime import datetime, timezone, timedelta

from app.quant.features.feature_engine import CausalFeatureEngine
from scripts.fetch_fyers_history import generate_synthetic_history


class TestFeatureEngineV02:

    @pytest.fixture
    def multi_day_dataset(self) -> pl.DataFrame:
        """Generates 3 full trading days of synthetic 1m data for SENSEX."""
        return generate_synthetic_history("BSE:SENSEX-INDEX", days=3, base_price=80000.0)

    def test_new_feature_columns_present(self, multi_day_dataset: pl.DataFrame):
        engine = CausalFeatureEngine()
        df = engine.compute_features(multi_day_dataset)

        expected_cols = [
            "prev_day_high",
            "prev_day_low",
            "price_displacement",
            "directional_streak",
            "distance_to_prev_high",
            "distance_to_prev_low",
            "wick_rejection_ratio",
            "vwap_band_touch",
        ]

        for col in expected_cols:
            assert col in df.columns, f"Expected column {col} missing from feature DataFrame"

    def test_prev_day_high_low_strictly_causal(self, multi_day_dataset: pl.DataFrame):
        """Verifies Day 1 has null prev_day_high/low, Day 2 has Day 1 high/low."""
        engine = CausalFeatureEngine()
        df = engine.compute_features(multi_day_dataset)

        # First 375 bars (Day 1): prev_day_high and prev_day_low must be None
        day1_prev_high = df["prev_day_high"].slice(0, 375).to_list()
        assert all(x is None for x in day1_prev_high), "Day 1 must not have prev_day_high"

        # Day 1 actual max high
        day1_actual_max = multi_day_dataset["high"].slice(0, 375).max()
        day1_actual_min = multi_day_dataset["low"].slice(0, 375).min()

        # Day 2 bars (375 to 750): prev_day_high must equal day1_actual_max
        day2_prev_high = df["prev_day_high"].slice(375, 375).to_list()
        day2_prev_low = df["prev_day_low"].slice(375, 375).to_list()

        assert all(abs(x - day1_actual_max) < 1e-4 for x in day2_prev_high if x is not None)
        assert all(abs(x - day1_actual_min) < 1e-4 for x in day2_prev_low if x is not None)

    def test_price_displacement_non_negative(self, multi_day_dataset: pl.DataFrame):
        engine = CausalFeatureEngine()
        df = engine.compute_features(multi_day_dataset)

        disp = df["price_displacement"].drop_nulls().to_list()
        assert len(disp) > 0
        assert all(x >= 0.0 for x in disp)

    def test_directional_streak_counts(self):
        """Tests directional streak with a deterministic synthetic price series."""
        # 10 bars: up, up, up, down, down, flat, up
        base_time = datetime(2026, 9, 15, 3, 45, tzinfo=timezone.utc)
        timestamps = [base_time + timedelta(minutes=i) for i in range(7)]
        closes = [100.0, 101.0, 102.0, 103.0, 101.0, 99.0, 99.0]
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        opens = [c - 0.5 for c in closes]
        volumes = [1000.0] * 7

        raw_df = pl.DataFrame({
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        })

        engine = CausalFeatureEngine(vol_lookback=2)
        df = engine.compute_features(raw_df)

        streaks = df["directional_streak"].to_list()
        # bar 0: 0
        # bar 1: +1 (100 -> 101)
        # bar 2: +2 (101 -> 102)
        # bar 3: +3 (102 -> 103)
        # bar 4: -1 (103 -> 101)
        # bar 5: -2 (101 -> 99)
        # bar 6: 0 (99 -> 99 flat)
        assert streaks == [0, 1, 2, 3, -1, -2, 0]

    def test_wick_rejection_ratio_bounds(self, multi_day_dataset: pl.DataFrame):
        engine = CausalFeatureEngine()
        df = engine.compute_features(multi_day_dataset)

        wicks = df["wick_rejection_ratio"].drop_nulls().to_list()
        assert len(wicks) > 0
        assert all(0.0 <= x <= 1.0 + 1e-4 for x in wicks)

    def test_vwap_band_touch_binary(self, multi_day_dataset: pl.DataFrame):
        engine = CausalFeatureEngine()
        df = engine.compute_features(multi_day_dataset)

        touches = df["vwap_band_touch"].to_list()
        assert set(touches).issubset({0, 1})
