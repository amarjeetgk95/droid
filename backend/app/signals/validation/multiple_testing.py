"""
Multiple-Testing Protection & Deflated Sharpe Ratio (§42).
Implements the Deflated Sharpe Ratio (DSR) (Bailey & López de Prado, 2014)
to statistically adjust Sharpe ratios for data snooping, number of trials,
sample length, skewness, and kurtosis.
"""
from __future__ import annotations

import math
from typing import Optional
from pydantic import BaseModel


class DSRResult(BaseModel):
    estimated_sharpe: float
    deflated_sharpe_ratio: float      # Statistical probability that SR > 0 after adjusting for multiple tests
    expected_maximum_sharpe: float    # Expected max SR under the null hypothesis (pure noise)
    num_trials: int
    sample_length: int
    is_statistically_significant: bool # True if DSR >= 0.95 (5% significance level)
    haircut_pct: float                # % reduction in observed Sharpe due to selection bias


def compute_expected_max_sharpe(num_trials: int, variance_sharpe: float = 1.0) -> float:
    """
    Approximates E[max(SR)] under the null hypothesis that true SR = 0.
    Using extreme value theory: E[max_N] ≈ sqrt(V) * ((1 - γ) * Z^{-1}(1 - 1/N) + γ * Z^{-1}(1 - 1/(N * e)))
    where γ ≈ 0.5772 (Euler-Mascheroni constant).
    """
    if num_trials <= 1:
        return 0.0
    
    euler_mascheroni = 0.5772156649
    # Standard normal approximation
    z1 = math.sqrt(2.0 * math.log(num_trials))
    if z1 == 0:
        return 0.0
    emax = math.sqrt(variance_sharpe) * (z1 + (euler_mascheroni / z1))
    return max(0.0, emax)


def calculate_deflated_sharpe_ratio(
    observed_sharpe: float,
    num_trials: int,
    sample_length: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    benchmark_sharpe: float = 0.0,
) -> DSRResult:
    """
    Calculates the Deflated Sharpe Ratio (DSR).
    Returns probability that the strategy has genuine predictive power rather than being a selection artifact.
    """
    if sample_length <= 2:
        return DSRResult(
            estimated_sharpe=observed_sharpe,
            deflated_sharpe_ratio=0.0,
            expected_maximum_sharpe=0.0,
            num_trials=num_trials,
            sample_length=sample_length,
            is_statistically_significant=False,
            haircut_pct=100.0,
        )

    # Standard error of Sharpe ratio
    # SE(SR) = sqrt((1 - skew*SR + (kurt - 1)/4 * SR^2) / (T - 1))
    se_numerator = 1.0 - (skewness * observed_sharpe) + ((kurtosis - 1.0) / 4.0) * (observed_sharpe ** 2)
    se_sharpe = math.sqrt(max(1e-6, se_numerator / (sample_length - 1.0)))

    # Expected max SR under null hypothesis of N trials
    emax = compute_expected_max_sharpe(num_trials, variance_sharpe=se_sharpe ** 2)
    threshold = max(benchmark_sharpe, emax)

    # Test statistic Z
    z_score = (observed_sharpe - threshold) / se_sharpe

    # Normal CDF approximation
    dsr_prob = 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))
    dsr_prob = max(0.0, min(1.0, dsr_prob))

    haircut = 0.0
    if observed_sharpe > 0:
        haircut = max(0.0, min(100.0, ((observed_sharpe - max(0.0, observed_sharpe - emax)) / observed_sharpe) * 100.0))

    return DSRResult(
        estimated_sharpe=round(observed_sharpe, 3),
        deflated_sharpe_ratio=round(dsr_prob, 4),
        expected_maximum_sharpe=round(emax, 3),
        num_trials=num_trials,
        sample_length=sample_length,
        is_statistically_significant=(dsr_prob >= 0.95),
        haircut_pct=round(haircut, 1),
    )
