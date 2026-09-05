"""
Statistical Reliability & Empirical Distribution Engine — §§20, 21
Calculates Kish's ESS, Wilson 95% Confidence Intervals, and Minimum Sample Policy.
"""
from __future__ import annotations

import math
from typing import Sequence
from app.historical_intelligence.schemas import (
    ConfidenceInterval,
    HorizonStatistics,
    HistoricalAnalogMatch,
    SampleReliability,
)


def calculate_wilson_ci(successes: int, total: int, z: float = 1.96) -> ConfidenceInterval:
    """
    Wilson Score Interval for binomial proportions (guarantees robust coverage even with small N).
    """
    if total <= 0:
        return ConfidenceInterval(lower=0.0, upper=1.0, point_estimate=0.0)

    p_hat = successes / total
    denom = 1.0 + (z * z) / total
    centre = (p_hat + (z * z) / (2.0 * total)) / denom
    margin = (z * math.sqrt((p_hat * (1.0 - p_hat) / total) + ((z * z) / (4.0 * total * total)))) / denom

    lower = max(0.0, min(1.0, centre - margin))
    upper = max(0.0, min(1.0, centre + margin))

    return ConfidenceInterval(
        lower=round(lower, 4),
        upper=round(upper, 4),
        point_estimate=round(p_hat, 4),
        confidence_level=0.95,
    )


def calculate_effective_sample_size(weights: Sequence[float]) -> float:
    """
    Kish's Effective Sample Size: ESS = (sum(w))^2 / sum(w^2).
    """
    if not weights:
        return 0.0
    sum_w = sum(weights)
    sum_sq_w = sum(w * w for w in weights)
    if sum_sq_w < 1e-12:
        return 0.0
    return round((sum_w * sum_w) / sum_sq_w, 2)


def classify_sample_reliability(sample_count: int) -> SampleReliability:
    """Classifies sample reliability according to §21 Minimum Sample Policy."""
    if sample_count < 10:
        return SampleReliability.INSUFFICIENT
    elif sample_count <= 24:
        return SampleReliability.LOW_CONFIDENCE
    elif sample_count <= 49:
        return SampleReliability.MODERATE
    elif sample_count <= 99:
        return SampleReliability.GOOD
    else:
        return SampleReliability.HIGH_SAMPLE


def compute_horizon_statistics(
    analogs: list[HistoricalAnalogMatch],
    horizon_minutes: int,
) -> HorizonStatistics:
    """
    Aggregates outcomes for a specific forward horizon (15m, 30m, 60m).
    """
    n = len(analogs)
    if n == 0:
        return HorizonStatistics(
            horizon_minutes=horizon_minutes,
            bullish_probability=0.33,
            bearish_probability=0.33,
            neutral_probability=0.34,
            continuation_probability=0.0,
            failure_probability=0.0,
            reversal_probability=0.0,
            median_return=0.0,
            mean_return=0.0,
            median_mfe=0.0,
            median_mae=0.0,
            target_hit_rate=0.0,
            stop_hit_rate=0.0,
            median_duration=None,
            confidence_interval_bullish=ConfidenceInterval(lower=0.0, upper=1.0, point_estimate=0.33),
        )

    # Extract horizon slice
    if horizon_minutes == 15:
        outcomes_with_weights = [(a, a.similarity_score * a.temporal_weight, a.outcome_15m) for a in analogs if a.outcome_15m is not None]
    elif horizon_minutes == 30:
        outcomes_with_weights = [(a, a.similarity_score * a.temporal_weight, a.outcome_30m) for a in analogs if a.outcome_30m is not None]
    else:
        outcomes_with_weights = [(a, a.similarity_score * a.temporal_weight, a.outcome_60m) for a in analogs if a.outcome_60m is not None]

    if not outcomes_with_weights:
        return HorizonStatistics(
            horizon_minutes=horizon_minutes,
            bullish_probability=0.33,
            bearish_probability=0.33,
            neutral_probability=0.34,
            continuation_probability=0.0,
            failure_probability=0.0,
            reversal_probability=0.0,
            median_return_pct=0.0,
            mean_return_pct=0.0,
            iqr_return_pct=0.0,
            median_mfe_pct=0.0,
            median_mae_pct=0.0,
            target_hit_rate=0.0,
            stop_hit_rate=0.0,
            median_duration=None,
            confidence_interval_bullish=ConfidenceInterval(lower=0.0, upper=1.0, point_estimate=0.33),
        )

    n_valid = len(outcomes_with_weights)
    total_w = sum(w for _, w, _ in outcomes_with_weights) or 1.0

    bull_w = sum(w for _, w, out in outcomes_with_weights if out.direction == "BULLISH")
    bear_w = sum(w for _, w, out in outcomes_with_weights if out.direction == "BEARISH")
    neut_w = sum(w for _, w, out in outcomes_with_weights if out.direction == "NEUTRAL")

    bull_prob = bull_w / total_w
    bear_prob = bear_w / total_w
    neut_prob = neut_w / total_w

    cont_w = sum(w for _, w, out in outcomes_with_weights if out.continuation)
    fail_w = sum(w for _, w, out in outcomes_with_weights if out.failure)
    rev_w = sum(w for _, w, out in outcomes_with_weights if out.reversal)

    outcomes = [out for _, _, out in outcomes_with_weights]
    # Excursions & Returns
    rets = sorted(out.return_pct for out in outcomes)
    mfes = sorted(out.mfe_pct for out in outcomes)
    maes = sorted(out.mae_pct for out in outcomes)

    med_ret = _median(rets)
    mean_ret = sum(rets) / n_valid
    med_mfe = _median(mfes)
    med_mae = _median(maes)

    tgt_hits = sum(1 for out in outcomes if out.target_hit)
    stop_hits = sum(1 for out in outcomes if out.stop_hit)

    durations = [out.duration_bars for out in outcomes if out.duration_bars is not None]
    med_dur = _median(sorted(durations)) if durations else None

    # Wilson CI for Bullish %
    raw_bull_count = sum(1 for out in outcomes if out.direction == "BULLISH")
    wilson_ci = calculate_wilson_ci(raw_bull_count, n_valid)

    return HorizonStatistics(
        horizon_minutes=horizon_minutes,
        bullish_probability=round(bull_prob, 4),
        bearish_probability=round(bear_prob, 4),
        neutral_probability=round(neut_prob, 4),
        continuation_probability=round(cont_w / total_w, 4),
        failure_probability=round(fail_w / total_w, 4),
        reversal_probability=round(rev_w / total_w, 4),
        median_return=round(med_ret, 4),
        mean_return=round(mean_ret, 4),
        median_mfe=round(med_mfe, 4),
        median_mae=round(med_mae, 4),
        target_hit_rate=round(tgt_hits / n, 4),
        stop_hit_rate=round(stop_hits / n, 4),
        median_duration=round(med_dur, 1) if med_dur is not None else None,
        confidence_interval_bullish=wilson_ci,
    )


def _median(sorted_seq: list[float]) -> float:
    if not sorted_seq:
        return 0.0
    k = len(sorted_seq)
    mid = k // 2
    if k % 2 == 1:
        return sorted_seq[mid]
    return (sorted_seq[mid - 1] + sorted_seq[mid]) / 2.0
