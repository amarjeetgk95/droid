"""DROID MACD + Fisher-9 Exhaustion Research — Statistical Power Analysis Framework.

Specification Reference: §57.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal
from scipy.stats import norm


PowerCategory = Literal[
    "ADEQUATELY_POWERED",
    "MARGINALLY_POWERED",
    "UNDERPOWERED",
    "SEVERELY_UNDERPOWERED",
    "INSUFFICIENT_SAMPLE",
]


@dataclass(frozen=True)
class PowerResult:
    """Power analysis evaluation for an experiment."""
    effect_size: float
    baseline_std: float
    alpha: float
    target_power: float
    required_n: int
    available_n_eff: int
    observed_power: float
    category: PowerCategory
    is_reportable: bool
    warning_message: str | None


def calculate_required_n(
    effect_size: float = 0.15,
    baseline_std: float = 1.0,
    alpha: float = 0.05,
    power: float = 0.80,
) -> int:
    """Calculate required sample size for two-sided test.

    Formula (§57):
      z_alpha = norm.ppf(1 - alpha / 2)
      z_beta = norm.ppf(power)
      n = ((z_alpha + z_beta) * baseline_std / effect_size) ** 2
    """
    if effect_size <= 0:
        raise ValueError("effect_size must be positive")
    if baseline_std <= 0:
        raise ValueError("baseline_std must be positive")

    z_alpha = norm.ppf(1.0 - alpha / 2.0)
    z_beta = norm.ppf(power)
    n = ((z_alpha + z_beta) * baseline_std / effect_size) ** 2
    return int(math.ceil(n))


def calculate_observed_power(
    observed_effect: float,
    baseline_std: float,
    n_eff: int,
    alpha: float = 0.05,
) -> float:
    """Calculate post-hoc power given observed sample and effect.

    Observed Power (§57):
      z_alpha = norm.ppf(1 - alpha / 2)
      delta = abs(observed_effect) / (baseline_std / sqrt(n_eff))
      power = 1 - norm.cdf(z_alpha - delta) + norm.cdf(-z_alpha - delta)
    """
    if n_eff <= 1 or baseline_std <= 0:
        return 0.0

    se = baseline_std / math.sqrt(n_eff)
    z_alpha = norm.ppf(1.0 - alpha / 2.0)
    delta = abs(observed_effect) / se

    # Two-sided power
    power = float(1.0 - norm.cdf(z_alpha - delta) + norm.cdf(-z_alpha - delta))
    return min(1.0, max(0.0, power))


def evaluate_power(
    available_n_eff: int,
    effect_size: float = 0.15,
    baseline_std: float = 1.0,
    alpha: float = 0.05,
    target_power: float = 0.80,
) -> PowerResult:
    """Evaluate power category and reportability per §57."""
    req_n = calculate_required_n(
        effect_size=effect_size,
        baseline_std=baseline_std,
        alpha=alpha,
        power=target_power,
    )

    observed_power = calculate_observed_power(
        observed_effect=effect_size,
        baseline_std=baseline_std,
        n_eff=available_n_eff,
        alpha=alpha,
    )

    # Minimum reporting threshold: n_eff < 20 must not be reported as findings
    if available_n_eff < 20:
        return PowerResult(
            effect_size=effect_size,
            baseline_std=baseline_std,
            alpha=alpha,
            target_power=target_power,
            required_n=req_n,
            available_n_eff=available_n_eff,
            observed_power=observed_power,
            category="INSUFFICIENT_SAMPLE",
            is_reportable=False,
            warning_message="INSUFFICIENT_SAMPLE: n_eff < 20. Cannot draw research conclusions.",
        )

    ratio = available_n_eff / req_n
    if ratio >= 1.0:
        cat: PowerCategory = "ADEQUATELY_POWERED"
        msg = None
    elif ratio >= 0.50:
        cat = "MARGINALLY_POWERED"
        msg = "MARGINALLY_POWERED: Null results may represent false negatives (beta error)."
    elif ratio >= 0.25:
        cat = "UNDERPOWERED"
        msg = "UNDERPOWERED: Insufficient events to detect effect with target power. Null results not trustworthy."
    else:
        cat = "SEVERELY_UNDERPOWERED"
        msg = "SEVERELY_UNDERPOWERED: Do not draw conclusions. Extend data range or pool timeframes."

    return PowerResult(
        effect_size=effect_size,
        baseline_std=baseline_std,
        alpha=alpha,
        target_power=target_power,
        required_n=req_n,
        available_n_eff=available_n_eff,
        observed_power=observed_power,
        category=cat,
        is_reportable=True,
        warning_message=msg,
    )
