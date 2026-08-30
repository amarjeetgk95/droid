from app.market_data.timeframes import TIMEFRAME_CONFIG

def compute_alignment(analyses: dict[str, dict]) -> dict:
    """analyses: dict timeframe -> analyze_timeframe result
    Compares the 6 chart T.F.s: 1m, 5m, 15m, 1h, 4h, 1D.  Handles data-unavailable
    TFs by excluding them.  Higher TFs provide context; lower TFs entry timing.
    """
    tfs = ["1m","5m","15m","1h","4h","1D"]
    # Exclude data-unavailable entries
    analyses = {k: v for k, v in (analyses or {}).items() if not v.get("data_unavailable")}
    if not analyses:
        return {
            "biases": {},
            "scores": {},
            "alignment_score": 0.0,
            "alignment_count": "0/0",
            "bull_count": 0, "bear_count": 0, "neutral_count": 0,
            "overall_bias": "NEUTRAL",
            "dominant_timeframe": None,
            "conflict": False,
            "mixed_low_confidence": True,
            "interpretation": "Data unavailable — no alignment.",
            "weighting": {tf: TIMEFRAME_CONFIG.get(tf,{}).get("weight") for tf in tfs},
            "regime_note": "Mixed / Low Confidence",
        }
    biases = {tf: analyses[tf]["bias"] for tf in tfs if tf in analyses}
    scores = {tf: analyses[tf].get("score",50) for tf in tfs if tf in analyses}
    # Count bullish/bearish/neutral
    bull=sum(1 for b in biases.values() if b=="BULLISH")
    bear=sum(1 for b in biases.values() if b=="BEARISH")
    neut=sum(1 for b in biases.values() if b=="NEUTRAL")
    total=len(biases)
    alignment_score=0
    if total>0:
        # Use weighting from timeframe config
        weighted_bull=0; weighted_bear=0; weighted_total=0
        for tf,bias in biases.items():
            w=TIMEFRAME_CONFIG.get(tf,{}).get("weight",0.25)
            weighted_total+=w
            if bias=="BULLISH": weighted_bull+=w
            elif bias=="BEARISH": weighted_bear+=w
        # alignment = max weighted share
        alignment_score = max(weighted_bull, weighted_bear, weighted_total-weighted_bull-weighted_bear)/weighted_total*100 if weighted_total>0 else 0
    # dominant timeframe: highest score among bullish if overall bullish else etc
    dominant=None
    if bull>bear and bull>neut:
        # bullish majority
        overall_bias="BULLISH"
        # dominant = highest score bullish TF
        bullish_tfs=[tf for tf,b in biases.items() if b=="BULLISH"]
        dominant=max(bullish_tfs, key=lambda tf: scores.get(tf,0)) if bullish_tfs else None
    elif bear>bull and bear>neut:
        overall_bias="BEARISH"
        bearish_tfs=[tf for tf,b in biases.items() if b=="BEARISH"]
        dominant=max(bearish_tfs, key=lambda tf: scores.get(tf,0)) if bearish_tfs else None
    else:
        # check weighted
        if weighted_bull>weighted_bear and weighted_bull>0.4:
            overall_bias="BULLISH"
        elif weighted_bear>weighted_bull and weighted_bear>0.4:
            overall_bias="BEARISH"
        else:
            overall_bias="NEUTRAL"
        dominant=max(scores, key=lambda k: scores[k]) if scores else None

    # interpretation
    if overall_bias=="BULLISH" and biases.get("1h")=="NEUTRAL":
        interpretation="Short-term bullish movement inside a neutral higher-timeframe structure."
    elif overall_bias=="BEARISH" and biases.get("1h")=="NEUTRAL":
        interpretation="Short-term bearish movement inside a neutral higher-timeframe structure."
    elif overall_bias=="NEUTRAL":
        interpretation="Timeframes are mixed / neutral — no strong directional alignment."
    elif bull==total:
        interpretation="Strong bullish alignment across all timeframes."
    elif bear==total:
        interpretation="Strong bearish alignment across all timeframes."
    else:
        interpretation=f"{overall_bias} bias with {bull if overall_bias=='BULLISH' else bear}/{total} timeframe agreement."

    # conflict detection
    conflict = (bull>0 and bear>0)
    # Cross-timeframe confirmation statuses per spec
    if bull==total and total>=4:
        cross_status = "Strong bullish alignment"
    elif bear==total and total>=4:
        cross_status = "Strong bearish alignment"
    elif conflict:
        cross_status = "Mixed signals"
    elif overall_bias=="NEUTRAL":
        cross_status = "Mixed / Low Confidence"
    else:
        cross_status = interpretation

    # Higher-TF context vs lower-TF entry timing detection
    higher_tfs = ["1D","4h","1h"]
    lower_tfs = ["1m","5m","15m"]
    higher_biases = [biases[tf] for tf in higher_tfs if tf in biases]
    lower_biases = [biases[tf] for tf in lower_tfs if tf in biases]
    higher_bull = sum(1 for b in higher_biases if b=="BULLISH")
    higher_bear = sum(1 for b in higher_biases if b=="BEARISH")
    lower_bull = sum(1 for b in lower_biases if b=="BULLISH")
    lower_bear = sum(1 for b in lower_biases if b=="BEARISH")
    short_term_reversal = (higher_bull>0 and lower_bear>0) or (higher_bear>0 and lower_bull>0)
    trend_continuation = not short_term_reversal and not conflict and overall_bias!="NEUTRAL"
    possible_regime_change = conflict and (higher_bull>0 or higher_bear>0) and (lower_bull>0 or lower_bear>0)

    return {
        "biases": biases,
        "scores": scores,
        "alignment_score": round(alignment_score,1),
        "alignment_count": f"{max(bull,bear,neut)}/{total}",
        "bull_count": bull, "bear_count": bear, "neutral_count": neut,
        "overall_bias": overall_bias,
        "dominant_timeframe": dominant,
        "conflict": conflict,
        "mixed_low_confidence": conflict or overall_bias=="NEUTRAL",
        "interpretation": interpretation,
        "cross_timeframe_status": cross_status,
        "higher_timeframe_context": {"timeframes": higher_tfs, "biases": {tf: biases[tf] for tf in higher_tfs if tf in biases}},
        "lower_timeframe_timing": {"timeframes": lower_tfs, "biases": {tf: biases[tf] for tf in lower_tfs if tf in biases}},
        "short_term_reversal_against_htf": short_term_reversal,
        "trend_continuation": trend_continuation,
        "possible_regime_change": possible_regime_change,
        "weighting": {tf: TIMEFRAME_CONFIG.get(tf,{}).get("weight") for tf in tfs},
    }
