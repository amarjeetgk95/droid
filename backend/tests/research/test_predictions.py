"""Unit tests for Research Predictions and Outcome Measurement (§26, N5)."""

import pytest
from datetime import datetime, timezone

from app.research.enums import Direction, ForecastHorizon
from app.research.models import PredictionOutcome, ResearchPrediction
from app.research.outcome_measurer import OutcomeMeasurer
from app.research.predictions import PredictionService


@pytest.mark.asyncio
async def test_prediction_recording_and_retrieval():
    """Test immutable prediction recording and retrieval."""
    now = datetime.now(timezone.utc)
    pred = ResearchPrediction(
        prediction_id="test_pred_01",
        indicator_id="ompi",
        indicator_version="0.1.0",
        instrument="NIFTY 50",
        timeframe="5m",
        timestamp=now,
        current_price=24200.0,
        direction=Direction.BULLISH,
        score=35.5,
        confidence=0.72,
        forecast_horizon=ForecastHorizon.HORIZON_15M,
        horizon_candles=5,
        target_price=24280.0,
        invalidation_price=24150.0,
    )

    pred_id = await PredictionService.record_prediction(pred)
    assert pred_id == "test_pred_01"

    fetched = await PredictionService.get_prediction("test_pred_01")
    assert fetched is not None
    assert fetched.direction == Direction.BULLISH
    assert fetched.score == 35.5


def test_outcome_measurer_bullish_target_hit():
    """Test OutcomeMeasurer on a favorable sequence reaching target price."""
    pred = ResearchPrediction(
        prediction_id="test_pred_target",
        indicator_id="rsi",
        indicator_version="1.0.0",
        instrument="NIFTY 50",
        timeframe="5m",
        timestamp=datetime.now(timezone.utc),
        current_price=24000.0,
        direction=Direction.BULLISH,
        score=40.0,
        confidence=0.8,
        target_price=24050.0,
        invalidation_price=23950.0,
    )

    forward_candles = [
        {"open": 24000.0, "high": 24020.0, "low": 23990.0, "close": 24015.0},
        {"open": 24015.0, "high": 24040.0, "low": 24005.0, "close": 24035.0},
        {"open": 24035.0, "high": 24060.0, "low": 24020.0, "close": 24055.0},  # Touches 24050 target
    ]

    outcome = OutcomeMeasurer.evaluate_forward_candles(pred, forward_candles)
    assert outcome.actual_direction == Direction.BULLISH
    assert outcome.target_hit is True
    assert outcome.stop_hit is False
    assert outcome.mfe == 60.0  # 24060 - 24000
    assert outcome.mae == 10.0  # 24000 - 23990
    assert outcome.is_correct is True


def test_outcome_measurer_bearish_stop_hit():
    """Test OutcomeMeasurer when price moves adversely against prediction."""
    pred = ResearchPrediction(
        prediction_id="test_pred_stop",
        indicator_id="rsi",
        indicator_version="1.0.0",
        instrument="NIFTY 50",
        timeframe="5m",
        timestamp=datetime.now(timezone.utc),
        current_price=24000.0,
        direction=Direction.BEARISH,
        score=-40.0,
        confidence=0.8,
        target_price=23950.0,
        invalidation_price=24050.0,
    )

    forward_candles = [
        {"open": 24000.0, "high": 24060.0, "low": 23995.0, "close": 24055.0},  # Breaches 24050 invalidation
    ]

    outcome = OutcomeMeasurer.evaluate_forward_candles(pred, forward_candles)
    assert outcome.actual_direction == Direction.BULLISH
    assert outcome.stop_hit is True
    assert outcome.is_correct is False
