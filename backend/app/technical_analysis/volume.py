def analyze_volume(candles: list[dict]) -> dict:
    if not candles:
        return {"available": False, "reason": "Insufficient data"}
    volumes=[c.get("volume",0) for c in candles]
    closes=[c["close"] for c in candles]
    # check if volume is meaningful (not all zero)
    if all(v==0 or v is None for v in volumes):
        return {"available": False, "reason": "Volume not available for this instrument/data source", "score": None}
    # average volume
    avg_vol = sum(volumes[-20:])/min(20,len(volumes)) if volumes else 0
    curr_vol=volumes[-1]
    rel_vol = curr_vol/avg_vol if avg_vol>0 else 1
    vol_ma = avg_vol
    spike = rel_vol>1.5
    # VWAP
    vwap=None
    if sum(volumes[-20:])>0:
        typical=[(c["high"]+c["low"]+c["close"])/3 for c in candles[-20:]]
        vwap = sum(t*v for t,v in zip(typical, volumes[-20:]))/sum(volumes[-20:])
    # OBV
    obv=0
    for i in range(1,len(closes)):
        if closes[i]>closes[i-1]:
            obv+=volumes[i]
        elif closes[i]<closes[i-1]:
            obv-=volumes[i]
    # MFI approx
    if len(candles)>=14:
        pos_flow=0; neg_flow=0
        for i in range(1,14):
            tp = (candles[-i]["high"]+candles[-i]["low"]+candles[-i]["close"])/3
            tp_prev = (candles[-i-1]["high"]+candles[-i-1]["low"]+candles[-i-1]["close"])/3
            mf=tp*volumes[-i]
            if tp>tp_prev: pos_flow+=mf
            else: neg_flow+=mf
        mfr = pos_flow/neg_flow if neg_flow!=0 else 0
        mfi = 100 - 100/(1+mfr) if neg_flow!=0 else 100 if pos_flow>0 else 50
    else:
        mfi=50
    # price-volume relationship
    if len(closes)>=2:
        price_up = closes[-1]>closes[-2]
        vol_up = curr_vol>avg_vol
        if price_up and vol_up: relation="Price ↑ + Volume ↑ (confirmation)"
        elif price_up and not vol_up: relation="Price ↑ + Volume ↓ (weak)"
        elif not price_up and vol_up: relation="Price ↓ + Volume ↑ (distribution)"
        else: relation="Price ↓ + Volume ↓ (weak)"
    else:
        relation="UNKNOWN"

    score = 50
    if rel_vol>1.2 and closes[-1]>closes[-2]:
        score=78
    elif rel_vol>1.2:
        score=65
    elif rel_vol<0.8:
        score=40

    return {
        "available": True,
        "volume": curr_vol,
        "average_volume": round(avg_vol,2),
        "relative_volume": round(rel_vol,2),
        "volume_ma": round(vol_ma,2),
        "volume_spike": spike,
        "vwap": round(vwap,2) if vwap else None,
        "obv": obv,
        "mfi": round(mfi,2),
        "accumulation_distribution": "ACCUMULATION" if obv>0 else "DISTRIBUTION",
        "relationship": relation,
        "score": score,
    }
