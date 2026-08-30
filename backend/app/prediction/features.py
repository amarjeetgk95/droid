import math
from datetime import datetime, timezone

def build_features(candles: list[dict], technical: dict, fno: dict, instrument_meta: dict, timestamp: datetime) -> dict:
    """Historical-only feature engineering. No future leakage."""
    if not candles:
        return {}
    closes=[c["close"] for c in candles]
    highs=[c["high"] for c in candles]
    lows=[c["low"] for c in candles]
    vols=[c.get("volume",0) for c in candles]
    price=closes[-1]
    # returns
    ret_1 = (closes[-1]-closes[-2])/closes[-2] if len(closes)>=2 and closes[-2]!=0 else 0
    ret_5 = (closes[-1]-closes[-5])/closes[-5] if len(closes)>=5 and closes[-5]!=0 else 0
    # rolling returns
    # momentum
    momentum = sum(1 for i in range(max(0,len(closes)-5), len(closes)-1) if closes[i+1]>closes[i])/5 if len(closes)>=6 else 0.5
    # range
    rng = (highs[-1]-lows[-1])/price if price!=0 else 0
    # ATR
    atr = technical.get("volatility",{}).get("atr", 0)
    atr_pct = technical.get("volatility",{}).get("atr_pct", 0)
    # distance from VWAP / MAs
    vwap = technical.get("trend",{}).get("vwap")
    dist_vwap = (price - vwap)/price if vwap else 0
    ema20 = technical.get("trend",{}).get("ema20")
    dist_ema20 = (price - ema20)/price if ema20 else 0
    ema50 = technical.get("trend",{}).get("ema50")
    dist_ema50 = (price - ema50)/price if ema50 else 0
    # trend slope via ema20 diff
    trend_slope = dist_ema20
    # indicators
    rsi = technical.get("momentum",{}).get("rsi",50)
    macd = technical.get("momentum",{}).get("macd",0)
    adx = technical.get("trend",{}).get("adx",20)
    boll_width = technical.get("volatility",{}).get("bollinger_width",0)
    stoch_k = technical.get("momentum",{}).get("stoch_k",50)
    roc = technical.get("momentum",{}).get("roc",0)
    # volume features
    vol_available = technical.get("volume",{}).get("available", False)
    rel_vol = technical.get("volume",{}).get("relative_volume",1) if vol_available else 1
    obv = technical.get("volume",{}).get("obv",0) if vol_available else 0
    # structure
    structure = technical.get("price_action",{}).get("structure","UNKNOWN")
    breakout = technical.get("price_action",{}).get("breakout")
    swing_high = technical.get("price_action",{}).get("swing_high", price)
    swing_low = technical.get("price_action",{}).get("swing_low", price)
    dist_support = (price - technical.get("support_resistance",{}).get("support", swing_low))
    dist_resistance = (technical.get("support_resistance",{}).get("resistance", swing_high) - price)
    # F&O
    if fno.get("available"):
        futures_oi_change = fno.get("futures_oi_change",0)
        basis = fno.get("basis",0)
        pcr = fno.get("pcr",1.0)
        call_wall = fno.get("call_wall", price)
        put_wall = fno.get("put_wall", price)
        atm_iv = fno.get("atm_iv", 15)
        iv_change = 0  # placeholder
        call_wall_dist = (call_wall - price)/price if price!=0 else 0
        put_wall_dist = (price - put_wall)/price if price!=0 else 0
    else:
        futures_oi_change = basis = pcr = call_wall_dist = put_wall_dist = None
        atm_iv = iv_change = None
    # Time
    hour = timestamp.hour
    dow = timestamp.weekday()
    # expiry distance (use fno if available)
    expiry_dist = fno.get("distance_to_expiry_days", None) if fno.get("available") else None
    # timezone/session
    feat = {
        "asset_class": instrument_meta.get("asset_class"),
        "exchange": instrument_meta.get("exchange"),
        "instrument_type": instrument_meta.get("instrument_type"),
        "currency": instrument_meta.get("currency"),
        "session_state": "OPEN",
        "returns_1": round(ret_1,5),
        "returns_5": round(ret_5,5),
        "momentum_5": round(momentum,3),
        "range_pct": round(rng,5),
        "atr": round(atr,3),
        "atr_pct": round(atr_pct,5),
        "price_dist_vwap": round(dist_vwap,5),
        "price_dist_ema20": round(dist_ema20,5),
        "price_dist_ema50": round(dist_ema50,5),
        "trend_slope": round(trend_slope,5),
        "rsi": round(rsi,2),
        "macd": round(macd,4),
        "adx": round(adx,2),
        "bollinger_width": round(boll_width,4) if boll_width else 0,
        "stoch_k": round(stoch_k,2),
        "roc": round(roc,4),
        "rel_volume": round(rel_vol,3),
        "obv_norm": round(math.tanh(obv/1e6),4) if vol_available else 0,
        "structure": structure,
        "breakout": breakout,
        "dist_support": round(dist_support,2),
        "dist_resistance": round(dist_resistance,2),
        "futures_oi_change": futures_oi_change,
        "basis": basis,
        "pcr": pcr,
        "call_wall_dist": call_wall_dist,
        "put_wall_dist": put_wall_dist,
        "atm_iv": atm_iv,
        "hour": hour,
        "dow": dow,
        "expiry_distance_days": expiry_dist,
        "price": price,
    }
    return feat

def feature_vector_for_model(feat: dict) -> list[float]:
    """Ordered numeric vector for ML (no leakage, handles missing F&O as 0)."""
    def safe(v, default=0):
        return float(v) if v is not None else float(default)
    # normalized
    rsi_norm = (safe(feat.get("rsi",50))-50)/50
    adx_strength = min(1,max(0,safe(feat.get("adx",20))/50))
    macd_norm = math.tanh(safe(feat.get("macd",0))*10)
    boll_w = safe(feat.get("bollinger_width",0))/10
    stoch_norm = (safe(feat.get("stoch_k",50))-50)/50
    roc_norm = math.tanh(safe(feat.get("roc",0))*5)
    rel_vol_norm = min(2,safe(feat.get("rel_volume",1)))/2
    dist_vwap = safe(feat.get("price_dist_vwap",0))*100
    dist_ema20 = safe(feat.get("price_dist_ema20",0))*100
    dist_ema50 = safe(feat.get("price_dist_ema50",0))*100
    trend_slope = safe(feat.get("trend_slope",0))*100
    ret1 = safe(feat.get("returns_1",0))*100
    ret5 = safe(feat.get("returns_5",0))*100
    # F&O (0 if unavailable, model must handle)
    f_oi = safe(feat.get("futures_oi_change",0))/10
    basis = safe(feat.get("basis",0))/100
    pcr_dev = (safe(feat.get("pcr",1))-1)/0.5
    call_dist = safe(feat.get("call_wall_dist",0))*100
    put_dist = safe(feat.get("put_wall_dist",0))*100
    iv = safe(feat.get("atm_iv",15))/30
    # time
    hour_norm = safe(feat.get("hour",10))/24
    dow_norm = safe(feat.get("dow",2))/7
    expiry = safe(feat.get("expiry_distance_days",5))/30
    return [
        rsi_norm, adx_strength, macd_norm, boll_w, stoch_norm, roc_norm,
        rel_vol_norm, dist_vwap, dist_ema20, dist_ema50, trend_slope, ret1, ret5,
        f_oi, basis, pcr_dev, call_dist, put_dist, iv,
        hour_norm, dow_norm, expiry
    ]
