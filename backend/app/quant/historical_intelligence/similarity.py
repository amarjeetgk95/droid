"""
Multi-Metric Similarity Engine — §12, §13
Combines Cosine/Pearson returns, Fast Band-Constrained DTW, Candle Structure, Volatility, Volume, and Trend.
"""
from __future__ import annotations

import math
from app.quant.historical_intelligence.models import NormalizedFeatures, MarketRegime
from app.quant.historical_intelligence.regime_classifier import are_regimes_compatible


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Computes cosine similarity between two float vectors [-1.0, 1.0] -> normalized to [0.0, 1.0]."""
    if len(v1) != len(v2) or not v1:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0.0 or mag2 == 0.0:
        return 0.5
    raw_cos = dot / (mag1 * mag2)
    # Map [-1, 1] -> [0, 1]
    return max(0.0, min(1.0, (raw_cos + 1.0) / 2.0))


def pearson_correlation(v1: list[float], v2: list[float]) -> float:
    """Computes Pearson correlation coefficient between two series [0.0, 1.0]."""
    n = len(v1)
    if n != len(v2) or n < 2:
        return 0.5
    mean1 = sum(v1) / n
    mean2 = sum(v2) / n
    cov = sum((a - mean1) * (b - mean2) for a, b in zip(v1, v2))
    var1 = sum((a - mean1) ** 2 for a in v1)
    var2 = sum((b - mean2) ** 2 for b in v2)
    denom = math.sqrt(var1 * var2)
    if denom == 0.0:
        return 0.5
    raw_r = cov / denom
    return max(0.0, min(1.0, (raw_r + 1.0) / 2.0))


def fast_dtw_similarity(s1: list[float], s2: list[float], window_radius: int = 3) -> float:
    """
    Fast Band-Constrained Dynamic Time Warping (Sakoe-Chiba Band) to handle time-warped patterns efficiently.
    Complexity: O(N * W). Returns normalized similarity [0.0, 1.0].
    """
    n, m = len(s1), len(s2)
    if n == 0 or m == 0:
        return 0.0

    w = max(window_radius, abs(n - m))
    dtw = [[float('inf')] * (m + 1) for _ in range(n + 1)]
    dtw[0][0] = 0.0

    for i in range(1, n + 1):
        for j in range(max(1, i - w), min(m + 1, i + w + 1)):
            cost = abs(s1[i - 1] - s2[j - 1])
            dtw[i][j] = cost + min(dtw[i - 1][j], dtw[i][j - 1], dtw[i - 1][j - 1])

    dist = dtw[n][m]
    # Normalize by path length
    avg_dist = dist / max(1, n + m)
    return max(0.0, min(1.0, 1.0 / (1.0 + avg_dist)))


def compute_composite_similarity(
    current_f: NormalizedFeatures,
    current_regime: MarketRegime,
    candidate_f: NormalizedFeatures,
    candidate_regime: MarketRegime,
) -> tuple[float, dict[str, float]]:
    """
    Computes weighted multi-metric similarity score (§13).
    Weights:
      Price Structure: 30%
      Candle Structure: 15%
      Trend: 15%
      Volatility: 15%
      Volume: 10%
      Regime Compatibility: 15%
    """
    # 1. Price Similarity (Cosine + DTW + Pearson)
    cos_sim = cosine_similarity(current_f.normalized_returns, candidate_f.normalized_returns)
    pear_sim = pearson_correlation(current_f.normalized_returns, candidate_f.normalized_returns)
    dtw_sim = fast_dtw_similarity(current_f.normalized_returns, candidate_f.normalized_returns)
    price_sim = (cos_sim * 0.4) + (pear_sim * 0.3) + (dtw_sim * 0.3)

    # 2. Candle Structure Similarity
    body_diff = abs(current_f.avg_body_pct - candidate_f.avg_body_pct)
    wick_u_diff = abs(current_f.avg_upper_wick_pct - candidate_f.avg_upper_wick_pct)
    wick_l_diff = abs(current_f.avg_lower_wick_pct - candidate_f.avg_lower_wick_pct)
    shape_sim = max(0.0, 1.0 - (body_diff * 0.4 + wick_u_diff * 0.3 + wick_l_diff * 0.3))

    # 3. Trend Similarity
    trend_dir_match = 1.0 if current_f.trend_direction == candidate_f.trend_direction else 0.0
    slope_diff = abs(current_f.ema_slope_short - candidate_f.ema_slope_short)
    slope_sim = max(0.0, 1.0 - min(1.0, slope_diff * 10.0))
    trend_sim = (trend_dir_match * 0.6) + (slope_sim * 0.4)

    # 4. Volatility Similarity
    atr_ratio = min(current_f.atr_percentile, candidate_f.atr_percentile) / max(1e-5, max(current_f.atr_percentile, candidate_f.atr_percentile))
    exp_match = 1.0 if (current_f.is_expanding == candidate_f.is_expanding) else 0.5
    vol_sim = (atr_ratio * 0.7) + (exp_match * 0.3)

    # 5. Volume Similarity
    rvol_ratio = min(current_f.relative_volume, candidate_f.relative_volume) / max(1e-5, max(current_f.relative_volume, candidate_f.relative_volume))
    vol_trend_diff = abs(current_f.volume_trend - candidate_f.volume_trend)
    volume_sim = max(0.0, min(1.0, (rvol_ratio * 0.7) + max(0.0, 1.0 - vol_trend_diff) * 0.3))

    # 6. Regime Similarity
    if current_regime == candidate_regime:
        regime_sim = 1.0
    elif are_regimes_compatible(current_regime, candidate_regime):
        regime_sim = 0.75
    else:
        regime_sim = 0.20

    # Composite Weighted Total (§13)
    composite = (
        price_sim * 0.30 +
        shape_sim * 0.15 +
        trend_sim * 0.15 +
        vol_sim * 0.15 +
        volume_sim * 0.10 +
        regime_sim * 0.15
    )

    component_details = {
        "price_similarity": round(price_sim, 4),
        "shape_similarity": round(shape_sim, 4),
        "trend_similarity": round(trend_sim, 4),
        "volatility_similarity": round(vol_sim, 4),
        "volume_similarity": round(volume_sim, 4),
        "regime_similarity": round(regime_sim, 4),
    }

    return round(composite, 4), component_details
