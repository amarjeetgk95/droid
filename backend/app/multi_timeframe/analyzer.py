from app.multi_timeframe.alignment import compute_alignment
from app.multi_timeframe.scoring import compute_technical_scores

def analyze_multi_timeframe(analyses: dict, forecasts: dict, fno_available: bool) -> dict:
    alignment=compute_alignment(analyses)
    tech_scores=compute_technical_scores(analyses)
    # confidence considering alignment, model agreement, etc.
    # Simple heuristic
    avg_conf = sum(f.get("confidence_score",50) for f in forecasts.values())/len(forecasts) if forecasts else 50
    # Data freshness considered later
    mtf_score = alignment["alignment_score"]
    combined_conf = round((mtf_score*0.4 + avg_conf*0.6),1)
    if combined_conf>=70: conf_label="HIGH"
    elif combined_conf>=45: conf_label="MODERATE"
    else: conf_label="LOW"

    # Build per-TF summary for UI
    per_tf={}
    for tf in ["1m","5m","15m","1h"]:
        if tf in analyses:
            per_tf[tf]={"bias": analyses[tf]["bias"], "score": analyses[tf].get("score",50), "forecast": forecasts.get(tf)}

    return {
        "per_timeframe": per_tf,
        "alignment": alignment,
        "technical_scores": tech_scores,
        "confidence": conf_label,
        "confidence_score": combined_conf,
        "fno_available": fno_available,
    }
