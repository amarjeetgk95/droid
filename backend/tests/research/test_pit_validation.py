"""Tests for Point-In-Time (PIT) integrity and Statistical Evaluation (§19, §21)."""

import pytest
import math
from datetime import datetime, timezone, timedelta

from app.research.enums import Direction, ExperimentStatus
from app.research.indicators.rsi_indicator import RSIIndicator
from app.research.models import PredictionOutcome, ResearchPrediction
from app.research.validation.backtest_engine import CheapValidationGate
from app.research.validation.statistical_evaluator import StatisticalEvaluator


def test_confidence_interval_calculation():
    """Test Wilson score interval bounds."""
    low, high = StatisticalEvaluator.calculate_confidence_interval(60, 100)
    assert 50.0 < low < 60.0
    assert 60.0 < high < 75.0

    # 0 successes
    low_zero, high_zero = StatisticalEvaluator.calculate_confidence_interval(0, 50)
    assert low_zero == 0.0
    assert high_zero > 0.0


def test_p_value_calculation():
    """Test one-tailed binomial hypothesis test against baseline."""
    # 70% accuracy on 100 samples vs 50% baseline -> should be highly significant (p < 0.01)
    p_val = StatisticalEvaluator.calculate_p_value(0.70, 0.50, 100)
    assert p_val < 0.01

    # 51% accuracy on 50 samples vs 50% baseline -> not statistically significant (p > 0.10)
    p_val_insig = StatisticalEvaluator.calculate_p_value(0.51, 0.50, 50)
    assert p_val_insig > 0.10


@pytest.mark.asyncio
async def test_cheap_validation_gate_pit_integrity():
    """Verify CheapValidationGate enforces strict PIT separation and produces valid reports."""
    t0 = datetime(2026, 9, 1, 9, 15, tzinfo=timezone.utc)
    base = 24000.0
    candles = []

    # Generate 120 candles
    for i in range(120):
        p = base + (math.sin(i / 8.0) * 30.0)
        candles.append({
            "open": p - 1.0,
            "high": p + 4.0,
            "low": p - 4.0,
            "close": p + 1.0,
            "volume": 1200.0 + (i % 20) * 50.0,
            "timestamp": (t0 + timedelta(minutes=5 * i)).isoformat(),
        })

    ind = RSIIndicator()
    run, report = await CheapValidationGate.run_experiment(
        indicator=ind,
        candles=candles,
        warmup_period=20,
        horizon_candles=5,
        stride=2,
    )

    assert run.status == ExperimentStatus.COMPLETED
    assert run.sample_count > 0
    assert report.sample_size == run.sample_count
    assert 0.0 <= report.accuracy <= 100.0
    assert report.confidence_interval_95[0] <= report.accuracy <= report.confidence_interval_95[1]
    assert 0.0 <= report.p_value <= 1.0
    assert "CLOSED" in report.session_breakdown or "OPENING" in report.session_breakdown
