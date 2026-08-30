from app.technical_analysis.price_action import analyze_price_action
from app.technical_analysis.trend import analyze_trend
from app.technical_analysis.momentum import analyze_momentum
from app.technical_analysis.volatility import analyze_volatility
from app.technical_analysis.volume import analyze_volume
from app.technical_analysis.candlestick import detect_candlesticks, candlestick_summary
from app.technical_analysis.chart_patterns import detect_chart_patterns
from app.technical_analysis.divergence import detect_divergences
from app.technical_analysis.support_resistance import calculate_support_resistance

def analyze_timeframe(candles: list[dict], symbol: str, timeframe: str, fno_levels: dict|None=None, vix: float|None=None) -> dict:
    if not candles:
        return {"symbol": symbol, "timeframe": timeframe, "error": "No candles"}
    pa = analyze_price_action(candles)
    trend = analyze_trend(candles)
    momentum = analyze_momentum(candles)
    volatility = analyze_volatility(candles, vix=vix, fno_iv=fno_levels.get("atm_iv") if fno_levels else None)
    volume = analyze_volume(candles)
    cand_patterns = detect_candlesticks(candles, volume_info=volume)
    cand_summary = candlestick_summary(cand_patterns)
    chart_pats = detect_chart_patterns(candles)
    divergences = detect_divergences(candles)
    sr = calculate_support_resistance(candles, candles[-1]["close"], fno_levels=fno_levels)

    # Technical scores
    trend_score = trend.get("score",50)
    momentum_score = momentum.get("score",50)
    volume_score = volume.get("score",50) if volume.get("available") else None
    volatility_score = volatility.get("score",50)
    structure_score = 80 if pa["structure"] in ("HIGHER_HIGH_HIGHER_LOW","LOWER_LOW_LOWER_HIGH") else 60 if pa["structure"]!="CONSOLIDATION" else 40
    # Overall
    scores=[trend_score, momentum_score, volatility_score, structure_score]
    if volume_score is not None:
        scores.append(volume_score)
    overall = round(sum(scores)/len(scores),1)
    # Bias
    if overall>=65:
        bias="BULLISH"
    elif overall<=35:
        bias="BEARISH"
    else:
        bias="NEUTRAL"
    # Bias override from trend
    if trend["trend"]=="BULLISH" and bias=="NEUTRAL" and trend_score>60:
        bias="BULLISH"
    if trend["trend"]=="BEARISH" and bias=="NEUTRAL" and trend_score>60:
        # trend_score for bearish is still high but direction is bearish - check
        if trend["trend"]=="BEARISH":
            bias="BEARISH"

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "price_action": pa,
        "trend": trend,
        "momentum": momentum,
        "volatility": volatility,
        "volume": volume,
        "candlestick": {"patterns": cand_patterns, "summary": cand_summary},
        "chart_patterns": chart_pats,
        "divergences": divergences,
        "support_resistance": sr,
        "scores": {
            "trend": trend_score,
            "momentum": momentum_score,
            "volume": volume_score,
            "volatility": volatility_score,
            "structure": structure_score,
            "overall": overall,
        },
        "bias": bias,
        "score": overall,
        "current_price": candles[-1]["close"],
        "data_timestamp": candles[-1].get("timestamp"),
    }
