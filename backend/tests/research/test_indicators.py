"""Unit tests for Standard Indicators in the Research Laboratory."""

import pytest
from datetime import datetime, timezone

from app.research.enums import Direction, IndicatorCategory
from app.research.indicators.macd_indicator import MACDIndicator
from app.research.indicators.momentum_indicator import MomentumIndicator
from app.research.indicators.rsi_indicator import RSIIndicator
from app.research.indicators.vwap_indicator import VWAPIndicator
from app.research.models import IndicatorContext
from app.research.registry import IndicatorRegistry


@pytest.fixture
def sample_candles():
    """Generates 50 sequential bullish candles."""
    now = datetime.now(timezone.utc)
    base = 24000.0
    candles = []
    for i in range(50):
        p = base + (i * 5.0)
        candles.append({
            "open": p - 2.0,
            "high": p + 4.0,
            "low": p - 3.0,
            "close": p + 2.0,
            "volume": 1500.0 + (i * 10.0),
            "timestamp": now.isoformat(),
        })
    return candles


@pytest.fixture
def context(sample_candles):
    return IndicatorContext(
        instrument="NIFTY 50",
        timeframe="5m",
        timestamp=datetime.now(timezone.utc),
        candles=sample_candles,
        current_price=sample_candles[-1]["close"],
    )


def test_registry_registration():
    """Verify indicators are registered in IndicatorRegistry."""
    all_inds = IndicatorRegistry.list_all()
    ids = [i.indicator_id for i in all_inds]
    assert "rsi" in ids
    assert "vwap" in ids
    assert "macd" in ids
    assert "momentum" in ids
    assert "ompi" in ids


@pytest.mark.asyncio
async def test_rsi_indicator(context):
    """Test RSI Indicator standard contract."""
    ind = RSIIndicator()
    out = await ind.calculate(context)

    assert out.indicator_id == "rsi"
    assert -100.0 <= out.score <= 100.0
    assert 0.0 <= out.confidence <= 1.0
    assert out.direction in (Direction.BULLISH, Direction.BEARISH, Direction.NEUTRAL)
    assert "rsi" in out.component_values
    assert out.target_price is not None
    assert out.invalidation_price is not None


@pytest.mark.asyncio
async def test_vwap_indicator(context):
    """Test VWAP Indicator standard contract."""
    ind = VWAPIndicator()
    out = await ind.calculate(context)

    assert out.indicator_id == "vwap"
    assert -100.0 <= out.score <= 100.0
    assert "vwap" in out.component_values
    assert "distance_pct" in out.component_values
    assert out.direction == Direction.BULLISH  # Rising prices above VWAP


@pytest.mark.asyncio
async def test_macd_indicator(context):
    """Test MACD Indicator standard contract."""
    ind = MACDIndicator()
    out = await ind.calculate(context)

    assert out.indicator_id == "macd"
    assert -100.0 <= out.score <= 100.0
    assert "macd_line" in out.component_values
    assert "signal_line" in out.component_values
    assert "histogram" in out.component_values


@pytest.mark.asyncio
async def test_momentum_indicator(context):
    """Test Momentum Indicator standard contract."""
    ind = MomentumIndicator()
    out = await ind.calculate(context)

    assert out.indicator_id == "momentum"
    assert -100.0 <= out.score <= 100.0
    assert "composite_roc" in out.component_values
    assert out.direction == Direction.BULLISH
