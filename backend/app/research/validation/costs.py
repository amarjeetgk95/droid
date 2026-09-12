"""Reference cost model for 1H forecast v2.3 (P1-5). No broker calls.

Execution mapping (§15 v2.3, pre-registered):
    spot signal at T -> futures mid entry at the NEXT available mid after T,
    exit at futures mid at T+60m. Both legs cross half the reference spread
    and incur slippage + statutory drag. This module prices that mapping;
    it never places orders, never reads live prices.

REFERENCE_COSTS_V1 (costs_version "ref-v1"):
    spread_bps    = 2.0 per side (half-spread proxy crossed on each leg;
                    round-trip spread = 2 * 2.0 = 4.0 bps of traded notional).
    slippage_bps  = 1.0 per side (queue/latency proxy; round-trip 2.0 bps).
    statutory_pct = 0.001 per side (ASSUMPTION: single blended placeholder for
                    STT + exchange + GST + SEBI + stamp, expressed as a
                    fraction of traded notional = 10 bps/side, 20 bps
                    round-trip. Real schedules vary by venue/product; the
                    placeholder is deliberately conservative and versioned so
                    a calibrated schedule can supersede it as ref-v2 without
                    rewriting history).
    brokerage_flat = 0.0 in return units (reference assumes zero brokerage;
                    non-zero flat fees belong in product-specific overlays).

Total reference drag per unit round-trip turnover:
    per_side_rate  = (spread_bps + slippage_bps) * 1e-4 + statutory_pct
                   = (2 + 1) * 1e-4 + 0.001 = 0.0013 (13 bps/side)
    roundtrip_rate = 2 * per_side_rate = 0.0026 (26 bps per full entry+exit).

Conventions:
    gross_returns[i]: per-signal gross return in decimal (e.g. 0.01 = +1%
        on traded notional, mid-to-mid, before costs).
    turnover[i]: round-trip turnover multiple for signal i
        (1.0 = full entry+exit on full notional; 0.0 = abstain/no-trade).
        A scalar is broadcast to all signals.
    net[i] = gross[i] - turnover[i] * roundtrip_rate - brokerage_flat
        (brokerage_flat scalar per signal, default 0).

Sensitivity: scale_costs(base, mult) returns a copy with spread/slippage/
statutory (and brokerage_flat) multiplied by mult. The P1 report runs
{base, 1.5x, 2x}.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

COSTS_VERSION: str = "ref-v1"

REFERENCE_COSTS_V1: Dict[str, float] = {
    "spread_bps": 2.0,
    "brokerage_flat": 0.0,
    "statutory_pct": 0.001,
    "slippage_bps": 1.0,
}

_SENSITIVITY_KEYS = ("spread_bps", "slippage_bps", "statutory_pct", "brokerage_flat")


def _cost_rates(costs: Dict[str, float]) -> tuple[float, float]:
    try:
        spread = float(costs["spread_bps"])
        slip = float(costs["slippage_bps"])
        stat = float(costs["statutory_pct"])
        flat = float(costs.get("brokerage_flat", 0.0))
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"costs must hold numeric spread_bps/slippage_bps/statutory_pct: {e}") from e
    if spread < 0 or slip < 0 or stat < 0 or flat < 0:
        raise ValueError(f"cost components must be >= 0, got {costs!r}")
    per_side = (spread + slip) * 1e-4 + stat
    return 2.0 * per_side, flat


def _as_lists(gross_returns, turnover) -> tuple[List[float], List[float]]:
    try:
        gross = [float(v) for v in gross_returns]
    except TypeError as e:
        raise ValueError("gross_returns must be a sequence of numbers") from e
    if isinstance(turnover, (int, float)):
        to = [float(turnover)] * len(gross)
    else:
        try:
            to = [float(v) for v in turnover]
        except TypeError as e:
            raise ValueError("turnover must be a number or sequence of numbers") from e
    if len(gross) != len(to):
        raise ValueError(f"length mismatch: gross={len(gross)} vs turnover={len(to)}")
    for i, v in enumerate(to):
        if v != v or v < 0:
            raise ValueError(f"turnover[{i}] must be >= 0, got {v!r}")
    return gross, to


def apply_costs(
    gross_returns: Sequence[float],
    turnover: Sequence[float] | float,
    costs: Dict[str, float] | None = None,
) -> List[float]:
    """Per-signal net returns after reference costs.

    net[i] = gross[i] - turnover[i] * roundtrip_rate - brokerage_flat.
    Pure; empty input -> []. Never touches network/broker.
    """
    base = dict(REFERENCE_COSTS_V1) if costs is None else dict(costs)
    roundtrip_rate, flat = _cost_rates(base)
    gross, to = _as_lists(gross_returns, turnover)
    return [g - t * roundtrip_rate - (flat if t > 0 else 0.0) for g, t in zip(gross, to)]


def summarize_costs(
    gross_returns: Sequence[float],
    turnover: Sequence[float] | float,
    costs: Dict[str, float] | None = None,
) -> Dict:
    """Aggregate {gross, cost, net, n, turnover, costs_version, costs}."""
    base = dict(REFERENCE_COSTS_V1) if costs is None else dict(costs)
    nets = apply_costs(gross_returns, turnover, base)
    gross, to = _as_lists(gross_returns, turnover)
    gross_sum = sum(gross)
    net_sum = sum(nets)
    return {
        "n": len(gross),
        "gross": gross_sum,
        "net": net_sum,
        "cost": gross_sum - net_sum,
        "turnover": sum(to),
        "costs_version": COSTS_VERSION,
        "costs": dict(base),
    }


def scale_costs(base: Dict[str, float], mult: float) -> Dict[str, float]:
    """Return a copy of base with cost components scaled by mult.

    Scales spread_bps, slippage_bps, statutory_pct, brokerage_flat.
    mult must be >= 0. Input dict is never mutated.
    """
    try:
        m = float(mult)
    except (TypeError, ValueError) as e:
        raise ValueError(f"mult must be numeric, got {mult!r}") from e
    if m < 0:
        raise ValueError(f"mult must be >= 0, got {mult!r}")
    out = dict(base)
    for k in _SENSITIVITY_KEYS:
        if k in out:
            out[k] = float(out[k]) * m
    return out


def sensitivity_summary(
    gross_returns: Sequence[float],
    turnover: Sequence[float] | float,
    base: Dict[str, float] | None = None,
    mults: Sequence[float] = (1.0, 1.5, 2.0),
) -> Dict[str, Dict]:
    """Net/gross/cost under each cost multiple (P1 report sensitivity)."""
    b0 = dict(REFERENCE_COSTS_V1) if base is None else dict(base)
    return {f"{float(m)}x": summarize_costs(gross_returns, turnover, scale_costs(b0, m)) for m in mults}
