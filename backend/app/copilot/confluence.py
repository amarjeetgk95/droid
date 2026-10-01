"""Confluence Engine (spec §7).

Aggregates factors into ONE canonical directional state. It never forces a
direction: weak or conflicting evidence yields NEUTRAL / NO_SIGNAL, and the
conflicting factors are reported verbatim so the LLM can explain them.
"""
from __future__ import annotations

from itertools import combinations

from app.copilot.enums import DIRECTION_SIGN, FACTOR_LABELS
from app.copilot.models import ConfluenceResult, Factor

#: Domain weights — trend/momentum dominate, liquidity is context only.
FACTOR_WEIGHTS: dict[str, float] = {
    "trend": 1.3,
    "momentum": 1.1,
    "market_structure": 1.0,
    "options_positioning": 0.9,
    "futures_positioning": 0.8,
    "breakout_pressure": 0.7,
    "institutional_flow": 0.7,
    "mean_reversion_pressure": 0.6,
    "volatility": 0.4,
    "liquidity": 0.2,
}

#: Minimum directional evidence before a bias may be published at all.
MIN_USABLE_FACTORS = 3
MIN_TOTAL_WEIGHT = 1.8


def _label_for(ds: float, confluence: float, insufficient: bool, conflicts: list[str]) -> str:
    if insufficient:
        return "INSUFFICIENT EVIDENCE"
    if ds >= 0.55:
        return "STRONG BULLISH PRESSURE" if ds >= 0.75 else "MODERATE BULLISH PRESSURE"
    if ds <= -0.55:
        return "STRONG BEARISH PRESSURE" if ds <= -0.75 else "MODERATE BEARISH PRESSURE"
    if abs(ds) >= 0.3:
        return "MILD BULLISH LEAN" if ds > 0 else "MILD BEARISH LEAN"
    if confluence < 0.5 or conflicts:
        return "NO HIGH-CONVICTION DIRECTIONAL SETUP"
    return "BALANCED / RANGE CONDITIONS"


def _state_for(ds: float, confluence: float, insufficient: bool, conflicts: list[str]) -> str:
    if insufficient:
        return "NO_SIGNAL"
    if abs(ds) >= 0.55 and confluence >= 0.6:
        return "BULLISH" if ds > 0 else "BEARISH"
    if abs(ds) >= 0.3:
        return "MILD_BULLISH" if ds > 0 else "MILD_BEARISH"
    if abs(ds) >= 0.15:
        # A weak lean without agreement must never render as a directional badge.
        return "NEUTRAL"
    if conflicts and abs(ds) >= 0.25:
        return "NEUTRAL"
    return "NEUTRAL"


def detect_conflicts(factors: dict[str, Factor]) -> list[str]:
    conflicts: list[str] = []
    directional = {
        key: factor
        for key, factor in factors.items()
        if factor.state in ("BULLISH", "BEARISH") and factor.strength >= 0.25
    }
    for (key_a, a), (key_b, b) in combinations(directional.items(), 2):
        if a.state == b.state:
            continue
        stronger, weaker = (a, b) if a.strength >= b.strength else (b, a)
        strong_key = key_a if stronger is a else key_b
        weak_key = key_b if stronger is a else key_a
        evidence = (weaker.evidence[0] if weaker.evidence else weaker.state).rstrip(".")
        conflicts.append(
            f"{FACTOR_LABELS.get(strong_key, strong_key)} {stronger.state} "
            f"({stronger.strength:.2f}) vs {FACTOR_LABELS.get(weak_key, weak_key)} {weaker.state} "
            f"({weaker.strength:.2f}) — {evidence}"
        )
    return conflicts


def evaluate_confluence(factors: dict[str, Factor]) -> ConfluenceResult:
    counts = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0, "UNKNOWN": 0}
    for factor in factors.values():
        counts[factor.state if factor.state in counts else "UNKNOWN"] += 1

    usable: dict[str, Factor] = {}
    for key, factor in factors.items():
        if factor.state in ("BULLISH", "BEARISH") and factor.strength > 0:
            usable[key] = factor

    conflicts = detect_conflicts(factors)

    total_weight = sum(FACTOR_WEIGHTS.get(key, 0.5) for key in usable)
    insufficient = len(usable) < MIN_USABLE_FACTORS or total_weight < MIN_TOTAL_WEIGHT

    if total_weight <= 0:
        ds = 0.0
        confluence = 0.0
    else:
        ds = sum(
            DIRECTION_SIGN.get(factor.state, 0.0) * factor.strength * FACTOR_WEIGHTS.get(key, 0.5)
            for key, factor in usable.items()
        ) / total_weight
        direction = 1.0 if ds >= 0 else -1.0
        agreeing = sum(
            FACTOR_WEIGHTS.get(key, 0.5)
            for key, factor in usable.items()
            if DIRECTION_SIGN.get(factor.state, 0.0) * direction > 0
        )
        confluence = agreeing / total_weight

    dominant = _state_for(ds, confluence, insufficient, conflicts)
    return ConfluenceResult(
        dominant_state=dominant,  # type: ignore[arg-type]
        directional_strength=round(ds, 4),
        confluence=round(confluence, 4),
        label=_label_for(ds, confluence, insufficient, conflicts),
        counts=counts,
        conflicting_factors=conflicts,
        factor_states={key: factor.state for key, factor in factors.items()},
        insufficient_evidence=insufficient,
    )
