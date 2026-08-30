import math
from app.quant.indicators import (
    calculate_sma, calculate_ema, calculate_rsi, calculate_atr,
    calculate_adx, calculate_bollinger_bands, calculate_supertrend
)


class TestIndicators:
    def test_sma_and_ema(self):
        prices = [100.0, 102.0, 104.0, 106.0, 108.0]
        sma = calculate_sma(prices, 5)
        assert sma == 104.0

        ema = calculate_ema(prices, 3)
        assert ema is not None
        assert ema > 100.0

    def test_rsi_calculation(self):
        # Monotonically increasing prices -> high RSI
        uptrend = [100.0 + i * 2.0 for i in range(25)]
        rsi_up = calculate_rsi(uptrend, 14)
        assert rsi_up > 80.0

        # Monotonically decreasing prices -> low RSI
        downtrend = [200.0 - i * 2.0 for i in range(25)]
        rsi_down = calculate_rsi(downtrend, 14)
        assert rsi_down < 20.0

    def test_bollinger_bands(self):
        prices = [25000.0 + (i % 5) * 20.0 for i in range(30)]
        upper, middle, lower, bandwidth, pct_b = calculate_bollinger_bands(prices, 20)

        assert upper > middle > lower
        assert bandwidth > 0
        assert 0.0 <= pct_b <= 1.0

    def test_supertrend(self):
        highs = [25050.0 + i * 10.0 for i in range(25)]
        lows = [24950.0 + i * 10.0 for i in range(25)]
        closes = [25000.0 + i * 10.0 for i in range(25)]

        st_val, direction = calculate_supertrend(highs, lows, closes, period=10)
        assert direction == "BULLISH"
        assert st_val < closes[-1]
