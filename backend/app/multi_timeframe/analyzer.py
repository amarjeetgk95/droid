from app.multi_timeframe.alignment import compute_alignment
from app.multi_timeframe.scoring import compute_technical_scores

def analyze_multi_timeframe(analyses: dict, forecasts: dict, fno_available: bool) -> dict:
    # Filter out data-unavailable TFs
    analyses = {k: v for k, v in (analyses or {}).items() if not v.get("data_unavailable")}
    forecasts = {k: v for k, v in (forecasts or {}).items() if not v.get("data_unavailable")}
    alignment=compute_alignment(analyses)
    tech_scores=compute_technical_scores(analyses) if analyses else {}
    avg_conf = sum(f.get("confidence_score",50) for f in forecasts.values())/len(forecasts) if forecasts else 50
    mtf_score = alignment.get("alignment_score", 0) if alignment else 0
    combined_conf = round((mtf_score*0.4 + avg_conf*0.6),1) if forecasts else round(mtf_score*0.4,1)
    if combined_conf>=70: conf_label="HIGH"
    elif combined_conf>=45: conf_label="MODERATE"
    else: conf_label="LOW"

    per_tf={}
    for tf in ["1m","5m","15m","1h","4h","1D"]:
        if tf in analyses:
            # Signal quality: no strong signal from single indicator; use overall bias
            # When indicators conflict, alignment.conflict handles Mixed/Low Confidence
            per_tf[tf]={"bias": analyses[tf].get("bias","NEUTRAL"), "score": analyses[tf].get("score",50), "forecast": forecasts.get(tf), "data_unavailable": False}
        elif tf in forecasts and forecasts[tf].get("data_unavailable"):
            per_tf[tf]={"bias": "NEUTRAL", "score": 0, "forecast": forecasts[tf], "data_unavailable": True}

    return {
        "per_timeframe": per_tf,
        "alignment": alignment,
        "technical_scores": tech_scores,
        "confidence": conf_label,
        "confidence_score": combined_conf,
        "fno_available": fno_available,
        "signal_quality_note": "High confidence requires price structure + trend + momentum + volume + volatility + derivatives positioning; conflicting indicators → Mixed / Low Confidence",
    }
