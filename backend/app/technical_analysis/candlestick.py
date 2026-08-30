def detect_candlesticks(candles: list[dict], volume_info: dict=None) -> list[dict]:
    patterns=[]
    if len(candles)<2:
        return patterns
    curr=candles[-1]
    prev=candles[-2] if len(candles)>=2 else curr
    o=curr["open"]; h=curr["high"]; l=curr["low"]; c=curr["close"]
    body=abs(c-o)
    rng=h-l if h!=l else 1
    upper=max(o,c)
    lower=min(o,c)
    upper_wick=h-upper
    lower_wick=lower-l
    vol_status = volume_info.get("relative_volume",1) if volume_info and volume_info.get("available") else 1
    vol_label = "ABOVE_AVERAGE" if vol_status>1.2 else "BELOW_AVERAGE" if vol_status<0.8 else "AVERAGE"

    # Doji
    if body/rng <0.1:
        patterns.append({"pattern":"DOJI","location":"NEUTRAL","volume":vol_label,"context_strength":"MEDIUM","bias":"NEUTRAL"})
    # Hammer
    if lower_wick > body*2 and upper_wick < body*0.5 and body/rng>0.15:
        patterns.append({"pattern":"HAMMER","location":"SUPPORT","volume":vol_label,"context_strength":"HIGH" if vol_status>1.2 else "MEDIUM","bias":"BULLISH"})
    # Inverted Hammer
    if upper_wick> body*2 and lower_wick < body*0.5:
        patterns.append({"pattern":"INVERTED_HAMMER","location":"RESISTANCE","volume":vol_label,"context_strength":"MEDIUM","bias":"BEARISH"})
    # Shooting Star (similar to inverted hammer but at top)
    if upper_wick> body*2 and lower_wick < body*0.3 and c<o:
        patterns.append({"pattern":"SHOOTING_STAR","location":"RESISTANCE","volume":vol_label,"context_strength":"HIGH","bias":"BEARISH"})
    # Bullish Engulfing
    if prev["close"]<prev["open"] and c>o and c>prev["open"] and o<prev["close"]:
        patterns.append({"pattern":"BULLISH_ENGULFING","location":"SUPPORT","volume":vol_label,"context_strength":"HIGH","bias":"BULLISH"})
    # Bearish Engulfing
    if prev["close"]>prev["open"] and c<o and c<prev["open"] and o>prev["close"]:
        patterns.append({"pattern":"BEARISH_ENGULFING","location":"RESISTANCE","volume":vol_label,"context_strength":"HIGH","bias":"BEARISH"})
    # Inside Bar
    if h<prev["high"] and l>prev["low"]:
        patterns.append({"pattern":"INSIDE_BAR","location":"CONSOLIDATION","volume":vol_label,"context_strength":"MEDIUM","bias":"NEUTRAL"})
    # Outside Bar
    if h>prev["high"] and l<prev["low"] and body>abs(prev["close"]-prev["open"]):
        patterns.append({"pattern":"OUTSIDE_BAR","location":"BREAKOUT","volume":vol_label,"context_strength":"HIGH","bias":"NEUTRAL"})
    # Harami
    if abs(prev["close"]-prev["open"]) > body*1.5 and max(o,c) < max(prev["open"],prev["close"]) and min(o,c) > min(prev["open"],prev["close"]):
        patterns.append({"pattern":"HARAMI","location":"REVERSAL_ZONE","volume":vol_label,"context_strength":"MEDIUM","bias":"NEUTRAL"})
    return patterns

def candlestick_summary(patterns: list[dict]) -> dict:
    if not patterns:
        return {"pattern":"NONE","bias":"NEUTRAL","count":0}
    bullish=sum(1 for p in patterns if p["bias"]=="BULLISH")
    bearish=sum(1 for p in patterns if p["bias"]=="BEARISH")
    if bullish>bearish: bias="BULLISH"
    elif bearish>bullish: bias="BEARISH"
    else: bias="NEUTRAL"
    return {"pattern":patterns[0]["pattern"],"bias":bias,"count":len(patterns),"all":patterns}
