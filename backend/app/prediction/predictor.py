import math
from datetime import datetime, timezone
from app.prediction.features import feature_vector_for_model
from app.prediction.ensemble import EnsembleModel

HORIZON_MAP = {"1m":10, "5m":20, "15m":60, "1h":120, "4h":240, "1D":1440, "1d":1440}

def forecast_for_timeframe(features: dict, technical: dict, timeframe: str, symbol: str, asset_class: str, data_timestamp: str | None = None, fno_ctx: dict | None = None, crypto_ctx: dict | None = None) -> dict:
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
    technical_score = technical.get("score", technical.get("scores",{}).get("overall", 50)) if isinstance(technical.get("scores"), dict) else technical.get("score", 50)
    fno_score = None
    derivatives_bias = "NEUTRAL"
    # Try index FNO first, then crypto derivatives
    if fno_ctx and fno_ctx.get("available"):
        # Check if this is crypto derivatives (funding_rate etc) vs index FNO (pcr)
        if "funding_rate" in fno_ctx or (crypto_ctx and crypto_ctx.get("available")):
            # Crypto: use funding_rate + long/short + basis
            try:
                ctx = crypto_ctx if crypto_ctx and crypto_ctx.get("available") else fno_ctx
                funding = ctx.get("funding_rate", 0)
                lsr = ctx.get("long_short_ratio") or ctx.get("long_short_ratio", 1)
                basis_pct = ctx.get("basis_percent", 0) or 0
                # funding positive -> long bias (perpetual premium), long_short >1 -> long bias
                # simple proxy
                if funding > 0.0005 and (lsr or 1) > 1.3: derivatives_bias = "BULLISH"
                elif funding < -0.0001 and (lsr or 1) < 0.9: derivatives_bias = "BEARISH"
                elif funding > 0.0003: derivatives_bias = "BULLISH"
                elif funding < -0.0001: derivatives_bias = "BEARISH"
                # basis contango vs backwardation
                if basis_pct and basis_pct > 0.3 and derivatives_bias == "NEUTRAL":
                    derivatives_bias = "BULLISH"
                elif basis_pct and basis_pct < -0.3 and derivatives_bias == "NEUTRAL":
                    derivatives_bias = "BEARISH"
                # score proxy
                fno_score = 65 if derivatives_bias != "NEUTRAL" else 50
            except Exception:
                fno_score = 50
        else:
            try:
                pcr = fno_ctx.get("pcr", 1.0)
                pcr_score = 80 if 0.9 < pcr < 1.15 else 60 if 0.8 < pcr < 1.25 else 40
                pos = fno_ctx.get("futures_positioning", "UNKNOWN")
                pos_score = 78 if pos in ("LONG_BUILDUP","SHORT_BUILDUP") else 55 if pos != "UNKNOWN" else 50
                fno_score = round((pcr_score*0.5 + pos_score*0.5),1)
                if pcr < 0.9 and pos == "LONG_BUILDUP": derivatives_bias = "BULLISH"
                elif pcr > 1.2 and pos == "SHORT_BUILDUP": derivatives_bias = "BEARISH"
                elif pcr > 1.15: derivatives_bias = "BEARISH"
                elif pcr < 0.85: derivatives_bias = "BULLISH"
            except Exception:
                fno_score = 60
    elif crypto_ctx and crypto_ctx.get("available"):
        try:
            funding = crypto_ctx.get("funding_rate", 0)
            lsr = crypto_ctx.get("long_short_ratio", 1)
            if funding > 0.0003: derivatives_bias = "BULLISH"
            elif funding < -0.0001: derivatives_bias = "BEARISH"
            fno_score = 60 if derivatives_bias != "NEUTRAL" else 50
        except Exception:
            fno_score = 50

    # Direction label, confidence %, key levels, invalidation, reason (spec required)
    if probs["up"] > probs["down"] and probs["up"] > probs["sideways"]:
        direction_label = "Bullish"
    elif probs["down"] > probs["up"] and probs["down"] > probs["sideways"]:
        direction_label = "Bearish"
    else:
        direction_label = "Neutral"
    # Mixed / Low Confidence when indicators conflict
    if confidence == "LOW" or raw_conf < 45:
        direction_label_for_display = "Neutral" if direction_label != "Neutral" and raw_conf < 40 else direction_label
    else:
        direction_label_for_display = direction_label

    # Key support/resistance from SR
    key_support = sr.get("support")
    key_resistance = sr.get("resistance")
    # Market regime from volatility + trend
    vol_class = technical.get("volatility",{}).get("classification", "NORMAL")
    trend_label = technical.get("trend",{}).get("trend", technical.get("bias", "NEUTRAL"))
    market_regime = f"{vol_class} / {trend_label}"

    # Technical bias
    technical_bias = technical.get("bias", trend_label)

    # Reason: concise measurable evidence
    # Build from price structure + trend + momentum + volume + volatility + derivatives positioning
    pa_struct = technical.get("price_action",{}).get("structure", "UNKNOWN")
    mom_rsi = technical.get("momentum",{}).get("rsi", 50)
    mom_hist = technical.get("momentum",{}).get("macd_histogram", 0)
    vol_flag = "high vol" if vol_class in ("HIGH","EXPANDING") else "low vol" if vol_class in ("LOW","CONTRACTING") else "normal vol"
    vol_avail = technical.get("volume",{}).get("available", False)
    vol_rel = technical.get("volume",{}).get("relationship", "unknown")
    # Signal quality: no strong signal from single indicator
    # High confidence only if multiple independent factors agree
    factors = []
    factors.append(f"structure {pa_struct}")
    factors.append(f"trend {trend_label} ({technical_score})")
    factors.append(f"RSI {mom_rsi:.0f} MACD hist {mom_hist:+.2f}")
    factors.append(f"vol {vol_flag} ATR {atr:.2f}")
    factors.append(f"volume {vol_rel}" if vol_avail else "volume n/a")
    if fno_ctx and fno_ctx.get("available"):
        factors.append(f"PCR {fno_ctx.get('pcr', '—')} {fno_ctx.get('futures_positioning','')}")
    else:
        factors.append("derivatives n/a")
    # Determine if conflicting
    # Conflict if technical bullish but derivatives bearish etc.
    conflicting = (technical_bias == "BULLISH" and derivatives_bias == "BEARISH") or (technical_bias == "BEARISH" and derivatives_bias == "BULLISH")
    if conflicting:
        reason_prefix = "Mixed / Low Confidence — conflicting signals: "
    elif confidence == "LOW":
        reason_prefix = "Mixed / Low Confidence — weak confluence: "
    else:
        reason_prefix = ""
    reason = reason_prefix + "; ".join(factors[:4]) + f"; derivatives {derivatives_bias}"
    # Cap length
    if len(reason) > 300:
        reason = reason[:297] + "..."

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
        "direction_label": direction_label,
        "direction_display": direction_label_for_display,
        "confidence": confidence,
        "confidence_score": round(raw_conf,1),
        "confidence_percent": round(raw_conf,1),
        "expected_move_percent": round(exp_move_pct,3),
        "expected_move_points": round(exp_move_pts,2),
        "expected_range": {"low": round(low,2), "high": round(high,2)},
        "key_support": round(key_support,2) if key_support else None,
        "key_resistance": round(key_resistance,2) if key_resistance else None,
        "invalidation_level": round(invalidation,2),
        "market_regime": market_regime,
        "technical_bias": technical_bias,
        "derivatives_bias": derivatives_bias,
        "reason": reason,
        "mixed_low_confidence": conflicting or confidence == "LOW",
        "current_price": round(price,2),
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
