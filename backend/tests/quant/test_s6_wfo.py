"""Unit tests for S6 Walk-Forward Splitter (S6SPEC_v1.3)."""

import pytest
import polars as pl
import numpy as np
from datetime import datetime, timezone, timedelta

from app.quant.research.s6_wfo import S6WalkForwardSplitter
from scripts.fetch_fyers_history import generate_synthetic_history


class TestS6WFO:

    @pytest.fixture
    def dataset(self) -> pl.DataFrame:
        np.random.seed(42)
        return generate_synthetic_history(symbol="NIFTY", days=10, base_price=25000.0)

    def test_wfo_chronological_splits_and_purging(self, dataset: pl.DataFrame):
        splitter = S6WalkForwardSplitter(
            train_days=5,
            oos_days=2,
            roll_days=2,
            purge_bars=15,
        )
        folds = splitter.split(dataset)
        assert len(folds) >= 1

        for fold in folds:
            # Chronological integrity: train strictly before OOS
            assert fold.train_end < fold.oos_start
            assert fold.purged_bars_count == 15
            # Zero overlap between train and OOS index sets
            train_set = set(fold.train_indices)
            oos_set = set(fold.oos_indices)
            assert len(train_set.intersection(oos_set)) == 0
