import math

def calculate_support_resistance(candles: list[dict], current_price: float, fno_levels: dict|None=None) -> dict:
    if not candles:
        return {"support": None, "resistance": None, "levels": []}
    highs=[c["high"] for c in candles]
    lows=[c["low"] for c in candles]
    closes=[c["close"] for c in candles]
    # swing highs/lows (last 20)
    swing_high = max(highs[-20:]) if len(highs)>=20 else max(highs)
    swing_low = min(lows[-20:]) if len(lows)>=20 else min(lows)
    # pivot classic (use prior day approximation: last 20 as day)
    if len(candles)>=20:
        h = max(highs[-20:]); l = min(lows[-20:]); c = closes[-20]
        pp=(h+l+c)/3
        r1=2*pp - l
        s1=2*pp - h
    else:
        pp=current_price; r1=current_price*1.01; s1=current_price*0.99
    # VWAP
    volumes=[c.get("volume",0) for c in candles]
    vwap=None
    if sum(volumes[-20:])>0:
        tp=[(c["high"]+c["low"]+c["close"])/3 for c in candles[-20:]]
        vwap=sum(t*v for t,v in zip(tp, volumes[-20:]))/sum(volumes[-20:])
    # Moving averages as S/R
    sma20=sum(closes[-20:])/20 if len(closes)>=20 else current_price
    # Bollinger
    if len(closes)>=20:
        mid=sum(closes[-20:])/20
        std=math.sqrt(sum((x-mid)**2 for x in closes[-20:])/20)
        bb_upper=mid+2*std
        bb_lower=mid-2*std
    else:
        bb_upper=bb_lower=None
    # Build candidate levels
    candidates=[]
    candidates.append({"level": round(swing_high,2), "type":"RESISTANCE", "source":"Swing High", "strength": 0.6})
    candidates.append({"level": round(swing_low,2), "type":"SUPPORT", "source":"Swing Low", "strength": 0.6})
    candidates.append({"level": round(r1,2), "type":"RESISTANCE", "source":"Pivot R1", "strength": 0.5})
    candidates.append({"level": round(s1,2), "type":"SUPPORT", "source":"Pivot S1", "strength": 0.5})
    candidates.append({"level": round(pp,2), "type":"PIVOT", "source":"Pivot PP", "strength": 0.5})
    if vwap: candidates.append({"level": round(vwap,2), "type":"PIVOT", "source":"VWAP", "strength": 0.7})
    candidates.append({"level": round(sma20,2), "type":"PIVOT", "source":"SMA20", "strength": 0.5})
    if bb_upper: candidates.append({"level": round(bb_upper,2), "type":"RESISTANCE", "source":"Bollinger Upper", "strength": 0.4})
    if bb_lower: candidates.append({"level": round(bb_lower,2), "type":"SUPPORT", "source":"Bollinger Lower", "strength": 0.4})
    # F&O levels if available
    if fno_levels:
        if fno_levels.get("call_wall"):
            candidates.append({"level": round(fno_levels["call_wall"],2), "type":"RESISTANCE", "source":"Call Wall (OI)", "strength": 0.8})
        if fno_levels.get("put_wall"):
            candidates.append({"level": round(fno_levels["put_wall"],2), "type":"SUPPORT", "source":"Put Wall (OI)", "strength": 0.8})
        if fno_levels.get("max_pain"):
            candidates.append({"level": round(fno_levels["max_pain"],2), "type":"PIVOT", "source":"Max Pain", "strength": 0.6})

    # Find nearest support/resistance
    supports = [c for c in candidates if c["level"] < current_price]
    resistances = [c for c in candidates if c["level"] > current_price]
    nearest_support = min(supports, key=lambda x: abs(x["level"]-current_price)) if supports else None
    nearest_resistance = min(resistances, key=lambda x: abs(x["level"]-current_price)) if resistances else None

    # Confluence scoring: count levels within 0.5% of nearest support/resistance
    def confluence(target):
        if not target: return {"count":0,"strength":"LOW","sources":[]}
        thresh = current_price*0.005
        close_levels=[c for c in candidates if abs(c["level"]-target["level"]) <= thresh]
        cnt=len(close_levels)
        strength="HIGH" if cnt>=3 else "MEDIUM" if cnt>=2 else "LOW"
        return {"count":cnt, "strength":strength, "sources":[c["source"] for c in close_levels]}

    return {
        "support": nearest_support["level"] if nearest_support else round(swing_low,2),
        "resistance": nearest_resistance["level"] if nearest_resistance else round(swing_high,2),
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "support_confluence": confluence(nearest_support),
        "resistance_confluence": confluence(nearest_resistance),
        "levels": candidates,
        "distance_to_support_pts": round(current_price - (nearest_support["level"] if nearest_support else swing_low),2),
        "distance_to_resistance_pts": round((nearest_resistance["level"] if nearest_resistance else swing_high) - current_price,2),
    }
