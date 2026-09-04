
def analyze_price_action(candles: list[dict]) -> dict:
    """Calculates price-action metrics from OHLCV candles.
    candles: list of dict with open/high/low/close/volume
    """
    if not candles:
        return {"structure":"UNKNOWN","trend":"NEUTRAL","consolidation":False,"breakout":None,"returns":0}

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    opens = [c["open"] for c in candles]
    volumes = [c.get("volume",0) for c in candles]

    # Returns
    ret = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0]!=0 else 0
    # Range
    curr = candles[-1]
    candle_range = curr["high"] - curr["low"]
    body = abs(curr["close"] - curr["open"])
    upper_wick = curr["high"] - max(curr["open"], curr["close"])
    lower_wick = min(curr["open"], curr["close"]) - curr["low"]
    prev = candles[-2] if len(candles)>=2 else curr
    true_range = max(curr["high"] - curr["low"], abs(curr["high"]-prev["close"]), abs(curr["low"]-prev["close"]))

    # Structure detection using last 5 candles
    n = min(5, len(candles))
    recent_closes = closes[-n:]
    recent_highs = highs[-n:]
    recent_lows = lows[-n:]
    # Simple HH/HL logic
    hh = all(recent_highs[i] <= recent_highs[i+1] for i in range(len(recent_highs)-1))
    hl = all(recent_lows[i] <= recent_lows[i+1] for i in range(len(recent_lows)-1))
    ll = all(recent_highs[i] >= recent_highs[i+1] for i in range(len(recent_highs)-1))
    lh = all(recent_lows[i] >= recent_lows[i+1] for i in range(len(recent_lows)-1))

    if hh and hl:
        structure = "HIGHER_HIGH_HIGHER_LOW"
        trend = "BULLISH"
    elif ll and lh:
        structure = "LOWER_LOW_LOWER_HIGH"
        trend = "BEARISH"
    elif hh:
        structure = "HIGHER_HIGH"
        trend = "BULLISH"
    elif ll:
        structure = "LOWER_LOW"
        trend = "BEARISH"
    else:
        structure = "CONSOLIDATION"
        trend = "NEUTRAL"

    # Swing high/low (last 10)
    swing_high = max(highs[-10:]) if len(highs)>=10 else max(highs)
    swing_low = min(lows[-10:]) if len(lows)>=10 else min(lows)
    is_breakout = closes[-1] > swing_high * 0.999 and structure!="CONSOLIDATION"
    is_breakdown = closes[-1] < swing_low *1.001 and structure!="CONSOLIDATION"
    breakout = "BREAKOUT" if is_breakout else "BREAKDOWN" if is_breakdown else None
    # Consolidation: narrow range
    avg_range = sum(h-l for h,l in zip(highs[-10:], lows[-10:]))/10 if len(candles)>=10 else candle_range
    consolidation = candle_range < avg_range * 0.6
    # Range expansion/contraction
    range_expansion = candle_range > avg_range * 1.2
    range_contraction = candle_range < avg_range * 0.8

    return {
        "open": curr["open"], "high": curr["high"], "low": curr["low"], "close": curr["close"],
        "returns_pct": round(ret,3),
        "range": round(candle_range,2), "true_range": round(true_range,2),
        "body_size": round(body,2), "upper_wick": round(upper_wick,2), "lower_wick": round(lower_wick,2),
        "structure": structure, "trend": trend,
        "swing_high": round(swing_high,2), "swing_low": round(swing_low,2),
        "breakout": breakout, "consolidation": consolidation,
        "range_expansion": range_expansion, "range_contraction": range_contraction,
        "gap": round(candles[-1]["open"] - candles[-2]["close"],2) if len(candles)>=2 else 0,
    }
