"""Causality and Anti-Lookahead Gate Tests for S6 (S6SPEC_v1.3)."""

import pytest
import polars as pl
import numpy as np
from datetime import datetime, timezone, timedelta

from app.quant.strategies.s6_config import create_default_config
from app.quant.strategies.s6_events import (
    S6EventEngine,
    resample_to_completed_5m,
    compute_5m_features,
    CausalityViolation,
)
from scripts.fetch_fyers_history import generate_synthetic_history


class TestS6Causality:

    @pytest.fixture
    def dataset(self) -> pl.DataFrame:
        np.random.seed(123)
        return generate_synthetic_history(symbol="NIFTY", days=2, base_price=25000.0)

    def test_truncation_invariance_5m_context(self, dataset: pl.DataFrame):
        """Assures features(t) on full dataset == features(t) on dataset truncated at t."""
        config = create_default_config()
        df_5m_full = resample_to_completed_5m(dataset)
        features_full = compute_5m_features(df_5m_full, config)

        checkpoints = [10, 25, 40, 50, len(df_5m_full) - 5]

        for k in checkpoints:
            truncated_5m = df_5m_full.slice(0, k)
            features_trunc = compute_5m_features(truncated_5m, config)

            row_full = features_full.row(k - 1, named=True)
            row_trunc = features_trunc.row(-1, named=True)

            # Compare atr5 and compression ratios
            v_full = row_full["atr5"]
            v_trunc = row_trunc["atr5"]
            if np.isnan(v_full) or np.isnan(v_trunc):
                assert np.isnan(v_full) and np.isnan(v_trunc), f"NaN mismatch at k={k}"
            else:
                diff_atr = abs(v_full - v_trunc)
                assert diff_atr < 1e-4, f"ATR5 lookahead leak at k={k}: full={v_full} vs trunc={v_trunc}"

            r_full = row_full["compression_atr_ratio"]
            r_trunc = row_trunc["compression_atr_ratio"]
            if r_full is not None and r_trunc is not None and not (np.isnan(r_full) or np.isnan(r_trunc)):
                diff_ratio = abs(r_full - r_trunc)
                assert diff_ratio < 1e-4, f"Compression ratio leak at k={k}"

    def test_compression_boundary_freeze_invariance(self, dataset: pl.DataFrame):
        """Compression boundaries must be frozen once compression ends and cannot change with future bars."""
        config = create_default_config()
        df_5m = resample_to_completed_5m(dataset)
        df_5m = compute_5m_features(df_5m, config)
        engine = S6EventEngine(config)

        episodes_full = engine.detect_compression_episodes(df_5m)
        if not episodes_full:
            return  # skip if no episodes in this synthetic seed

        first_ep = episodes_full[0]
        # Truncate dataset right at episode end_time + 1 bar
        end_idx = df_5m.filter(pl.col("available_at") <= first_ep.end_time).height
        truncated_df = df_5m.slice(0, end_idx + 2)
        episodes_trunc = engine.detect_compression_episodes(truncated_df)

        assert len(episodes_trunc) >= 1
        first_ep_trunc = episodes_trunc[0]
        assert first_ep.compression_high == first_ep_trunc.compression_high
        assert first_ep.compression_low == first_ep_trunc.compression_low
        assert first_ep.atr5 == first_ep_trunc.atr5
