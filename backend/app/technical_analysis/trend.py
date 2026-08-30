import math

def sma(prices, period):
    if len(prices) < period: return None
    return sum(prices[-period:])/period

def ema(prices, period):
    if len(prices) < period: return None
    mult = 2/(period+1)
    e = sum(prices[:period])/period
    for p in prices[period:]:
        e = (p-e)*mult + e
    return e

def wma(prices, period):
    if len(prices) < period: return None
    subset = prices[-period:]
    denom = period*(period+1)/2
    num = sum(v*(i+1) for i,v in enumerate(subset))
    return num/denom

def calculate_adx(highs, lows, closes, period=14):
    if len(closes) < period*2:
        return 22.0, 18.0, 24.0
    tr_list=[]; plus_dm=[]; minus_dm=[]
    for i in range(1,len(closes)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        tr_list.append(tr)
        up = highs[i]-highs[i-1]
        down = lows[i-1]-lows[i]
        plus_dm.append(up if up>down and up>0 else 0)
        minus_dm.append(down if down>up and down>0 else 0)
    s_tr=sum(tr_list[:period]); s_plus=sum(plus_dm[:period]); s_minus=sum(minus_dm[:period])
    dxs=[]
    for i in range(period,len(tr_list)):
        s_tr = s_tr - s_tr/period + tr_list[i]
        s_plus = s_plus - s_plus/period + plus_dm[i]
        s_minus = s_minus - s_minus/period + minus_dm[i]
        pdi = 100*s_plus/s_tr if s_tr>0 else 0
        mdi = 100*s_minus/s_tr if s_tr>0 else 0
        s = pdi+mdi
        dx = 100*abs(pdi-mdi)/s if s>0 else 0
        dxs.append(dx)
    if not dxs: return 22,18,24
    adx=sum(dxs[:period])/len(dxs[:period])
    for i in range(period,len(dxs)):
        adx = (adx*(period-1)+dxs[i])/period
    pdi = 100*s_plus/s_tr if s_tr>0 else 0
    mdi = 100*s_minus/s_tr if s_tr>0 else 0
    return round(pdi,2), round(mdi,2), round(adx,2)

def calculate_supertrend(highs,lows,closes,period=10,mult=3.0):
    if len(closes) < period+1:
        return closes[-1] if closes else 0, "BULLISH"
    # ATR
    trs=[]
    for i in range(1,len(closes)):
        trs.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    atr = sum(trs[:period])/period
    for i in range(period,len(trs)):
        atr = (atr*(period-1)+trs[i])/period
    hl2=(highs[-1]+lows[-1])/2
    up=hl2+mult*atr
    dn=hl2-mult*atr
    c=closes[-1]
    if c>up: return round(dn,2),"BULLISH"
    if c<dn: return round(up,2),"BEARISH"
    return round(dn,2),"BULLISH"

def analyze_trend(candles: list[dict]) -> dict:
    closes=[c["close"] for c in candles]
    highs=[c["high"] for c in candles]
    lows=[c["low"] for c in candles]
    volumes=[c.get("volume",0) for c in candles]
    if not closes:
        return {"trend":"NEUTRAL","score":50}

    sma20=sma(closes,20)
    ema9=ema(closes,9)
    ema20=ema(closes,20)
    ema50=ema(closes,50)
    wma20=wma(closes,20)
    # VWAP approx
    vwap=None
    if volumes and sum(volumes[-20:])>0:
        tp = [(c["high"]+c["low"]+c["close"])/3 for c in candles[-20:]]
        vwap = sum(t*p for t,p in zip(tp, volumes[-20:]))/sum(volumes[-20:])
    # ADX
    pdi,mdi,adx = calculate_adx(highs,lows,closes)
    st_val,st_dir = calculate_supertrend(highs,lows,closes)
    price=closes[-1]

    checks=[]
    # Price vs VWAP
    if vwap is not None:
        checks.append(price>vwap)
    else:
        checks.append(True)  # neutral
    # EMA relationships
    if ema9 is not None and ema20 is not None:
        checks.append(ema9>ema20)
    else:
        checks.append(False)
    if ema20 is not None and ema50 is not None:
        checks.append(ema20>ema50)
    else:
        checks.append(False)
    checks.append(adx>20 and pdi>mdi)
    # MA slope (ema20 slope)
    if len(closes)>=25 and ema20 is not None:
        prev_ema = ema(closes[:-5],20)
        checks.append((ema20 - (prev_ema or ema20))>0)
    else:
        checks.append(False)

    score = int(round(sum(1 for c in checks if c)/len(checks)*100)) if checks else 50
    # Determine trend
    if score>=65:
        trend="BULLISH"
    elif score<=35:
        trend="BEARISH"
    else:
        trend="NEUTRAL"
    # Bearish score invert
    bearish_checks = [
        vwap is not None and price<vwap,
        ema9 is not None and ema20 is not None and ema9<ema20,
        ema20 is not None and ema50 is not None and ema20<ema50,
        adx>20 and mdi>pdi
    ]
    bearish_score = sum(1 for c in bearish_checks if c)/len(bearish_checks)*100 if bearish_checks else 0
    if bearish_score>=60 and trend=="NEUTRAL":
        trend="BEARISH"
        score=int(bearish_score)

    return {
        "trend": trend,
        "score": score,
        "sma20": round(sma20,2) if sma20 else None,
        "ema9": round(ema9,2) if ema9 else None,
        "ema20": round(ema20,2) if ema20 else None,
        "ema50": round(ema50,2) if ema50 else None,
        "wma20": round(wma20,2) if wma20 else None,
        "vwap": round(vwap,2) if vwap else None,
        "adx": round(adx,2), "plus_di": round(pdi,2), "minus_di": round(mdi,2),
        "supertrend_value": round(st_val,2), "supertrend_direction": st_dir,
        "checks": {"price_above_vwap": checks[0] if len(checks)>0 else None, "ema9_above_ema20": checks[1] if len(checks)>1 else None, "ema20_above_ema50": checks[2] if len(checks)>2 else None, "adx_supports_trend": checks[3] if len(checks)>3 else None}
    }
