"""
Test fixtures and candle generation helpers for VORTEX-SNAP test suite.
"""
from typing import List
import pytest

from app.signals.strategies.vortex_snap.types import Candle


def create_candle(
    timestamp: int,
    open_p: float,
    high_p: float,
    low_p: float,
    close_p: float,
    volume: float = 1000.0,
) -> Candle:
    return Candle(
        timestamp=timestamp,
        open=round(open_p, 2),
        high=round(high_p, 2),
        low=round(low_p, 2),
        close=round(close_p, 2),
        volume=round(volume, 1),
    )


def generate_flat_candles(n: int = 30, base_price: float = 24000.0, bar_range: float = 4.0) -> List[Candle]:
    """Generates tightly compressed consolidation candles."""
    candles: List[Candle] = []
    t0 = 1758426000000
    for i in range(n):
        t = t0 + i * 60000
        # Alternating small up and down bars
        sign = 1 if i % 2 == 0 else -1
        o = base_price + (sign * 1.0)
        c = base_price - (sign * 1.0)
        h = max(o, c) + (bar_range / 2.0)
        l = min(o, c) - (bar_range / 2.0)
        candles.append(create_candle(t, o, h, l, c, volume=500.0))
    return candles


def generate_trending_candles(n: int = 30, base_price: float = 24000.0, step: float = 10.0) -> List[Candle]:
    """Generates strong trending candles with high directional efficiency."""
    candles: List[Candle] = []
    t0 = 1758426000000
    price = base_price
    for i in range(n):
        t = t0 + i * 60000
        o = price
        c = price + step
        h = c + 2.0
        l = o - 1.0
        candles.append(create_candle(t, o, h, l, c, volume=1500.0 + i * 50))
        price = c
    return candles


@pytest.fixture
def sample_compressed_candles() -> List[Candle]:
    return generate_flat_candles(35, base_price=24000.0, bar_range=5.0)


@pytest.fixture
def sample_trending_candles() -> List[Candle]:
    return generate_trending_candles(35, base_price=24000.0, step=12.0)
