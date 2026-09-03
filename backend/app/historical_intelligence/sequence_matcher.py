"""
Sequence Similarity & Dynamic Time Warping (DTW) — §23
Matches last N 1-minute candles against historical sequences.
"""
from __future__ import annotations

import math
from app.historical_intelligence.schemas import CandleData


def fast_dtw_similarity(seq1: list[float], seq2: list[float], max_radius: int = 3) -> float:
    """
    Computes Fast Dynamic Time Warping similarity between two normalized price sequences.
    Returns normalized similarity in [0.0, 1.0].
    """
    n, m = len(seq1), len(seq2)
    if n == 0 or m == 0:
        return 0.0

    # Z-normalize both series for shape-only matching
    s1 = _z_score(seq1)
    s2 = _z_score(seq2)

    # Fast Sakoe-Chiba band DTW
    dp = [[float("inf")] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0

    for i in range(1, n + 1):
        j_start = max(1, i - max_radius)
        j_end = min(m, i + max_radius)
        for j in range(j_start, j_end + 1):
            cost = abs(s1[i - 1] - s2[j - 1])
            dp[i][j] = cost + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

    dist = dp[n][m]
    if math.isinf(dist):
        return 0.0

    # Distance to similarity: 1 / (1 + normalized distance)
    avg_dist = dist / max(1, (n + m))
    sim = 1.0 / (1.0 + avg_dist)
    return max(0.0, min(1.0, round(sim, 4)))


def pearson_correlation(seq1: list[float], seq2: list[float]) -> float:
    """Computes Pearson correlation coefficient scaled to [0.0, 1.0]."""
    n = len(seq1)
    if n != len(seq2) or n < 2:
        return 0.0

    mean1 = sum(seq1) / n
    mean2 = sum(seq2) / n

    num = sum((a - mean1) * (b - mean2) for a, b in zip(seq1, seq2))
    den1 = sum((a - mean1) ** 2 for a in seq1)
    den2 = sum((b - mean2) ** 2 for b in seq2)

    if den1 < 1e-12 or den2 < 1e-12:
        return 0.0

    corr = num / math.sqrt(den1 * den2)
    # Scale from [-1, 1] to [0, 1]
    return max(0.0, min(1.0, (corr + 1.0) / 2.0))


def match_candle_sequence(
    query_candles: list[CandleData],
    candidate_candles: list[CandleData],
) -> float:
    """
    Computes hybrid sequence similarity combining closing price trajectory and candle bodies.
    """
    if len(query_candles) != len(candidate_candles) or len(query_candles) < 3:
        return 0.0

    q_closes = [c.close for c in query_candles]
    c_closes = [c.close for c in candidate_candles]

    dtw_sim = fast_dtw_similarity(q_closes, c_closes)
    corr_sim = pearson_correlation(q_closes, c_closes)

    return round((0.6 * dtw_sim) + (0.4 * corr_sim), 4)


def _z_score(seq: list[float]) -> list[float]:
    n = len(seq)
    if n < 2:
        return [0.0] * n
    mean = sum(seq) / n
    var = sum((x - mean) ** 2 for x in seq) / n
    std = math.sqrt(var)
    if std < 1e-9:
        return [0.0] * n
    return [(x - mean) / std for x in seq]
