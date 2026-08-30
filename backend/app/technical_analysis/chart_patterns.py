import math

def detect_chart_patterns(candles: list[dict]) -> list[dict]:
    patterns=[]
    if len(candles)<20:
        return patterns
    closes=[c["close"] for c in candles]
    highs=[c["high"] for c in candles]
    lows=[c["low"] for c in candles]
    # Simple peak/trough detection
    # Double Top: two highs within 2% and trough between
    # Look at last 30 candles
    n=30
    subset_highs=highs[-n:] if len(highs)>=n else highs
    subset_lows=lows[-n:] if len(lows)>=n else lows
    subset_closes=closes[-n:] if len(closes)>=n else closes
    # Find local maxima
    peaks=[]
    for i in range(1,len(subset_highs)-1):
        if subset_highs[i]>subset_highs[i-1] and subset_highs[i]>subset_highs[i+1]:
            peaks.append((i, subset_highs[i]))
    troughs=[]
    for i in range(1,len(subset_lows)-1):
        if subset_lows[i]<subset_lows[i-1] and subset_lows[i]<subset_lows[i+1]:
            troughs.append((i, subset_lows[i]))

    # Double Top
    if len(peaks)>=2:
        p1=peaks[-2]; p2=peaks[-1]
        if abs(p1[1]-p2[1])/p1[1] <0.02 and p2[0]-p1[0]>5:
            # trough between
            between_lows = subset_lows[p1[0]:p2[0]]
            if between_lows and min(between_lows) < min(p1[1],p2[1])*0.985:
                patterns.append({
                    "pattern":"DOUBLE_TOP",
                    "bias":"BEARISH",
                    "confidence":0.65,
                    "breakout_level": round(min(between_lows),2),
                    "invalidation_level": round(max(p1[1],p2[1])*1.01,2),
                    "start_time": None, "end_time": None
                })
    # Double Bottom
    if len(troughs)>=2:
        t1=troughs[-2]; t2=troughs[-1]
        if abs(t1[1]-t2[1])/t1[1] <0.02 and t2[0]-t1[0]>5:
            between_highs=subset_highs[t1[0]:t2[0]]
            if between_highs and max(between_highs) > max(t1[1],t2[1])*1.015:
                patterns.append({
                    "pattern":"DOUBLE_BOTTOM",
                    "bias":"BULLISH",
                    "confidence":0.65,
                    "breakout_level": round(max(between_highs),2),
                    "invalidation_level": round(min(t1[1],t2[1])*0.99,2),
                    "start_time":None,"end_time":None
                })
    # Triangle: converging highs and lows
    if len(peaks)>=2 and len(troughs)>=2:
        high_slope = (peaks[-1][1]-peaks[-2][1])/(peaks[-1][0]-peaks[-2][0]) if peaks[-1][0]!=peaks[-2][0] else 0
        low_slope = (troughs[-1][1]-troughs[-2][1])/(troughs[-1][0]-troughs[-2][0]) if troughs[-1][0]!=troughs[-2][0] else 0
        if high_slope<0 and low_slope>0:
            patterns.append({"pattern":"TRIANGLE","bias":"NEUTRAL","confidence":0.55,"breakout_level": round(subset_closes[-1]*1.01,2),"invalidation_level": round(subset_closes[-1]*0.99,2), "start_time":None,"end_time":None})
        elif high_slope<0 and abs(low_slope)<0.0005:
            patterns.append({"pattern":"DESCENDING_TRIANGLE","bias":"BEARISH","confidence":0.58,"breakout_level": round(min(subset_lows[-5:]),2),"invalidation_level": round(max(subset_highs[-5:]),2),"start_time":None,"end_time":None})
        elif low_slope>0 and abs(high_slope)<0.0005:
            patterns.append({"pattern":"ASCENDING_TRIANGLE","bias":"BULLISH","confidence":0.58,"breakout_level": round(max(subset_highs[-5:]),2),"invalidation_level": round(min(subset_lows[-5:]),2),"start_time":None,"end_time":None})
    # Channel: parallel highs/lows
    if len(closes)>=20:
        # Flag: sharp move then consolidation
        recent_range = max(highs[-5:])-min(lows[-5:])
        prior_move = abs(closes[-10]-closes[-20]) if len(closes)>=20 else 0
        if prior_move > recent_range*2 and recent_range < closes[-1]*0.02:
            patterns.append({"pattern":"FLAG","bias":"NEUTRAL","confidence":0.5,"breakout_level": round(max(highs[-5:]),2),"invalidation_level": round(min(lows[-5:]),2), "start_time":None,"end_time":None})

    return patterns
