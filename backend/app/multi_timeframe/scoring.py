def compute_technical_scores(analyses: dict) -> dict:
    # aggregate per timeframe scores
    scores={}
    for tf, data in analyses.items():
        s=data.get("scores",{})
        scores[tf]=s
    # Overall technical score: weighted avg of overs
    from app.market_data.timeframes import TIMEFRAME_CONFIG
    total_w=0; weighted_sum=0
    for tf, s in scores.items():
        w=TIMEFRAME_CONFIG.get(tf,{}).get("weight",0.25)
        total_w+=w
        weighted_sum+= s.get("overall",50)*w
    overall_tech = round(weighted_sum/total_w,1) if total_w>0 else 50
    # Component scores averaged across TFs
    components=["trend","momentum","volume","volatility","structure"]
    comp_avg={}
    for comp in components:
        vals=[ s.get(comp) for s in scores.values() if s.get(comp) is not None ]
        comp_avg[comp]= round(sum(vals)/len(vals),1) if vals else None
    return {"per_timeframe": scores, "overall_technical_score": overall_tech, "components_avg": comp_avg}
