"""Single construction point for ``SignalCandidate`` across all strategies.

Why this module exists
----------------------
Every detector used to repeat the same ~30-line ``SignalCandidate(...)`` kwarg
block twice (LONG_CALL / LONG_PUT), which meant:

* adding or renaming a candidate field required editing every strategy twice;
* the two mirrored branches could silently drift apart.

``make_candidate`` centralizes ctx plumbing and defaults. The builder mirrors
the model defaults on purpose (``max_chase_fraction=0.50``, ``ttl_seconds=300``,
``time_stop_seconds=None``, ``runner_ttl_seconds=None``, risk-reward 1.5/2.5,
neutral 50.0 sub-scores, ``overall_confidence=78.0``) so a strategy only passes
fields it actually overrides. Entry/stop/target geometry is always explicit —
those are per-setup economics, not global defaults.

``flip_direction`` is the LONG_CALL <-> LONG_PUT helper for mirrored branches.

Behavior contract: this module only forwards arguments to ``SignalCandidate``;
it must never add or infer trading values.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.signals.contract_resolver import InstrumentMaster
from app.signals.strategies.base import (
    SignalCandidate,
    SignalType,
    StrategyContext,
    StrategyName,
    TradeDirection,
)

_DIRECTION_FLIP: dict[str, str] = {
    "LONG_CALL": "LONG_PUT",
    "LONG_PUT": "LONG_CALL",
}


def flip_direction(direction: TradeDirection) -> TradeDirection:
    """Return the mirrored option direction (LONG_CALL <-> LONG_PUT)."""
    try:
        return _DIRECTION_FLIP[direction]  # type: ignore[return-value]
    except KeyError:
        raise ValueError(f"Unknown trade direction: {direction!r}") from None


def make_candidate(
    ctx: StrategyContext,
    *,
    strategy: StrategyName,
    direction: TradeDirection,
    entry_min: Decimal,
    entry_max: Decimal,
    trigger: Decimal,
    stop_loss: Decimal,
    target_1: Decimal,
    target_2: Decimal,
    risk_points: Decimal,
    risk_reward_t1: float = 1.5,
    risk_reward_t2: float = 2.5,
    signal_type: SignalType = "INTRADAY",
    is_scalp: bool = False,
    max_chase_fraction: float = 0.50,
    ttl_seconds: int = 300,
    time_stop_seconds: int | None = None,
    runner_ttl_seconds: int | None = None,
    technical_score: float = 50.0,
    mtf_score: float = 50.0,
    fno_score: float = 50.0,
    regime_score: float = 50.0,
    overall_confidence: float = 78.0,
    rationale: list[str] | None = None,
    option_contract: InstrumentMaster | None = None,
    greeks: dict[str, Any] | None = None,
    path_simulation: dict[str, Any] | None = None,
) -> SignalCandidate:
    """Build a ``SignalCandidate`` from a strategy context + explicit economics.

    ``underlying``, ``timeframe`` and ``spot_price`` are always taken from the
    live ``StrategyContext`` so callers cannot desynchronize them.
    """
    return SignalCandidate(
        underlying=ctx.underlying,
        strategy=strategy,
        direction=direction,
        timeframe=ctx.timeframe,
        spot_price=ctx.spot_price,
        signal_type=signal_type,
        is_scalp=is_scalp,
        entry_min=entry_min,
        entry_max=entry_max,
        trigger=trigger,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        risk_points=risk_points,
        risk_reward_t1=risk_reward_t1,
        risk_reward_t2=risk_reward_t2,
        max_chase_fraction=max_chase_fraction,
        ttl_seconds=ttl_seconds,
        time_stop_seconds=time_stop_seconds,
        runner_ttl_seconds=runner_ttl_seconds,
        technical_score=technical_score,
        mtf_score=mtf_score,
        fno_score=fno_score,
        regime_score=regime_score,
        overall_confidence=overall_confidence,
        rationale=list(rationale or []),
        option_contract=option_contract,
        greeks=greeks,
        path_simulation=path_simulation,
    )


# Explicit long-form alias for callers that prefer the verb.
build_candidate = make_candidate
