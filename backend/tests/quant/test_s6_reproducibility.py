"""Reproducibility & Shared Event Fairness Tests for S6 (S6SPEC_v1.3)."""

import pytest
import polars as pl
import numpy as np

from app.quant.strategies.s6_config import create_default_config, S6Variant, S6TimeframeBranch
from app.quant.research.s6_runner import run_s6_track
from scripts.fetch_fyers_history import generate_synthetic_history


class TestS6Reproducibility:

    @pytest.fixture
    def dataset(self) -> pl.DataFrame:
        np.random.seed(999)
        return generate_synthetic_history(symbol="NIFTY", days=4, base_price=25000.0)

    def test_s6_track_deterministic_reproducibility(self, dataset: pl.DataFrame):
        """Running the same track twice on the same dataset must yield identical metrics and trades."""
        m1, trades1, _ = run_s6_track("NIFTY", "S6A_T1", dataset)
        m2, trades2, _ = run_s6_track("NIFTY", "S6A_T1", dataset)

        assert m1.total_candidates == m2.total_candidates
        assert m1.total_trades == m2.total_trades
        assert m1.net_expectancy_R == m2.net_expectancy_R
        assert m1.profit_factor == m2.profit_factor
        assert len(trades1) == len(trades2)

        for t1, t2 in zip(trades1, trades2):
            assert t1.candidate_id == t2.candidate_id
            assert t1.entry_price == t2.entry_price
            assert t1.exit_price == t2.exit_price
            assert t1.net_R == t2.net_R
            assert t1.exit_reason == t2.exit_reason

    def test_shared_breakout_universe_between_s6_a_and_s6_f(self, dataset: pl.DataFrame):
        """Section 52 Fairness Test: S6-A and S6-F must evaluate the exact same RawBreakoutEvent count."""
        m_a, _, _ = run_s6_track("NIFTY", "S6A_T1", dataset)
        m_f, _, _ = run_s6_track("NIFTY", "S6F_T1", dataset)

        # Both tracks consume the identical raw breakout universe
        assert m_a.raw_breakouts == m_f.raw_breakouts
        assert m_a.compression_episodes == m_f.compression_episodes
