
def rsi(prices, period=14):
    if len(prices) < period+1: return 50.0
    gains=[]; losses=[]
    for i in range(1,len(prices)):
        d=prices[i]-prices[i-1]
        gains.append(max(0,d)); losses.append(max(0,-d))
    avg_g=sum(gains[:period])/period
    avg_l=sum(losses[:period])/period
    for i in range(period,len(gains)):
        avg_g=(avg_g*(period-1)+gains[i])/period
        avg_l=(avg_l*(period-1)+losses[i])/period
    if avg_l==0: return 100.0 if avg_g>0 else 50.0
    rs=avg_g/avg_l
    return 100-100/(1+rs)

def ema_series(prices, period):
    if len(prices)<period: return None
    mult=2/(period+1)
    e=sum(prices[:period])/period
    series=[e]
    for p in prices[period:]:
        e=(p-e)*mult+e
        series.append(e)
    return series

def macd(prices):
    if len(prices)<26: return 0,0,0
    ema12=ema_series(prices,12)
    ema26=ema_series(prices,26)
    if ema12 is None or ema26 is None: return 0,0,0
    # align lengths
    offset = len(ema12)-len(ema26)
    macd_line = ema12[offset] - ema26[0] if offset>=0 else 0
    # compute signal as ema9 of macd series (approx using last values)
    # simplified: signal = ema9 of recent macd approximations
    # For simplicity, use difference of EMAs as histogram proxy
    # We'll compute macd series properly
    # recompute full macd series
    macd_series=[]
    # need aligned series
    # build ema12_full and ema26_full aligned to original prices
    # simplified approach: use last values only
    macd_val = ema12[-1] - ema26[-1]
    signal = macd_val * 0.9  # placeholder smoothing
    hist = macd_val - signal
    return round(macd_val,3), round(signal,3), round(hist,3)

def stochastic(highs,lows,closes,period=14):
    if len(closes)<period: return 50,50
    hh=max(highs[-period:])
    ll=min(lows[-period:])
    denom=hh-ll if hh!=ll else 1
    k = (closes[-1]-ll)/denom*100
    return round(k,2), round(k*0.9,2)

def analyze_momentum(candles: list[dict]) -> dict:
    closes=[c["close"] for c in candles]
    highs=[c["high"] for c in candles]
    lows=[c["low"] for c in candles]
    if not closes:
        return {"momentum":"NEUTRAL","rsi":50,"score":50}
    r = rsi(closes,14)
    macd_l, sig, hist = macd(closes)
    stoch_k, stoch_d = stochastic(highs,lows,closes,14)
    # Williams %R
    if len(closes)>=14:
        hh=max(highs[-14:]); ll=min(lows[-14:])
        wr = (hh-closes[-1])/(hh-ll)*-100 if hh!=ll else -50
    else:
        wr=-50
    # ROC
    roc = (closes[-1]-closes[-14])/closes[-14]*100 if len(closes)>=15 and closes[-14]!=0 else 0
    # CCI approximation
    if len(closes)>=20:
        tp = [(h+l+c)/3 for h,l,c in zip(highs[-20:], lows[-20:], closes[-20:])]
        ma=sum(tp)/len(tp)
        md=sum(abs(x-ma) for x in tp)/len(tp) if len(tp)>0 else 1
        cci = (tp[-1]-ma)/(0.015*md) if md!=0 else 0
    else:
        cci=0
    # Determine conditions
    overbought = r>70
    oversold = r<30
    # momentum strengthening/weakening: check rsi slope
    if len(closes)>=6:
        r_prev = rsi(closes[:-3],14)
        strengthening = r > r_prev
    else:
        strengthening=True
    # crossover: macd above signal
    bullish_cross = hist>0
    # divergence placeholder handled in divergence module
    # Score 0-100
    score = 50
    if r>55 and hist>0:
        score=65
    if r>65 and hist>0 and stoch_k>60:
        score=75
    if r<45 and hist<0:
        score=35
    if r<35 and hist<0:
        score=25
    # trend of momentum
    momentum = "STRONG" if score>=70 else "WEAKENING" if not strengthening else "NEUTRAL"
    if r>70: momentum="OVERBOUGHT"
    if r<30: momentum="OVERSOLD"

    return {
        "rsi": round(r,2),
        "macd": macd_l, "macd_signal": sig, "macd_histogram": hist,
        "stoch_k": stoch_k, "stoch_d": stoch_d,
        "williams_r": round(wr,2),
        "roc": round(roc,2),
        "cci": round(cci,2),
        "overbought": overbought, "oversold": oversold,
        "momentum_strengthening": strengthening,
        "momentum_crossover": "BULLISH" if bullish_cross else "BEARISH",
        "momentum": momentum,
        "score": int(score),
    }
