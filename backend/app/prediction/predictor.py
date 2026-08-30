import math
from datetime import datetime, timezone
from app.prediction.features import feature_vector_for_model
from app.prediction.ensemble import EnsembleModel

HORIZON_MAP = {"1m":10, "5m":20, "15m":60, "1h":120}

def forecast_for_timeframe(features: dict, technical: dict, timeframe: str, symbol: str, asset_class: str) -> dict:
    vec=feature_vector_for_model(features)
    ens=EnsembleModel()
    probs=ens.predict(vec) # up/sideways/down
    # expected move % based on ATR% and model confidence
    atr_pct = technical.get("volatility",{}).get("atr_pct", 0.5)
    vol = technical.get("volatility",{}).get("rolling_volatility", atr_pct)
    # scale by horizon
    horizon = HORIZON_MAP.get(timeframe, 30)
    # expected move approx volatility * sqrt(horizon/60) * direction bias
    direction_bias = probs["up"] - probs["down"]
    exp_move_pct = round((atr_pct*0.6 + vol*0.4) * math.sqrt(horizon/60) * (0.5+0.5*abs(direction_bias)), 3)
    # if neutral, smaller
    if probs["sideways"]>0.4:
        exp_move_pct*=0.6
    price=features.get("price", 25000)
    exp_move_pts = price*exp_move_pct/100
    # range: +/- 1 ATR scaled
    atr = technical.get("volatility",{}).get("atr", price*0.005)
    # confidence based on separation and agreement
    sep = max(probs["up"], probs["sideways"], probs["down"]) - sorted([probs["up"], probs["sideways"], probs["down"]])[-2]
    agreement = 1 - abs(probs["up"]-probs["down"])*0.2  # not great but placeholder
    # model agreement (lgb vs xgb)
    lgb_up = probs["lgb"][0] if "lgb" in probs else probs["up"]
    xgb_up = probs["xgb"][0] if "xgb" in probs else probs["up"]
    model_agree = 1 - abs(lgb_up - xgb_up)
    raw_conf = (sep*0.5 + model_agree*0.3 + (1 if atr_pct<1.5 else 0.5)*0.2)*100
    if raw_conf>=70: confidence="HIGH"
    elif raw_conf>=45: confidence="MODERATE"
    else: confidence="LOW"

    # expected range
    # bullish bias: upper larger
    if probs["up"]>probs["down"]:
        low = price - atr*0.8
        high = price + atr*1.4 + exp_move_pts*0.5
    elif probs["down"]>probs["up"]:
        low = price - atr*1.4 - exp_move_pts*0.5
        high = price + atr*0.8
    else:
        low = price - atr
        high = price + atr
    # invalidation = support/resistance opposite
    sr = technical.get("support_resistance",{})
    invalidation = sr.get("support") if probs["up"]>probs["down"] else sr.get("resistance")
    if not invalidation:
        invalidation = price*0.99 if probs["up"]>probs["down"] else price*1.01

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "horizon_minutes": horizon,
        "direction": {"up": probs["up"], "sideways": probs["sideways"], "down": probs["down"]},
        "expected_move_percent": round(exp_move_pct,3),
        "expected_move_points": round(exp_move_pts,2),
        "expected_range": {"low": round(low,2), "high": round(high,2)},
        "confidence": confidence,
        "confidence_score": round(raw_conf,1),
        "prediction_timestamp": datetime.now(timezone.utc).isoformat(),
        "invalidation_level": round(invalidation,2),
        "model_meta": {"model_version": ens.version, "feature_version":"v1", "weights": probs.get("ensemble_weights")},
    }
