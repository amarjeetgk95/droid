from app.quant.patterns import detect_patterns_in_candles


class TestPatterns:
    def test_pinbar_detection(self):
        # Create a Bullish Pinbar (long lower wick, small body at high)
        opens = [100.0, 108.0]
        highs = [102.0, 110.0]
        lows = [98.0, 90.0]    # Lower wick = 18 pts, total range = 20 pts
        closes = [99.0, 109.0]
        volumes = [1000.0, 5000.0]

        patterns = detect_patterns_in_candles(opens, highs, lows, closes, volumes)
        types = [p.pattern_type for p in patterns]
        assert "BULLISH_PINBAR" in types

    def test_engulfing_detection(self):
        # Bearish candle followed by massive Bullish Engulfing
        opens = [105.0, 98.0]
        highs = [106.0, 110.0]
        lows = [99.0, 97.0]
        closes = [100.0, 108.0]
        volumes = [1000.0, 4000.0]

        patterns = detect_patterns_in_candles(opens, highs, lows, closes, volumes)
        types = [p.pattern_type for p in patterns]
        assert "BULLISH_ENGULFING" in types

    def test_inside_bar_detection(self):
        # Mother bar followed by Inside Bar
        opens = [100.0, 103.0]
        highs = [110.0, 106.0]
        lows = [95.0, 98.0]
        closes = [105.0, 102.0]
        volumes = [1000.0, 2000.0]

        patterns = detect_patterns_in_candles(opens, highs, lows, closes, volumes)
        types = [p.pattern_type for p in patterns]
        assert "INSIDE_BAR" in types
