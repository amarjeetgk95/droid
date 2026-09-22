"""Unit Tests for Historical Analogue & Regime Memory Engine (Tier 2).

Tests:
- 8D PCA regime space dimensionality reduction
- Temporal exclusion buffer (+/- 60 min) preventing single-event autocorrelation echo
- Causal boundary enforcement (t_historical < t_query)
- Metric calculation (win rate, mean return, dispersion, similarity score)
- Safe fallback for unindexed engine
"""

from datetime import datetime, timezone, timedelta
import pytest
import polars as pl
import numpy as np

from app.quant.historical.historical_analogue import (
    HistoricalAnalogueEngine,
    AnalogueContext,
    ANALOGUE_FEATURES,
)
from app.quant.features.feature_engine import CausalFeatureEngine
from app.quant.strategies.strategies import StrategyCandidate
from app.quant.labels.label_engine import BarrierOutcome
from scripts.fetch_fyers_history import generate_synthetic_history


class TestHistoricalAnalogue:

    @pytest.fixture
    def mock_market_data(self) -> pl.DataFrame:
        np.random.seed(42)
        raw = generate_synthetic_history("BSE:SENSEX-INDEX", days=5, base_price=80000.0)
        return CausalFeatureEngine().compute_features(raw)

    def test_analogue_engine_lifecycle_and_exclusion(self, mock_market_data):
        df_feat = mock_market_data
        n_bars = len(df_feat)
        timestamps = df_feat["timestamp"].to_list()

        # Create mock candidates spaced across the 5 days
        candidates: list[StrategyCandidate] = []
        outcomes: list[BarrierOutcome] = []
        net_returns: list[float] = []

        step = max(5, n_bars // 50)
        for i in range(10, n_bars - 20, step):
            candidates.append(StrategyCandidate(
                bar_index=i,
                direction=1 if i % 2 == 0 else -1,
                strategy_id="TEST_STRAT",
                entry_ref_price=float(df_feat["close"][i]),
                trigger_reason="test",
            ))
            outcomes.append(BarrierOutcome(
                t_start=timestamps[i + 1],
                t_end=timestamps[i + 10],
                entry_price=float(df_feat["open"][i + 1]),
                exit_price=float(df_feat["close"][i + 10]),
                gross_return=0.002 if i % 4 == 0 else -0.001,
                net_return=0.001 if i % 4 == 0 else -0.002,
                exit_reason="TARGET_HIT" if i % 4 == 0 else "STOP_HIT",
                bars_held=10,
                mfe=0.003,
                mae=-0.001,
                y_raw=1 if i % 4 == 0 else -1,
                y_net=1 if i % 4 == 0 else -1,
            ))
            net_returns.append(0.001 if i % 4 == 0 else -0.002)

        engine = HistoricalAnalogueEngine(
            n_components=8,
            k_neighbors=5,
            exclusion_window_minutes=60,
        )

        engine.build_index(df_feat, candidates, outcomes, net_returns)
        assert engine.is_indexed is True
        assert engine.projected_vectors.shape[1] <= 8

        # Query at candidate index 30
        query_cand = candidates[30]
        query_time = timestamps[query_cand.bar_index]

        context = engine.find_analogues(
            df_feat=df_feat,
            query_bar_idx=query_cand.bar_index,
            query_time=query_time,
            query_direction=query_cand.direction,
            k=5,
        )

        assert isinstance(context, AnalogueContext)
        assert len(context.top_neighbors) > 0
        assert 0.0 <= context.analogue_win_rate <= 1.0
        assert 0.0 <= context.regime_similarity_score <= 100.0

        # CRITICAL VERIFICATION:
        # Every retrieved neighbor MUST be strictly older than query_time - 60 minutes
        cutoff = query_time - timedelta(minutes=60)
        for neighbor in context.top_neighbors:
            assert neighbor.timestamp < cutoff, (
                f"Autocorrelation Leak! Neighbor time {neighbor.timestamp} is within 60m buffer of {query_time}"
            )
            assert neighbor.distance >= 0.0
            assert 0.0 <= neighbor.similarity <= 1.0

    def test_unindexed_engine_fallback(self, mock_market_data):
        engine = HistoricalAnalogueEngine()
        context = engine.find_analogues(
            df_feat=mock_market_data,
            query_bar_idx=10,
            query_time=datetime.now(timezone.utc),
            query_direction=1,
        )
        assert context.total_matches == 0
        assert context.has_historical_support is False
        assert context.regime_similarity_score == 50.0
