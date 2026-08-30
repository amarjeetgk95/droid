import math

def atr(highs,lows,closes,period=14):
    if len(closes)<2: return 50
    trs=[]
    for i in range(1,len(closes)):
        trs.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    if len(trs)<period:
        return sum(trs)/len(trs) if trs else 0
    a=sum(trs[:period])/period
    for i in range(period,len(trs)):
        a=(a*(period-1)+trs[i])/period
    return a

def bollinger(prices,period=20,num_std=2):
    if len(prices)<period: return None
    subset=prices[-period:]
    mid=sum(subset)/period
    var=sum((x-mid)**2 for x in subset)/period
    std=math.sqrt(var)
    upper=mid+num_std*std
    lower=mid-num_std*std
    bw=(upper-lower)/mid*100 if mid>0 else 0
    return upper,mid,lower,bw

def analyze_volatility(candles: list[dict], vix: float|None=None, fno_iv: float|None=None) -> dict:
    closes=[c["close"] for c in candles]
    highs=[c["high"] for c in candles]
    lows=[c["low"] for c in candles]
    if not closes:
        return {"volatility":"NORMAL","atr":0}
    a=atr(highs,lows,closes,14)
    atr_pct = a/closes[-1]*100 if closes[-1]!=0 else 0
    # rolling volatility (std of returns)
    if len(closes)>=20:
        rets=[(closes[i]-closes[i-1])/closes[i-1]*100 for i in range(1,len(closes))]
        recent=rets[-20:]
        mean=sum(recent)/len(recent)
        std=math.sqrt(sum((x-mean)**2 for x in recent)/len(recent))
        rolling_vol=std
    else:
        rolling_vol= atr_pct
    bb=bollinger(closes,20,2)
    if bb:
        upper,mid,lower,bw=bb
        pct_b=(closes[-1]-lower)/(upper-lower) if upper!=lower else 0.5
    else:
        upper=mid=lower=bw=pct_b=None
    # Keltner placeholder (ATR based)
    if bb and a:
        kelt_upper = mid + 1.5*a if mid else None
        kelt_lower = mid -1.5*a if mid else None
    else:
        kelt_upper=kelt_lower=None
    # classify
    vol_status="NORMAL"
    if atr_pct<0.5:
        vol_status="LOW"
    elif atr_pct>2.0:
        vol_status="HIGH"
    # expanding vs contracting: compare recent atr vs earlier
    if len(closes)>=28:
        atr_recent=atr(highs[-15:],lows[-15:],closes[-15:],14)
        atr_earlier=atr(highs[-30:-15],lows[-30:-15],closes[-30:-15],14)
        if atr_recent> atr_earlier*1.2:
            vol_status="EXPANDING"
        elif atr_recent < atr_earlier*0.8:
            vol_status="CONTRACTING"

    # IV handling where available
    iv_skew=None
    if fno_iv is not None:
        iv_skew=0.0

    return {
        "atr": round(a,2),
        "atr_pct": round(atr_pct,3),
        "rolling_volatility": round(rolling_vol,3),
        "std_dev": round(rolling_vol,3),
        "bollinger_upper": round(upper,2) if upper else None,
        "bollinger_middle": round(mid,2) if mid else None,
        "bollinger_lower": round(lower,2) if lower else None,
        "bollinger_width": round(bw,2) if bw else None,
        "bollinger_pct_b": round(pct_b,3) if pct_b is not None else None,
        "keltner_upper": round(kelt_upper,2) if kelt_upper else None,
        "keltner_lower": round(kelt_lower,2) if kelt_lower else None,
        "volatility": vol_status,
        "classification": vol_status,
        "atm_iv": fno_iv,
        "vix": vix,
        "score": 60 if vol_status in ("NORMAL","EXPANDING") else 40,
    }
