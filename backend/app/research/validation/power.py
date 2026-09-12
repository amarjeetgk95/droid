"""Power analysis for 1H forecast v2.3 (P1-3).

Pre-registered Cycle-1 defaults (do NOT tune post-hoc):
    BASELINE_RATE = 0.38
    MDE_ABSOLUTE  = 0.05  (i.e. 0.38 -> 0.43 hit-rate after costs)
    ALPHA = 0.05 (two-sided)
    POWER = 0.8

Formula (one-sample, two-sided proportion z-test, normal approximation):
    H0: p = p0 (baseline_rate)
    H1: p = p1 = p0 + mde_absolute
    Let z_a = Phi^{-1}(1 - alpha/2), z_b = Phi^{-1}(power).
    n = [ z_a * sqrt(p0*(1-p0)) + z_b * sqrt(p1*(1-p1)) ]^2 / mde^2
    required_n = ceil(n)

Notes:
- Pure stdlib math only (statistics.NormalDist for Phi^{-1}); no scipy/sklearn.
- One-sample form is correct here: Cycle-1 tests pooled hit-rate against a
  fixed baseline (naive/buy-hold measured on identical settlement), not a
  two-sample A/B split.
- Two-sample (unpooled) form would be ~2x larger; we document the choice so
  the promotion packet cannot silently swap formulas.
- Known value: baseline 0.38 / MDE 0.05 / alpha 0.05 / power 0.8 -> n = 749
  (exact 748.58 -> ceil 749). Asserted in backend/tests/test_p1_power_calib_costs.py.
"""

from __future__ import annotations

import math
import statistics

# --- Pre-registered Cycle-1 defaults (P1-5 budget references these) ---
BASELINE_RATE: float = 0.38
MDE_ABSOLUTE: float = 0.05
ALPHA: float = 0.05
POWER: float = 0.8


def _z_quantile(p: float) -> float:
    """Inverse standard-normal CDF via stdlib only."""
    if not 0.0 < p < 1.0:
        raise ValueError(f"quantile p must be in (0,1), got {p!r}")
    return statistics.NormalDist().inv_cdf(p)


def required_n(
    baseline_rate: float = BASELINE_RATE,
    mde_absolute: float = MDE_ABSOLUTE,
    alpha: float = ALPHA,
    power: float = POWER,
) -> int:
    """Required pooled n for a two-sided one-sample proportion z-test.

    Args:
        baseline_rate: H0 hit-rate p0 in (0,1).
        mde_absolute: minimum detectable absolute lift, p1 = p0 + mde.
        alpha: two-sided significance level in (0,1).
        power: target power 1-beta in (0,1).

    Returns:
        ceil(n) as int, minimum 1.

    Raises:
        ValueError: on out-of-range inputs or p1 outside (0,1).
    """
    p0 = float(baseline_rate)
    delta = float(mde_absolute)
    a = float(alpha)
    pw = float(power)
    if not 0.0 < p0 < 1.0:
        raise ValueError(f"baseline_rate must be in (0,1), got {baseline_rate!r}")
    if not delta > 0:
        raise ValueError(f"mde_absolute must be > 0, got {mde_absolute!r}")
    p1 = p0 + delta
    if not 0.0 < p1 < 1.0:
        raise ValueError(f"baseline_rate + mde_absolute must be in (0,1), got {p1!r}")
    if not 0.0 < a < 1.0:
        raise ValueError(f"alpha must be in (0,1), got {alpha!r}")
    if not 0.0 < pw < 1.0:
        raise ValueError(f"power must be in (0,1), got {power!r}")
    z_a = _z_quantile(1.0 - a / 2.0)
    z_b = _z_quantile(pw)
    num = z_a * math.sqrt(p0 * (1.0 - p0)) + z_b * math.sqrt(p1 * (1.0 - p1))
    n = (num / delta) ** 2
    return max(1, int(math.ceil(n)))


def cell_status(n: int, required_n: int, contradictory_flag: bool = False) -> str:
    """Per-cell sufficiency label for the walk-forward report.

    - "CONTRADICTORY" if contradictory_flag is True (takes precedence;
      caller sets it when the cell is significantly *worse* than baseline
      or otherwise unsafe — such cells block promotion).
    - "SUFFICIENT" if n >= required_n (and not contradictory).
    - "INSUFFICIENT" otherwise (cells never block promotion on their own).

    Args:
        n: actual cell sample size (>= 0).
        required_n: pooled required n (> 0).
        contradictory_flag: True marks the cell contradictory/unsafe.

    Returns:
        One of "SUFFICIENT" / "INSUFFICIENT" / "CONTRADICTORY".
    """
    if contradictory_flag:
        return "CONTRADICTORY"
    try:
        req = int(required_n)
    except (TypeError, ValueError) as e:
        raise ValueError(f"required_n must be a positive int, got {required_n!r}") from e
    if req <= 0:
        raise ValueError(f"required_n must be > 0, got {required_n!r}")
    try:
        actual = int(n)
    except (TypeError, ValueError) as e:
        raise ValueError(f"n must be a non-negative int, got {n!r}") from e
    if actual < 0:
        raise ValueError(f"n must be >= 0, got {n!r}")
    return "SUFFICIENT" if actual >= req else "INSUFFICIENT"


def power_report(
    n: int,
    baseline_rate: float = BASELINE_RATE,
    mde_absolute: float = MDE_ABSOLUTE,
    alpha: float = ALPHA,
    power: float = POWER,
    contradictory_flag: bool = False,
) -> dict:
    """Convenience bundle for the walk-forward report dict.

    Returns {"n", "required_n", "status", "baseline_rate", "mde_absolute",
    "alpha", "power"}. Pure; never raises on contradictory_flag handling.
    """
    req = required_n(baseline_rate, mde_absolute, alpha, power)
    return {
        "n": int(n),
        "required_n": req,
        "status": cell_status(n, req, contradictory_flag),
        "baseline_rate": float(baseline_rate),
        "mde_absolute": float(mde_absolute),
        "alpha": float(alpha),
        "power": float(power),
    }
