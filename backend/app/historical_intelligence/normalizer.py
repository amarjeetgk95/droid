"""
State Normalization & Volatility Scaling Engine — §6
"""
from __future__ import annotations

import math
from app.historical_intelligence.schemas import (
    CanonicalFeatureVector,
    NormalizedFeatureVector,
)
from app.historical_intelligence.versioning import NORMALIZATION_VERSION


# Canonical feature ordering to guarantee fixed-dimension dense vector
ORDERED_FEATURE_KEYS: list[str] = [
    # Price
    "price_returns_norm",
    "price_log_returns_norm",
    "price_gap_norm",
    "price_accel_norm",
    "price_vwap_dist_norm",
    # Candle
    "candle_range_norm",
    "candle_body_norm",
    "candle_body_to_range",
    "candle_close_location",
    "candle_compression",
    # Structure
    "struct_is_hh",
    "struct_is_hl",
    "struct_is_lh",
    "struct_is_ll",
    "struct_consolidation",
    "struct_breakout_dist_norm",
    # Trend
    "trend_ema_slope_norm",
    "trend_adx_norm",
    "trend_rsi_norm",
    "trend_macd_norm",
    "trend_momentum_accel",
    # Volume & Volatility
    "vol_relative_volume",
    "vol_percentile_norm",
    "vol_accel_norm",
    "vol_atr_norm",
    "vol_realized_vol_norm",
    "vol_vix_norm",
    "vol_iv_norm",
    # Futures
    "fut_basis_norm",
    "fut_oi_norm",
    "fut_oi_change_norm",
    "fut_price_oi_div_norm",
    # Options
    "opt_pcr_oi_norm",
    "opt_pcr_vol_norm",
    "opt_atm_iv_norm",
    "opt_iv_skew_norm",
    "opt_atm_pressure_norm",
    # Context
    "ctx_breadth_norm",
    "ctx_dist_support_norm",
    "ctx_dist_resistance_norm",
    "ctx_data_quality",
]


def clamp(val: float, low: float = -5.0, high: float = 5.0) -> float:
    if math.isnan(val) or math.isinf(val):
        return 0.0
    return max(low, min(high, val))


def normalize_features(
    raw_vector: CanonicalFeatureVector,
    baseline_atr: float | None = None,
    baseline_volume: float | None = None,
    baseline_oi: float | None = None,
) -> NormalizedFeatureVector:
    """
    Transforms raw multi-domain market features into a normalized, volatility-scaled representation.
    Guarantees comparability across regimes, volatility spikes, and asset price levels.
    """
    atr = max(0.5, raw_vector.volume_vol.atr if raw_vector.volume_vol.atr > 0 else (baseline_atr or 20.0))
    realized_vol = max(1.0, raw_vector.volume_vol.realized_volatility)
    vix = max(8.0, raw_vector.volume_vol.vix)

    norm_dict: dict[str, float] = {}

    # 1. Price Normalized by Volatility / ATR
    norm_dict["price_returns_norm"] = clamp(raw_vector.price.returns / (realized_vol / 15.0))
    norm_dict["price_log_returns_norm"] = clamp(raw_vector.price.log_returns / (realized_vol / 15.0))
    norm_dict["price_gap_norm"] = clamp(raw_vector.price.gap / atr)
    norm_dict["price_accel_norm"] = clamp(raw_vector.price.acceleration / atr)
    norm_dict["price_vwap_dist_norm"] = clamp(raw_vector.price.vwap_distance / atr)

    # 2. Candle Dynamics
    norm_dict["candle_range_norm"] = clamp(raw_vector.candle.range_pts / atr, 0.0, 5.0)
    norm_dict["candle_body_norm"] = clamp(raw_vector.candle.body / atr, 0.0, 5.0)
    norm_dict["candle_body_to_range"] = clamp(raw_vector.candle.body_to_range, 0.0, 1.0)
    norm_dict["candle_close_location"] = clamp(raw_vector.candle.close_location, 0.0, 1.0)
    norm_dict["candle_compression"] = clamp(raw_vector.candle.compression, 0.0, 2.0)

    # 3. Market Structure
    norm_dict["struct_is_hh"] = 1.0 if raw_vector.structure.is_hh else 0.0
    norm_dict["struct_is_hl"] = 1.0 if raw_vector.structure.is_hl else 0.0
    norm_dict["struct_is_lh"] = 1.0 if raw_vector.structure.is_lh else 0.0
    norm_dict["struct_is_ll"] = 1.0 if raw_vector.structure.is_ll else 0.0
    norm_dict["struct_consolidation"] = 1.0 if raw_vector.structure.consolidation else 0.0
    norm_dict["struct_breakout_dist_norm"] = clamp(raw_vector.structure.breakout_distance / atr)

    # 4. Trend & Momentum
    norm_dict["trend_ema_slope_norm"] = clamp(raw_vector.trend.ema_slope / atr)
    norm_dict["trend_adx_norm"] = clamp((raw_vector.trend.adx - 25.0) / 25.0, -1.0, 1.0)
    norm_dict["trend_rsi_norm"] = clamp((raw_vector.trend.rsi - 50.0) / 25.0, -2.0, 2.0)
    norm_dict["trend_macd_norm"] = clamp(raw_vector.trend.macd / atr)
    norm_dict["trend_momentum_accel"] = clamp(raw_vector.trend.momentum_accel / atr)

    # 5. Volume & Volatility
    norm_dict["vol_relative_volume"] = clamp(raw_vector.volume_vol.relative_volume - 1.0, -1.0, 4.0)
    norm_dict["vol_percentile_norm"] = clamp((raw_vector.volume_vol.volume_percentile - 50.0) / 25.0, -2.0, 2.0)
    norm_dict["vol_accel_norm"] = clamp(raw_vector.volume_vol.volume_acceleration, -3.0, 3.0)
    norm_dict["vol_atr_norm"] = clamp((atr - (baseline_atr or atr)) / (baseline_atr or atr or 1.0), -2.0, 3.0)
    norm_dict["vol_realized_vol_norm"] = clamp((realized_vol - 15.0) / 10.0, -1.5, 3.0)
    norm_dict["vol_vix_norm"] = clamp((vix - 15.0) / 8.0, -1.5, 3.0)
    norm_dict["vol_iv_norm"] = clamp((raw_vector.volume_vol.iv - 16.0) / 10.0, -1.5, 3.0)

    # 6. Futures Buildup & Basis
    norm_dict["fut_basis_norm"] = clamp(raw_vector.futures.basis / atr)
    base_oi = baseline_oi or max(1000.0, raw_vector.futures.oi)
    norm_dict["fut_oi_norm"] = clamp(math.log10(max(10.0, raw_vector.futures.oi)) / 7.0, 0.0, 2.0)
    norm_dict["fut_oi_change_norm"] = clamp(raw_vector.futures.oi_change / base_oi * 10.0, -3.0, 3.0)
    norm_dict["fut_price_oi_div_norm"] = clamp(raw_vector.futures.price_oi_divergence, -2.0, 2.0)

    # 7. Options Greeks & Structure
    norm_dict["opt_pcr_oi_norm"] = clamp((raw_vector.options.pcr_oi - 1.0) / 0.5, -2.0, 2.0)
    norm_dict["opt_pcr_vol_norm"] = clamp((raw_vector.options.pcr_volume - 1.0) / 0.5, -2.0, 2.0)
    norm_dict["opt_atm_iv_norm"] = clamp((raw_vector.options.atm_iv - 15.0) / 8.0, -1.5, 3.0)
    norm_dict["opt_iv_skew_norm"] = clamp(raw_vector.options.iv_skew / 5.0, -2.0, 2.0)
    norm_dict["opt_atm_pressure_norm"] = clamp(raw_vector.options.atm_pressure, -2.0, 2.0)

    # 8. Context & S/R
    norm_dict["ctx_breadth_norm"] = clamp(raw_vector.market_context.breadth, -1.0, 1.0)
    norm_dict["ctx_dist_support_norm"] = clamp(raw_vector.market_context.distance_to_support / atr, 0.0, 5.0)
    norm_dict["ctx_dist_resistance_norm"] = clamp(raw_vector.market_context.distance_to_resistance / atr, 0.0, 5.0)
    norm_dict["ctx_data_quality"] = clamp(raw_vector.market_context.data_quality_score, 0.0, 1.0)

    # Construct the fixed dense vector
    dense = [round(norm_dict.get(k, 0.0), 6) for k in ORDERED_FEATURE_KEYS]

    return NormalizedFeatureVector(
        normalized_dict=norm_dict,
        dense_vector=dense,
        norm_version=NORMALIZATION_VERSION,
    )
