def _find_swings(prices, lookback=5):
    """return indices of peaks and troughs"""
    peaks=[]; troughs=[]
    for i in range(lookback, len(prices)-lookback):
        is_peak = all(prices[i]>=prices[i-j] for j in range(1,lookback+1)) and all(prices[i]>=prices[i+j] for j in range(1,lookback+1))
        is_trough = all(prices[i]<=prices[i-j] for j in range(1,lookback+1)) and all(prices[i]<=prices[i+j] for j in range(1,lookback+1))
        if is_peak: peaks.append(i)
        if is_trough: troughs.append(i)
    return peaks, troughs

def detect_divergences(candles: list[dict], rsi_series: list[float] | None = None) -> list[dict]:
    closes=[c["close"] for c in candles]
    if len(closes)<20:
        return []
    # compute RSI series if not provided
    if rsi_series is None:
        # simple rsi series
        rsi_series=[]
        for i in range(len(closes)):
            if i<14:
                rsi_series.append(50)
            else:
                subset=closes[max(0,i-14):i+1]
                # quick calc
                gains=sum(max(0,subset[j]-subset[j-1]) for j in range(1,len(subset)))/14
                losses=sum(max(0,subset[j-1]-subset[j]) for j in range(1,len(subset)))/14
                if losses==0:
                    rsi_series.append(100 if gains>0 else 50)
                else:
                    rs=gains/losses
                    rsi_series.append(100-100/(1+rs))
    peaks, troughs = _find_swings(closes, lookback=3)
    divergences=[]
    # Check last two peaks for divergence
    if len(peaks)>=2:
        p1, p2 = peaks[-2], peaks[-1]
        price_higher = closes[p2] > closes[p1]
        rsi_lower = rsi_series[p2] < rsi_series[p1]
        rsi_higher = rsi_series[p2] > rsi_series[p1]
        if price_higher and rsi_lower:
            divergences.append({"indicator":"RSI","type":"BEARISH_DIVERGENCE","price_swing":[closes[p1],closes[p2]],"indicator_swing":[rsi_series[p1],rsi_series[p2]],"time_range":f"{p1}-{p2}","confidence":0.65})
        if not price_higher and rsi_higher:
            divergences.append({"indicator":"RSI","type":"BULLISH_DIVERGENCE","price_swing":[closes[p1],closes[p2]],"indicator_swing":[rsi_series[p1],rsi_series[p2]],"time_range":f"{p1}-{p2}","confidence":0.55})
        # hidden
        if price_higher and rsi_higher:
            divergences.append({"indicator":"RSI","type":"HIDDEN_BULLISH_DIVERGENCE","price_swing":[closes[p1],closes[p2]],"indicator_swing":[rsi_series[p1],rsi_series[p2]],"time_range":f"{p1}-{p2}","confidence":0.5})
    if len(troughs)>=2:
        t1,t2 = troughs[-2], troughs[-1]
        price_lower = closes[t2] < closes[t1]
        rsi_higher = rsi_series[t2] > rsi_series[t1]
        if price_lower and rsi_higher:
            divergences.append({"indicator":"RSI","type":"BULLISH_DIVERGENCE","price_swing":[closes[t1],closes[t2]],"indicator_swing":[rsi_series[t1],rsi_series[t2]],"time_range":f"{t1}-{t2}","confidence":0.65})
    return divergences
