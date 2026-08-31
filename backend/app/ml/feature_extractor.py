import math
from typing import NamedTuple, Any
from app.models.regime import TechnicalIndicators, KeyLevelsModel
from app.models.options import OptionsAnalytics, MaxPainResult


class MLFeatures(NamedTuple):
    rsi_norm: float          # Normalized around 50 (-1.0 to 1.0)
    adx_strength: float      # 0 to 1.0
    supertrend_signal: float # +1.0 (bullish), -1.0 (bearish)
    bollinger_pct_b: float   # 0 to 1.0
    pcr_oi_deviation: float  # Deviation from 1.0 (-1.0 to 1.0)
    max_pain_distance_pct: float # (Spot - MaxPain) / Spot
    futures_basis_pct: float     # Basis / Spot
    price_above_ema20: float     # (Spot - EMA20) / Spot
    price_above_sma200: float    # (Spot - SMA200) / Spot
    pivot_position: float        # Position relative to Pivot Point (-1.0 below S1, +1.0 above R1)


def extract_ml_feature_vector(
    spot_price: float,
    indicators: TechnicalIndicators,
    key_levels: KeyLevelsModel | None,
    options_analytics: OptionsAnalytics | None,
    max_pain: MaxPainResult | None,
    term_structure: Any | None = None,
) -> MLFeatures:
    """Extract normalized feature vector for quantitative ML prediction."""
    # 1. RSI Normalization (-1 to +1)
    rsi_norm = (indicators.rsi_14 - 50.0) / 50.0

    # 2. ADX Trend Strength (0 to 1)
    adx_strength = min(1.0, max(0.0, indicators.adx_14 / 50.0))

    # 3. Supertrend Signal
    st_sig = 1.0 if indicators.supertrend_direction == "BULLISH" else -1.0

    # 4. Bollinger %B
    band_width = max(1.0, indicators.bollinger_upper - indicators.bollinger_lower)
    pct_b = (spot_price - indicators.bollinger_lower) / band_width
    pct_b_clamped = min(1.5, max(-0.5, pct_b))

    # 5. PCR OI Deviation (-1 to +1)
    pcr = options_analytics.pcr_oi if options_analytics else 1.0
    pcr_dev = min(1.0, max(-1.0, (pcr - 1.0) / 0.5))

    # 6. Max Pain Distance %
    mp_strike = max_pain.max_pain_strike if max_pain else spot_price
    mp_dist_pct = (spot_price - mp_strike) / max(1.0, spot_price)

    # 7. Futures Basis %
    near_basis = term_structure.contracts[0].basis if term_structure and term_structure.contracts else 0.0
    basis_pct = near_basis / max(1.0, spot_price)

    # 8. EMAs
    ema20 = indicators.ema_20 if indicators.ema_20 is not None else spot_price
    sma200 = indicators.sma_200 if indicators.sma_200 is not None else spot_price
    above_ema20 = (spot_price - ema20) / max(1.0, spot_price)
    above_sma200 = (spot_price - sma200) / max(1.0, spot_price)

    # 9. Pivot Position
    pivot_pos = 0.0
    if key_levels and key_levels.classic_pivots:
        pp = key_levels.classic_pivots.pivot
        r1 = key_levels.classic_pivots.r1
        s1 = key_levels.classic_pivots.s1
        if spot_price > pp:
            pivot_pos = min(1.0, (spot_price - pp) / max(1.0, r1 - pp))
        else:
            pivot_pos = max(-1.0, (spot_price - pp) / max(1.0, pp - s1))

    return MLFeatures(
        rsi_norm=round(rsi_norm, 4),
        adx_strength=round(adx_strength, 4),
        supertrend_signal=round(st_sig, 4),
        bollinger_pct_b=round(pct_b_clamped, 4),
        pcr_oi_deviation=round(pcr_dev, 4),
        max_pain_distance_pct=round(mp_dist_pct, 4),
        futures_basis_pct=round(basis_pct, 4),
        price_above_ema20=round(above_ema20, 4),
        price_above_sma200=round(above_sma200, 4),
        pivot_position=round(pivot_pos, 4),
    )
