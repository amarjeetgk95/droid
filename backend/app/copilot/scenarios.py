"""Scenario Engine (spec §8).

Produces the three-way scenario set (Range / Bullish expansion / Bearish
expansion) with deterministic trigger conditions and an ATR-derived expected
range.

Probabilities are ONLY attached when a quantitative model supplied them. With
no calibrated model the API returns `probability: null` + `UNAVAILABLE` — the
LLM is never allowed to fill in numbers here.
"""
from __future__ import annotations

import math

from app.copilot.models import LevelsBlock, MarketContext, Scenario

#: ATR(5m) → horizon ATR scaling: ATR_h ≈ ATR_5m × sqrt(minutes/5).
HORIZON_BARS: dict[str, float] = {
    "NEXT_15_MIN": 3.0,
    "NEXT_60_MIN": 12.0,
    "TODAY": 75.0,
    "NEXT_SESSION": 75.0,
    "SWING_3_5_DAYS": 300.0,
}


def horizon_atr(ctx: MarketContext) -> float | None:
    atr = ctx.technicals.atr
    if not atr or atr <= 0:
        return None
    bars = HORIZON_BARS.get(ctx.horizon, 12.0)
    return round(atr * math.sqrt(bars), 2)


def expected_range(ctx: MarketContext) -> dict[str, float | None]:
    """ATR-derived expected range — a volatility statistic, not a forecast."""
    price = ctx.price.ltp
    atr_h = horizon_atr(ctx)
    if price is None or atr_h is None:
        return {"low": None, "high": None, "basis": "unavailable"}
    return {
        "low": round(price - atr_h, 2),
        "high": round(price + atr_h, 2),
        "basis": f"±1.0×ATR({ctx.horizon}) derived from 5m ATR {ctx.technicals.atr:,.2f}",
    }


def _conditions(levels: LevelsBlock, horizon_label: str) -> dict[str, list[str]]:
    bull = levels.bull_trigger
    bear = levels.bear_trigger
    range_conditions: list[str] = []
    if bear is not None:
        range_conditions.append(f"{bear:,.0f} support holds")
    if bull is not None:
        range_conditions.append(f"{bull:,.0f} resistance holds")
    range_conditions.append(f"no acceptance outside the value area over {horizon_label}")
    bull_conditions = (
        [f"sustained breakout and acceptance above {bull:,.0f}"] if bull is not None else ["no validated resistance level available"]
    )
    bear_conditions = (
        [f"confirmed breakdown and acceptance below {bear:,.0f}"] if bear is not None else ["no validated support level available"]
    )
    return {"RANGE": range_conditions, "BULL_EXPANSION": bull_conditions, "BEAR_EXPANSION": bear_conditions}


def build_scenarios(
    ctx: MarketContext,
    levels: LevelsBlock,
    model_probabilities: dict[str, float | None] | None = None,
    probability_source: str | None = None,
) -> list[Scenario]:
    """Build the scenario set. Probabilities appear only with a quantitative source."""
    horizon_label = ctx.horizon.replace("_", " ").lower()
    conds = _conditions(levels, horizon_label)
    ranges = expected_range(ctx)

    def probability(key: str) -> tuple[float | None, str]:
        if not model_probabilities:
            return None, "UNAVAILABLE"
        value = model_probabilities.get(key)
        if value is None:
            return None, "UNAVAILABLE"
        return round(float(value), 4), "MODEL"

    specs = (
        ("RANGE", "Range-bound", "RANGE"),
        ("BULL_EXPANSION", "Bullish expansion", "BULL"),
        ("BEAR_EXPANSION", "Bearish expansion", "BEAR"),
    )
    scenarios: list[Scenario] = []
    for scenario_id, label, prob_key in specs:
        prob, status = probability(prob_key)
        scenarios.append(
            Scenario(
                id=scenario_id,  # type: ignore[arg-type]
                label=label,
                probability=prob,
                probability_status=status,  # type: ignore[arg-type]
                conditions=conds[scenario_id],
                expected_range=ranges if scenario_id == "RANGE" else None,
            )
        )

    if model_probabilities and probability_source:
        for scenario in scenarios:
            if scenario.probability_status == "MODEL":
                scenario.conditions = list(scenario.conditions) + [f"probability source: {probability_source}"]
    return scenarios


def probability_available(scenarios: list[Scenario]) -> bool:
    return all(s.probability is not None for s in scenarios)
