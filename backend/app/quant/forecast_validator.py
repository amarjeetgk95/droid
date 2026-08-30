"""
TSFM Forecast Validator — §5

Validates probabilistic forecasts BEFORE downstream processing.
Implements exact checks from spec:

    P10 < P50 < P90
    P10 > 0
    all values finite
    no NaN
    no Inf
    valid forecast horizon
    valid current price

Never silently repairs invalid quantiles for execution.
A sorted/clipped version may be stored ONLY for diagnostic visualization;
original invalid forecast must remain flagged as invalid.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ForecastInvalidReason(str, Enum):
    NOT_FINITE_P10 = "NOT_FINITE_P10"
    NOT_FINITE_P50 = "NOT_FINITE_P50"
    NOT_FINITE_P90 = "NOT_FINITE_P90"
    P10_NON_POSITIVE = "P10_NON_POSITIVE"
    P10_NOT_LESS_P50 = "P10_NOT_LESS_P50"
    P50_NOT_LESS_P90 = "P50_NOT_LESS_P90"
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_HORIZON = "INVALID_HORIZON"
    INVALID_CURRENT_PRICE = "INVALID_CURRENT_PRICE"
    NOT_FINITE_PRICE = "NOT_FINITE_PRICE"


@dataclass
class ForecastValidationResult:
    valid: bool
    reason: ForecastInvalidReason | None = None
    detail: str | None = None
    # Diagnostic-only clipped/sorted view — NEVER use for execution
    diagnostic_sorted: dict[str, float] | None = None


def validate_tsfm_forecast(
    p10: Any,
    p50: Any,
    p90: Any,
    current_price: Any | None = None,
    horizon_minutes: Any | None = None,
) -> ForecastValidationResult:
    """
    Validate TSFM forecast per §5 spec.

    Implementation mirrors spec pseudocode verbatim:

        if not np.isfinite(p10): reject
        if not np.isfinite(p50): reject
        if not np.isfinite(p90): reject
        if p10 <= 0: reject
        if not (p10 < p50 < p90): reject
    """
    # Check missing
    if p10 is None:
        return ForecastValidationResult(valid=False, reason=ForecastInvalidReason.MISSING_FIELD, detail="p10 missing")
    if p50 is None:
        return ForecastValidationResult(valid=False, reason=ForecastInvalidReason.MISSING_FIELD, detail="p50 missing")
    if p90 is None:
        return ForecastValidationResult(valid=False, reason=ForecastInvalidReason.MISSING_FIELD, detail="p90 missing")

    # Type coercion attempt — but strictly validate finite numeric
    try:
        p10_f = float(p10)
        p50_f = float(p50)
        p90_f = float(p90)
    except Exception as e:
        return ForecastValidationResult(valid=False, reason=ForecastInvalidReason.NOT_FINITE_P10, detail=f"non-numeric quantile: {e}")

    # Finite checks (covers NaN, Inf, -Inf)
    if not math.isfinite(p10_f):
        return ForecastValidationResult(valid=False, reason=ForecastInvalidReason.NOT_FINITE_P10, detail=f"p10 not finite: {p10_f}")
    if not math.isfinite(p50_f):
        return ForecastValidationResult(valid=False, reason=ForecastInvalidReason.NOT_FINITE_P50, detail=f"p50 not finite: {p50_f}")
    if not math.isfinite(p90_f):
        return ForecastValidationResult(valid=False, reason=ForecastInvalidReason.NOT_FINITE_P90, detail=f"p90 not finite: {p90_f}")

    # P10 > 0
    if p10_f <= 0:
        return ForecastValidationResult(valid=False, reason=ForecastInvalidReason.P10_NON_POSITIVE, detail=f"p10 <=0: {p10_f}")

    # Strict ordering
    if not (p10_f < p50_f):
        return ForecastValidationResult(
            valid=False,
            reason=ForecastInvalidReason.P10_NOT_LESS_P50,
            detail=f"p10 ({p10_f}) not < p50 ({p50_f})",
            diagnostic_sorted=_diagnostic_sorted(p10_f, p50_f, p90_f),
        )
    if not (p50_f < p90_f):
        return ForecastValidationResult(
            valid=False,
            reason=ForecastInvalidReason.P50_NOT_LESS_P90,
            detail=f"p50 ({p50_f}) not < p90 ({p90_f})",
            diagnostic_sorted=_diagnostic_sorted(p10_f, p50_f, p90_f),
        )

    # Optional horizon validation (if provided)
    if horizon_minutes is not None:
        try:
            h = int(horizon_minutes)
            if h <= 0 or h > 10080:  # up to 1 week
                return ForecastValidationResult(valid=False, reason=ForecastInvalidReason.INVALID_HORIZON, detail=f"horizon {h} out of range (1-10080)")
        except Exception:
            return ForecastValidationResult(valid=False, reason=ForecastInvalidReason.INVALID_HORIZON, detail=f"horizon not int: {horizon_minutes}")

    # Optional current price validation
    if current_price is not None:
        try:
            cp = float(current_price)
            if not math.isfinite(cp) or cp <= 0:
                return ForecastValidationResult(valid=False, reason=ForecastInvalidReason.INVALID_CURRENT_PRICE, detail=f"current_price invalid: {current_price}")
        except Exception:
            return ForecastValidationResult(valid=False, reason=ForecastInvalidReason.NOT_FINITE_PRICE, detail=f"current_price non-numeric: {current_price}")

    return ForecastValidationResult(valid=True, detail="forecast valid")


def _diagnostic_sorted(p10: float, p50: float, p90: float) -> dict[str, float]:
    vals = sorted([p10, p50, p90])
    # Clipped at 0
    vals = [max(0.01, v) for v in vals]
    return {"p10": vals[0], "p50": vals[1], "p90": vals[2]}


def validate_forecast_dict(forecast: dict, current_price: float | None = None) -> ForecastValidationResult:
    """Convenience wrapper for dict with keys p10/p50/p90 or P10/P50/P90."""
    p10 = forecast.get("p10", forecast.get("P10", forecast.get("low")))
    p50 = forecast.get("p50", forecast.get("P50", forecast.get("mid")))
    p90 = forecast.get("p90", forecast.get("P90", forecast.get("high")))
    # Also support expected_range low/high as p10/p90 approximation? No – require explicit
    # If forecast uses expected_range, extract but still validate strict
    if p10 is None and "expected_range" in forecast:
        er = forecast["expected_range"]
        p10 = er.get("low")
        p90 = er.get("high")
        p50 = forecast.get("expected_move_points", 0)  # not valid, will fail correctly
        # Better to fail missing than guess
        if p50 == 0:
            p50 = None
    horizon = forecast.get("horizon_minutes", forecast.get("horizon"))
    return validate_tsfm_forecast(p10, p50, p90, current_price=current_price, horizon_minutes=horizon)


def reject_forecast(reason: ForecastInvalidReason, detail: str = "") -> None:
    """Helper that raises ValueError – used for strict enforcement."""
    raise ValueError(f"INVALID_FORECAST {reason.value}: {detail}")
