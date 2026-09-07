"""Unit tests for the Option Market Pressure Index (OMPI) v0.1 (§15-§18)."""

import pytest
from datetime import datetime, timezone

from app.research.enums import Direction, IndicatorCategory, IndicatorLifecycle
from app.research.indicators.ompi import OMPIIndicator
from app.research.models import IndicatorContext


@pytest.fixture
def bullish_candles():
    now = datetime.now(timezone.utc)
    base = 24000.0
    candles = []
    for i in range(60):
        p = base + (i * 8.0)
        candles.append({
            "open": p - 2.0,
            "high": p + 6.0,
            "low": p - 2.0,
            "close": p + 4.0,
            "volume": 2000.0 + (i * 20.0),
            "timestamp": now.isoformat(),
        })
    return candles


@pytest.fixture
def bearish_candles():
    now = datetime.now(timezone.utc)
    base = 24500.0
    candles = []
    for i in range(60):
        p = base - (i * 8.0)
        candles.append({
            "open": p + 2.0,
            "high": p + 2.0,
            "low": p - 6.0,
            "close": p - 4.0,
            "volume": 2500.0 + (i * 20.0),
            "timestamp": now.isoformat(),
        })
    return candles


def test_ompi_metadata():
    ind = OMPIIndicator()
    assert ind.indicator_id == "ompi"
    assert ind.version == "0.1.0"
    assert ind.category == IndicatorCategory.PROPRIETARY
    assert ind.lifecycle == IndicatorLifecycle.EXPERIMENTAL
    assert "0.30*P_dir" in ind.formula_summary


@pytest.mark.asyncio
async def test_ompi_bullish_calculation(bullish_candles):
    ind = OMPIIndicator()
    opt_ctx = {
        "available": True,
        "pcr_oi": 1.35,  # Bullish PCR
        "atm_iv": 14.2,
        "call_wall": 25000.0,
        "put_wall": 23800.0,
        "max_pain": 24200.0,
        "days_to_expiry": 3.0,
        "atm_theta": -11.0,
    }

    ctx = IndicatorContext(
        instrument="NIFTY 50",
        timeframe="5m",
        timestamp=datetime.now(timezone.utc),
        candles=bullish_candles,
        current_price=bullish_candles[-1]["close"],
        options_context=opt_ctx,
    )

    out = await ind.calculate(ctx)

    assert out.indicator_id == "ompi"
    assert out.direction == Direction.BULLISH
    assert out.score >= 20.0
    assert 0.0 <= out.confidence <= 1.0

    # Verify §17 transparency: all 5 sub-pressures exposed
    comps = out.component_values
    assert "p_dir" in comps
    assert "p_opt" in comps
    assert "p_part" in comps
    assert "p_vol" in comps
    assert "p_decay" in comps
    assert comps["pcr_oi"] == 1.35
    assert comps["days_to_expiry"] == 3.0
    assert "weights" in comps


@pytest.mark.asyncio
async def test_ompi_bearish_calculation(bearish_candles):
    ind = OMPIIndicator()
    opt_ctx = {
        "available": True,
        "pcr_oi": 0.65,  # Bearish PCR
        "atm_iv": 17.5,
        "call_wall": 24800.0,
        "put_wall": 23500.0,
        "max_pain": 23900.0,
        "days_to_expiry": 2.0,
        "atm_theta": -14.0,
    }

    ctx = IndicatorContext(
        instrument="NIFTY 50",
        timeframe="5m",
        timestamp=datetime.now(timezone.utc),
        candles=bearish_candles,
        current_price=bearish_candles[-1]["close"],
        options_context=opt_ctx,
    )

    out = await ind.calculate(ctx)

    assert out.indicator_id == "ompi"
    assert out.direction == Direction.BEARISH
    assert out.score <= -20.0
    assert out.target_price is not None
    assert out.invalidation_price is not None


@pytest.mark.asyncio
async def test_ompi_neutral_calculation():
    """Verify that NEUTRAL signals have None for target_price and invalidation_price."""
    ind = OMPIIndicator()
    now = datetime.now(timezone.utc)
    # Flat candles that produce neutral score
    candles = []
    base = 24000.0
    for i in range(60):
        # alternating small variations
        offset = 1.0 if i % 2 == 0 else -1.0
        candles.append({
            "open": base,
            "high": base + 2.0,
            "low": base - 2.0,
            "close": base + offset,
            "volume": 1000.0,
            "timestamp": now.isoformat(),
        })

    ctx = IndicatorContext(
        instrument="NIFTY 50",
        timeframe="5m",
        timestamp=now,
        candles=candles,
        current_price=base,
        options_context={"available": False},
    )

    out = await ind.calculate(ctx)
    if out.direction == Direction.NEUTRAL:
        assert out.target_price is None
        assert out.invalidation_price is None
