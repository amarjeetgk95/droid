"""Unit tests for the 1-hour trend forecast orchestrator."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.research.enums import Direction
from app.research.trend_forecast import TrendForecast1H


def _make_candles(start_price: float, count: int, minutes: int = 60):
    """Generate a simple upward trending OHLCV series."""
    base = datetime(2026, 9, 7, 9, 15, tzinfo=timezone.utc)
    candles = []
    for i in range(count):
        price = start_price + i * 2.0
        candles.append({
            "open": price - 1.0,
            "high": price + 2.0,
            "low": price - 2.0,
            "close": price,
            "volume": 1000.0 + i * 10.0,
            "timestamp": (base + timedelta(minutes=minutes * i)).isoformat(),
        })
    return candles


@pytest.fixture
def mock_market_service():
    ms = MagicMock()
    candles_1h = _make_candles(24000.0, 60, minutes=60)
    candles_5m = _make_candles(24000.0, 200, minutes=5)
    candles_15m = _make_candles(24000.0, 80, minutes=15)
    candles_1m = _make_candles(24000.0, 500, minutes=1)
    ms.get_candles = AsyncMock(side_effect=lambda symbol, timeframe: {
        "1h": candles_1h,
        "5m": candles_5m,
        "15m": candles_15m,
        "1m": candles_1m,
        "4h": candles_1h[-20:],
        "1D": candles_1h[-10:],
    }.get(timeframe, []))
    return ms


@pytest.fixture
def mock_ml_predictor():
    mp = MagicMock()
    response = MagicMock()
    response.bullish_pct = 55.0
    response.bearish_pct = 25.0
    response.neutral_pct = 20.0
    response.predicted_bias = "BULLISH"
    response.trend_strength = 62.0
    response.confidence_score = 70.0
    response.model_source = "heuristic_ensemble"
    response.calibrated = False
    mp.predict_probabilities = AsyncMock(return_value=response)
    return mp


@pytest.mark.asyncio
async def test_1h_forecast_ensemble(mock_market_service, mock_ml_predictor):
    """TrendForecast1H should ensemble all mechanics into a directional forecast."""
    forecaster = TrendForecast1H(
        market_service=mock_market_service,
        ml_predictor=mock_ml_predictor,
    )
    result = await forecaster.forecast(instrument="NIFTY 50", record=False)

    assert result["instrument"] == "NIFTY 50"
    assert result["timeframe"] == "1h"
    assert result["forecast_horizon"] == "1h"
    assert result["direction"] in {"BULLISH", "BEARISH", "NEUTRAL"}
    assert -100.0 <= result["score"] <= 100.0
    assert 0.0 <= result["confidence"] <= 1.0
    assert "layer_scores" in result
    assert "mtf_features" in result
    assert "indicator_outputs" in result
    assert "ml_forecast" in result

    # Should include all indicator layers
    layer_scores = result["layer_scores"]
    assert "mtf_alignment" in layer_scores
    assert "indicators" in layer_scores
    assert "ml" in layer_scores
    assert "options" in layer_scores
    assert "structure" in layer_scores


@pytest.mark.asyncio
async def test_1h_forecast_records_prediction(mock_market_service, mock_ml_predictor):
    """When record=True, an immutable prediction_id should be returned."""
    forecaster = TrendForecast1H(
        market_service=mock_market_service,
        ml_predictor=mock_ml_predictor,
    )
    result = await forecaster.forecast(instrument="NIFTY 50", record=True)
    assert "prediction_id" in result
    assert result["prediction_id"].startswith("forecast_1h_")


def test_ensemble_forecast_neutral_when_no_data():
    """Ensemble should degrade gracefully when mechanics layers are empty."""
    forecaster = TrendForecast1H()
    mtf_features = {
        "instrument": "NIFTY 50",
        "per_timeframe": {},
        "alignment": {
            "overall_bias": "NEUTRAL",
            "alignment_score": 0.0,
        },
    }
    result = forecaster.ensemble_forecast(
        mtf_features=mtf_features,
        indicator_outputs=[],
        ml_forecast=None,
        options_ctx={"available": False},
        current_price=24000.0,
    )
    assert result["direction"] == "NEUTRAL"
    assert result["score"] == 0.0
    assert result["target_price"] is None
    assert result["invalidation_price"] is None
