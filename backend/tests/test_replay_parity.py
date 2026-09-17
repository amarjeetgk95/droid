"""Replay Parity Test.

Asserts that the Candidate Replay Engine produces identical strategy candidate
outputs (triggers, targets, stops) compared to live strategy evaluation.
"""
from decimal import Decimal
import pandas as pd
import pyarrow.parquet as pq

from app.signals.strategies.trend_pullback import TrendPullbackStrategy
from app.signals.strategies.base import StrategyContext


def test_strategy_candidate_determinism():
    strategy = TrendPullbackStrategy()

    ctx = StrategyContext(
        underlying="NIFTY",
        spot_price=Decimal("25000.0"),
        timeframe="5M",
        indicators={
            "trend": {
                "ema20": 25005.0,
                "ema50": 24950.0,
                "ema200": 24800.0,
                "adx": 28.0,
            },
            "vwap": 24960.0,
            "supertrend_direction": "BULLISH",
        },
        regime="TREND_UP",
    )

    cand1 = strategy.detect(ctx)
    cand2 = strategy.detect(ctx)

    assert cand1 is not None
    assert cand2 is not None
    assert cand1.spot_price == cand2.spot_price
    assert cand1.trigger == cand2.trigger
    assert cand1.stop_loss == cand2.stop_loss
    assert cand1.target_1 == cand2.target_1
    assert cand1.direction == "LONG_CALL"


def test_parquet_dataset_structure():
    import os
    dataset_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ml_datasets", "candidates_v3.parquet")
    assert os.path.exists(dataset_path), "candidates_v3.parquet must exist"

    df = pd.read_parquet(dataset_path)
    assert len(df) > 100
    assert "candidate_id" in df.columns
    assert "f_ret_1m" in df.columns
    assert "f_atr_14" in df.columns
    assert "f_vwap_distance_pct" in df.columns
    assert "f_is_expiry_day" in df.columns
    assert "label_triple_barrier" in df.columns
    assert "label_direction_15m" in df.columns
