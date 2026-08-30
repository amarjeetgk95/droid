from typing import NamedTuple, Literal

PatternType = Literal[
    "BULLISH_PINBAR",
    "BEARISH_PINBAR",
    "BULLISH_ENGULFING",
    "BEARISH_ENGULFING",
    "INSIDE_BAR",
    "VOLATILITY_SQUEEZE_BREAKOUT",
    "VOLUME_CLIMAX",
]


class DetectedCandlePattern(NamedTuple):
    pattern_type: PatternType
    name: str
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float
    timeframe: str
    bar_index: int
    trigger_price: float
    invalidation_level: float
    target_level: float
    description: str


def detect_patterns_in_candles(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    timeframe: str = "5m",
) -> list[DetectedCandlePattern]:
    """Scan OHLCV series and identify institutional candlestick & volatility patterns."""
    if len(closes) < 2:
        return []

    patterns: list[DetectedCandlePattern] = []
    n = len(closes)

    for i in range(1, n):
        o = opens[i]
        h = highs[i]
        l = lows[i]
        c = closes[i]
        v = volumes[i]

        prev_o = opens[i - 1]
        prev_h = highs[i - 1]
        prev_l = lows[i - 1]
        prev_c = closes[i - 1]

        total_range = h - l
        if total_range <= 1e-4:
            continue

        body = abs(c - o)
        upper_wick = h - max(c, o)
        lower_wick = min(c, o) - l

        # 1. Bullish Pinbar (Hammer)
        if lower_wick >= 2.0 * body and upper_wick <= 0.3 * total_range and c >= l + 0.65 * total_range:
            patterns.append(DetectedCandlePattern(
                pattern_type="BULLISH_PINBAR",
                name="Bullish Pinbar (Rejection Hammer)",
                bias="BULLISH",
                confidence=85.0,
                timeframe=timeframe,
                bar_index=i,
                trigger_price=round(h, 2),
                invalidation_level=round(l - 5.0, 2),
                target_level=round(h + total_range * 1.5, 2),
                description="Strong buying absorption and supply rejection at lower prices. Favors long expansion.",
            ))

        # 2. Bearish Pinbar (Shooting Star)
        if upper_wick >= 2.0 * body and lower_wick <= 0.3 * total_range and c <= l + 0.35 * total_range:
            patterns.append(DetectedCandlePattern(
                pattern_type="BEARISH_PINBAR",
                name="Bearish Pinbar (Supply Rejection)",
                bias="BEARISH",
                confidence=85.0,
                timeframe=timeframe,
                bar_index=i,
                trigger_price=round(l, 2),
                invalidation_level=round(h + 5.0, 2),
                target_level=round(l - total_range * 1.5, 2),
                description="Heavy institutional profit taking and upside rejection. Favors short continuation.",
            ))

        # 3. Bullish Engulfing
        if prev_c < prev_o and c > o and c >= prev_o and o <= prev_c and body > abs(prev_c - prev_o):
            patterns.append(DetectedCandlePattern(
                pattern_type="BULLISH_ENGULFING",
                name="Bullish Engulfing",
                bias="BULLISH",
                confidence=82.0,
                timeframe=timeframe,
                bar_index=i,
                trigger_price=round(h, 2),
                invalidation_level=round(l, 2),
                target_level=round(h + (h - l) * 1.6, 2),
                description="Buyers completely overpower previous bearish bar with strong momentum.",
            ))

        # 4. Bearish Engulfing
        if prev_c > prev_o and c < o and c <= prev_o and o >= prev_c and body > abs(prev_c - prev_o):
            patterns.append(DetectedCandlePattern(
                pattern_type="BEARISH_ENGULFING",
                name="Bearish Engulfing",
                bias="BEARISH",
                confidence=82.0,
                timeframe=timeframe,
                bar_index=i,
                trigger_price=round(l, 2),
                invalidation_level=round(h, 2),
                target_level=round(l - (h - l) * 1.6, 2),
                description="Sellers completely engulf previous bullish candle indicating trend reversal.",
            ))

        # 5. Inside Bar (Harami Consolidation)
        if h <= prev_h and l >= prev_l:
            patterns.append(DetectedCandlePattern(
                pattern_type="INSIDE_BAR",
                name="Inside Bar (Volatility Consolidation)",
                bias="NEUTRAL",
                confidence=78.0,
                timeframe=timeframe,
                bar_index=i,
                trigger_price=round(prev_h, 2),
                invalidation_level=round(prev_l, 2),
                target_level=round(prev_h + (prev_h - prev_l) * 1.0, 2),
                description="Range contraction within mother bar range. Watch for decisive breakout of high/low.",
            ))

        # 6. Volume Climax
        if i >= 10:
            avg_vol = sum(volumes[i - 10:i]) / 10.0
            if avg_vol > 0 and v >= 2.5 * avg_vol:
                patterns.append(DetectedCandlePattern(
                    pattern_type="VOLUME_CLIMAX",
                    name="Volume Climax / Institutional Absorption",
                    bias="BULLISH" if c > o else "BEARISH",
                    confidence=80.0,
                    timeframe=timeframe,
                    bar_index=i,
                    trigger_price=round(c, 2),
                    invalidation_level=round(l if c > o else h, 2),
                    target_level=round(c + (total_range * 1.5) if c > o else c - (total_range * 1.5), 2),
                    description=f"Massive volume spike ({round(v / avg_vol, 1)}x average) indicating institutional turnover.",
                ))

    return patterns
