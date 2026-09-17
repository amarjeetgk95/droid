"""Unit tests for the shared SignalCandidate builder (dedup refactor).

Guards the contract that strategy construction goes through
``app.signals.strategies.candidate`` and that the builder forwards values
without inventing trading defaults beyond the model defaults.
"""
from decimal import Decimal
from pathlib import Path

import pytest

from app.signals.strategies.base import StrategyContext
from app.signals.strategies.candidate import (
    build_candidate,
    flip_direction,
    make_candidate,
)

STRATEGIES_DIR = Path(__file__).resolve().parents[1] / "app" / "signals" / "strategies"


def _ctx() -> StrategyContext:
    return StrategyContext(
        underlying="NIFTY",
        spot_price=Decimal("25000.00"),
        timeframe="5M",
    )


def _build(**overrides):
    kwargs = {
        "strategy": "ORB",
        "direction": "LONG_CALL",
        "entry_min": Decimal("25000.00"),
        "entry_max": Decimal("25010.00"),
        "trigger": Decimal("25005.00"),
        "stop_loss": Decimal("24975.00"),
        "target_1": Decimal("25050.00"),
        "target_2": Decimal("25100.00"),
        "risk_points": Decimal("30.00"),
    }
    kwargs.update(overrides)
    return make_candidate(_ctx(), **kwargs)


def test_make_candidate_plumbs_context_and_model_defaults():
    cand = _build()

    assert cand.underlying == "NIFTY"
    assert cand.timeframe == "5M"
    assert cand.spot_price == Decimal("25000.00")
    assert cand.strategy == "ORB"
    assert cand.direction == "LONG_CALL"

    assert cand.signal_type == "INTRADAY"
    assert cand.is_scalp is False
    assert cand.max_chase_fraction == 0.50
    assert cand.ttl_seconds == 300
    assert cand.time_stop_seconds is None
    assert cand.runner_ttl_seconds is None
    assert cand.risk_reward_t1 == 1.5
    assert cand.risk_reward_t2 == 2.5
    assert cand.technical_score == 50.0
    assert cand.mtf_score == 50.0
    assert cand.fno_score == 50.0
    assert cand.regime_score == 50.0
    assert cand.overall_confidence == 78.0
    assert cand.rationale == []
    assert cand.option_contract is None
    assert cand.greeks is None
    assert cand.path_simulation is None
    assert cand.candidate_id


def test_build_candidate_is_make_candidate_alias():
    cand = build_candidate(
        _ctx(),
        strategy="VWAP_SCALP",
        direction=flip_direction("LONG_CALL"),
        signal_type="SCALP",
        is_scalp=True,
        entry_min=Decimal("24900.00"),
        entry_max=Decimal("24910.00"),
        trigger=Decimal("24905.00"),
        stop_loss=Decimal("24880.00"),
        target_1=Decimal("24940.00"),
        target_2=Decimal("24960.00"),
        risk_points=Decimal("25.00"),
        risk_reward_t1=1.5,
        risk_reward_t2=2.5,
        max_chase_fraction=0.35,
        ttl_seconds=240,
        rationale=["mirrored"],
    )

    assert cand.direction == "LONG_PUT"
    assert cand.signal_type == "SCALP"
    assert cand.is_scalp is True
    assert cand.max_chase_fraction == 0.35
    assert cand.ttl_seconds == 240
    assert cand.rationale == ["mirrored"]


def test_flip_direction_round_trips():
    assert flip_direction("LONG_CALL") == "LONG_PUT"
    assert flip_direction("LONG_PUT") == "LONG_CALL"
    assert flip_direction(flip_direction("LONG_CALL")) == "LONG_CALL"


def test_flip_direction_rejects_unknown_direction():
    with pytest.raises(ValueError):
        flip_direction("SIDEWAYS")  # type: ignore[arg-type]


def test_strategy_modules_construct_only_through_builder():
    offenders = []
    for path in sorted(STRATEGIES_DIR.glob("*.py")):
        if path.name in {"candidate.py", "base.py"}:
            continue
        if "SignalCandidate(" in path.read_text(encoding="utf-8"):
            offenders.append(path.name)
    assert offenders == [], f"Direct SignalCandidate(...) construction found in {offenders}"
