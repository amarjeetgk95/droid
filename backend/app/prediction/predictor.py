import math
from datetime import datetime, timezone
from app.prediction.features import feature_vector_for_model
from app.prediction.ensemble import EnsembleModel

HORIZON_MAP = {"1m":10, "5m":20, "15m":60, "1h":120}

def forecast_for_timeframe(features: dict, technical: dict, timeframe: str, symbol: str, asset_class: str, data_timestamp: str | None = None, fno_ctx: dict | None = None) -> dict:
    vec=feature_vector_for_model(features)
    ens=EnsembleModel()
    probs=ens.predict(vec) # up/sideways/down
    # record prediction for performance tracking (store synchronously, non-blocking for chart)
    try:
        from app.prediction.evaluation import store_prediction
        from datetime import datetime as _dt, timezone as _tz
        _now = _dt.now(_tz.utc).isoformat()
    except Exception:
        _now = datetime.now(timezone.utc).isoformat() if 'datetime' in globals() else None
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

    now_iso = datetime.now(timezone.utc).isoformat()
    data_ts = data_timestamp or now_iso
    # §7 strict schema fields plus technical/fno scores
    technical_score = technical.get("score", technical.get("scores",{}).get("overall", 50)) if isinstance(technical.get("scores"), dict) else technical.get("score", 50)
    fno_score = None
    if fno_ctx and fno_ctx.get("available"):
        # proxy fno score from PCR distance from 1 + positioning strength + basis coherence
        try:
            pcr = fno_ctx.get("pcr", 1.0)
            pcr_score = 80 if 0.9 < pcr < 1.15 else 60 if 0.8 < pcr < 1.25 else 40
            pos = fno_ctx.get("futures_positioning", "UNKNOWN")
            pos_score = 78 if pos in ("LONG_BUILDUP","SHORT_BUILDUP") else 55 if pos != "UNKNOWN" else 50
            fno_score = round((pcr_score*0.5 + pos_score*0.5),1)
        except Exception:
            fno_score = 60
    fc_obj = {
        "symbol": symbol,
        "timeframe": timeframe,
        "generated_at": now_iso,
        "data_timestamp": data_ts,
        "forecast_timestamp": now_iso,
        "prediction_timestamp": now_iso,
        "data_age_seconds": 0,
        "horizon_minutes": horizon,
        "direction": {"up": probs["up"], "sideways": probs["sideways"], "down": probs["down"]},
        "expected_move_percent": round(exp_move_pct,3),
        "expected_move_points": round(exp_move_pts,2),
        "expected_range": {"low": round(low,2), "high": round(high,2)},
        "confidence": confidence,
        "confidence_score": round(raw_conf,1),
        "invalidation_level": round(invalidation,2),
        "model_meta": {"model_version": ens.version, "feature_version":"v1", "weights": probs.get("ensemble_weights")},
        "technical_score": round(float(technical_score),1) if technical_score is not None else None,
        "fno_score": fno_score,
        "disclaimer": "Probabilistic forecast — not guaranteed. For decision support only.",
    }
    # Persist for performance tracking (§35, §45)
    try:
        from app.prediction.evaluation import store_prediction
        store_prediction({
            "prediction_timestamp": now_iso,
            "symbol": symbol,
            "timeframe": timeframe,
            "horizon": horizon,
            "forecast_probability": fc_obj["direction"],
            "expected_move": fc_obj["expected_move_percent"],
            "expected_range": fc_obj["expected_range"],
            "confidence": confidence,
            "model_version": ens.version,
            "feature_version": "v1",
            "data_timestamp": data_ts,
        })
    except Exception:
        pass
    return fc_obj
