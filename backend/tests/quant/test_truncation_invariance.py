"""Truncation Invariance & Anti-Lookahead Gate Test Suite (Tier 0).

Mandatory CI test (§19):
Assures that for every timestamp t:
feature(t) on the full dataset == feature(t) on the dataset truncated at t.

If any feature uses future information (e.g. lookahead rolling, global normalization,
non-causal centering), this test raises an AssertionError and blocks deployment.
"""

import pytest
import polars as pl
import numpy as np
from datetime import datetime, timezone, timedelta

from app.quant.features.feature_engine import CausalFeatureEngine
from scripts.fetch_fyers_history import generate_synthetic_history


class TestTruncationInvariance:

    @pytest.fixture
    def dataset(self) -> pl.DataFrame:
        """Generate a reproducible 3-day intraday dataset."""
        np.random.seed(42)
        return generate_synthetic_history(symbol="BSE:SENSEX-INDEX", days=3, base_price=80000.0)

    def test_truncation_invariance_across_bars(self, dataset: pl.DataFrame):
        """Assert feature values at bar t are identical whether computed on full history or truncated at t."""
        engine = CausalFeatureEngine()
        full_features = engine.compute_features(dataset)

        # Test at multiple intraday checkpoints:
        # Bar 50 (mid morning), Bar 200 (lunch), Bar 370 (near close), Bar 500 (day 2)
        checkpoints = [50, 100, 200, 370, 450, 600, 750]
        
        numeric_cols = [
            "return_1m", "return_3m", "return_5m", "return_15m",
            "vwap", "vwap_distance", "std_dev_vwap", "vwap_upper_2std", "vwap_lower_2std",
            "ema_fast", "ema_slow", "ema_20", "ema_50", "ema_slope_50",
            "candle_body_ratio", "upper_wick_ratio", "lower_wick_ratio", "absorption_ratio_5",
            "volume_ratio", "atr", "atr_pct", "rsi", "or_high", "or_low"
        ]

        for t in checkpoints:
            truncated_raw = dataset.slice(0, t)
            truncated_features = engine.compute_features(truncated_raw)

            # Last row of truncated_features corresponds to index t - 1
            row_trunc = truncated_features.row(-1, named=True)
            row_full = full_features.row(t - 1, named=True)

            for col in numeric_cols:
                val_trunc = row_trunc.get(col)
                val_full = row_full.get(col)

                if val_trunc is None or val_full is None:
                    assert val_trunc is None and val_full is None, (
                        f"Lookahead leak at t={t} for column {col}: "
                        f"truncated={val_trunc} vs full={val_full}"
                    )
                    continue

                if np.isnan(val_trunc) or np.isnan(val_full):
                    assert np.isnan(val_trunc) and np.isnan(val_full), (
                        f"NaN mismatch at t={t} for column {col}: "
                        f"truncated={val_trunc} vs full={val_full}"
                    )
                    continue

                diff = abs(val_trunc - val_full)
                assert diff < 1e-5, (
                    f"LOOKAHEAD DETECTED at t={t} for column {col}: "
                    f"truncated={val_trunc:.7f} vs full={val_full:.7f} (diff={diff:.2e})"
                )

    def test_feature_version_hash_stability(self):
        """Feature hash must remain deterministic across instances with same parameters."""
        engine1 = CausalFeatureEngine(ema_fast=9, ema_slow=21)
        engine2 = CausalFeatureEngine(ema_fast=9, ema_slow=21)
        assert engine1.feature_hash == engine2.feature_hash

        engine3 = CausalFeatureEngine(ema_fast=10, ema_slow=21)
        assert engine1.feature_hash != engine3.feature_hash
