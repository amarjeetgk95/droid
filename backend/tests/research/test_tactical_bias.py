"""Unit tests for TacticalHorizonEngine and the Tactical Horizon Bias overhaul."""

import math
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.research.enums import Direction
from app.research.trend_forecast import (
    LAYER_WEIGHTS,
    REGIME_LAYER_WEIGHTS,
    TacticalHorizonEngine,
    TrendForecast1H,
    TrendForecaster,
    get_regime_layer_weights,
    tactical_horizon_engine,
    trend_forecast_1h,
    trend_forecaster,
)


def _make_candles(start_price: float, count: int, minutes: int = 60):
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
    response.bullish_pct = 60.0
    response.bearish_pct = 20.0
    response.neutral_pct = 20.0
    response.predicted_bias = "BULLISH"
    response.trend_strength = 65.0
    response.confidence_score = 75.0
    response.model_source = "heuristic_ensemble"
    response.calibrated = False
    mp.predict_probabilities = AsyncMock(return_value=response)
    return mp


def test_aliases_and_singletons():
    """TacticalHorizonEngine and legacy aliases must reference the same engine hierarchy."""
    assert issubclass(TacticalHorizonEngine, TrendForecaster)
    assert TrendForecast1H is TacticalHorizonEngine
    assert isinstance(tactical_horizon_engine, TacticalHorizonEngine)
    assert isinstance(trend_forecaster, TacticalHorizonEngine)
    assert isinstance(trend_forecast_1h, TacticalHorizonEngine)


def test_regime_layer_weights():
    """Regime-adaptive layer weights should shift based on regime."""
    # Baseline non-adaptive returns default LAYER_WEIGHTS
    default_w = get_regime_layer_weights("TRENDING", adaptive=False)
    assert default_w == LAYER_WEIGHTS

    # Adaptive returns regime specific weights
    trending_w = get_regime_layer_weights("TRENDING_UP", adaptive=True)
    assert trending_w["mtf_alignment"] == 0.35
    assert trending_w["ml"] == 0.30
    assert trending_w["indicators"] == 0.20
    assert sum(trending_w.values()) == pytest.approx(1.0)

    ranging_w = get_regime_layer_weights("RANGING", adaptive=True)
    assert ranging_w["indicators"] == 0.35
    assert ranging_w["options"] == 0.25
    assert ranging_w["mtf_alignment"] == 0.15
    assert sum(ranging_w.values()) == pytest.approx(1.0)

    volatile_w = get_regime_layer_weights("VOLATILE", adaptive=True)
    assert volatile_w["options"] == 0.25
    assert volatile_w["structure"] == 0.10
    assert sum(volatile_w.values()) == pytest.approx(1.0)


def test_continuous_options_wall_decay():
    """Options wall decay must be continuous rather than a sharp cliff."""
    engine = TacticalHorizonEngine()
    current_price = 25000.0

    # At 0.2% distance (< 0.4%), penalty is -20.0
    ctx_near = {"call_wall": 25050.0, "pcr_oi": 1.0}  # 50/25000 = +0.2%
    res_near = engine.ensemble_forecast(
        mtf_features={"per_timeframe": {}},
        indicator_outputs=[],
        ml_forecast=None,
        options_ctx=ctx_near,
        current_price=current_price,
    )

    # At 0.6% distance (> 0.4%), decay is continuous: -20 * exp(-((0.6-0.4)/0.5)^2)
    ctx_mid = {"call_wall": 25150.0, "pcr_oi": 1.0}  # 150/25000 = +0.6%
    res_mid = engine.ensemble_forecast(
        mtf_features={"per_timeframe": {}},
        indicator_outputs=[],
        ml_forecast=None,
        options_ctx=ctx_mid,
        current_price=current_price,
    )

    # Far away (3% distance), penalty decays to ~0
    ctx_far = {"call_wall": 25750.0, "pcr_oi": 1.0}  # 750/25000 = +3.0%
    res_far = engine.ensemble_forecast(
        mtf_features={"per_timeframe": {}},
        indicator_outputs=[],
        ml_forecast=None,
        options_ctx=ctx_far,
        current_price=current_price,
    )

    assert res_near["layer_scores"]["options"] == -20.0
    assert -20.0 < res_mid["layer_scores"]["options"] < 0.0
    assert res_far["layer_scores"]["options"] == 0.0


@pytest.mark.asyncio
async def test_tactical_bias_method(mock_market_service, mock_ml_predictor):
    """get_tactical_bias should return a fully formed Tactical Horizon Bias payload."""
    engine = TacticalHorizonEngine(
        market_service=mock_market_service,
        ml_predictor=mock_ml_predictor,
    )
    result = await engine.get_tactical_bias(instrument="NIFTY 50", horizon="1h", record=False)

    assert result["engine"] == "tactical_horizon_bias"
    assert result["tactical_bias"] in {"BULLISH", "BEARISH", "NEUTRAL"}
    assert "layer_weights" in result
    assert result["instrument"] == "NIFTY 50"
    assert result["direction"] == result["tactical_bias"]
