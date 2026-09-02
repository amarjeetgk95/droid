"""
Market Regime Classification — §10
Classifies the active market environment into contextual regimes to ensure compatible historical matching.
"""
from __future__ import annotations

from app.quant.historical_intelligence.models import MarketRegime, NormalizedFeatures


def classify_regime(features: NormalizedFeatures) -> MarketRegime:
    """
    Classifies market regime based on trend strength, volatility expansion, and price location.
    """
    # 1. Breakout Check
    if features.is_expanding and features.relative_volume > 1.35 and abs(features.total_return_pct) > 0.4:
        return MarketRegime.BREAKOUT

    # 2. Strong Trend Check
    if features.trend_strength > 0.65 and abs(features.ema_slope_short) > 0.035:
        if features.trend_direction == "UP":
            return MarketRegime.TRENDING_UP
        elif features.trend_direction == "DOWN":
            return MarketRegime.TRENDING_DOWN

    # 3. Volatility Regimes
    if features.is_expanding and features.volatility_zscore > 1.5:
        return MarketRegime.VOLATILITY_EXPANSION
    if features.is_compressing and features.volatility_zscore < -1.0:
        return MarketRegime.VOLATILITY_COMPRESSION

    # 4. High / Low Volatility
    if features.atr_percentile > 0.25:
        return MarketRegime.HIGH_VOLATILITY
    if features.atr_percentile < 0.08:
        return MarketRegime.LOW_VOLATILITY

    # 5. Ranging / Mean Reversion (Default)
    if abs(features.dist_from_vwap_pct) < 0.15 and features.trend_strength < 0.3:
        return MarketRegime.MEAN_REVERSION

    return MarketRegime.RANGING


def are_regimes_compatible(regime_a: MarketRegime, regime_b: MarketRegime) -> bool:
    """
    Determines if two regimes are contextually compatible for historical analog comparison (§10, §11).
    """
    if regime_a == regime_b:
        return True

    compatible_groups = [
        {MarketRegime.TRENDING_UP, MarketRegime.BREAKOUT, MarketRegime.VOLATILITY_EXPANSION},
        {MarketRegime.TRENDING_DOWN, MarketRegime.BREAKOUT, MarketRegime.VOLATILITY_EXPANSION},
        {MarketRegime.RANGING, MarketRegime.MEAN_REVERSION, MarketRegime.LOW_VOLATILITY, MarketRegime.VOLATILITY_COMPRESSION},
        {MarketRegime.HIGH_VOLATILITY, MarketRegime.VOLATILITY_EXPANSION, MarketRegime.BREAKOUT},
    ]

    for group in compatible_groups:
        if regime_a in group and regime_b in group:
            return True

    return False
