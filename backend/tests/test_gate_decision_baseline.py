"""
Phase 0 Characterization Test: Gate Decision Baseline
Captures gate evaluation and candidate rejection behaviors across:
  - Scalp Confirmation Gate (lunch session, vix extreme)
  - Trigger Integrity Gate (born triggered, inverted levels, no edge)
"""
from decimal import Decimal
import pytest
from app.signals.strategies.base import SignalCandidate
from app.signals.scalp_confirmation import scalp_confirmation_engine
from app.signals.trigger_gate import check_trigger_integrity


def _valid_candidate(strategy="BREAKOUT", direction="LONG_CALL", spot=Decimal("24000.0")) -> SignalCandidate:
    return SignalCandidate(
        underlying="NIFTY",
        strategy=strategy,
        direction=direction,
        timeframe="5M",
        spot_price=spot,
        entry_min=Decimal("24010.0"),
        entry_max=Decimal("24020.0"),
        trigger=Decimal("24015.0"),
        stop_loss=Decimal("23950.0"),
        target_1=Decimal("24100.0"),
        target_2=Decimal("24180.0"),
        risk_points=Decimal("65.0"),
        risk_reward_t1=1.3,
        risk_reward_t2=2.5,
        confidence=80.0,
    )


def test_trigger_gate_valid_candidate_passes():
    cand = _valid_candidate()
    gate = check_trigger_integrity(
        underlying=cand.underlying,
        strategy=cand.strategy,
        direction=cand.direction,
        spot_price=cand.spot_price,
        entry_min=cand.entry_min,
        entry_max=cand.entry_max,
        trigger=cand.trigger,
        stop_loss=cand.stop_loss,
        target_1=cand.target_1,
        target_2=cand.target_2,
        risk_points=cand.risk_points,
        risk_reward_t1=cand.risk_reward_t1,
        risk_reward_t2=cand.risk_reward_t2,
        is_scalp=cand.is_scalp,
        timeframe=cand.timeframe,
    )
    assert gate.passed is True
    assert gate.reason_code is None


def test_trigger_gate_born_triggered_rejected():
    # Long call where spot is already way above trigger
    cand = _valid_candidate(spot=Decimal("24080.0"))
    gate = check_trigger_integrity(
        underlying=cand.underlying,
        strategy=cand.strategy,
        direction=cand.direction,
        spot_price=cand.spot_price,
        entry_min=cand.entry_min,
        entry_max=cand.entry_max,
        trigger=cand.trigger,
        stop_loss=cand.stop_loss,
        target_1=cand.target_1,
        target_2=cand.target_2,
        risk_points=cand.risk_points,
        risk_reward_t1=cand.risk_reward_t1,
        risk_reward_t2=cand.risk_reward_t2,
        is_scalp=cand.is_scalp,
        timeframe=cand.timeframe,
    )
    assert gate.passed is False
    assert gate.reason_code == "TRIGGER_WRONG_SIDE"
    assert "born-triggered" in str(gate.message).lower()


def test_trigger_gate_inverted_stop_loss_rejected():
    # Long call with stop loss above trigger
    cand = _valid_candidate()
    cand.stop_loss = Decimal("24050.0")  # Invalid: SL > Trigger
    gate = check_trigger_integrity(
        underlying=cand.underlying,
        strategy=cand.strategy,
        direction=cand.direction,
        spot_price=cand.spot_price,
        entry_min=cand.entry_min,
        entry_max=cand.entry_max,
        trigger=cand.trigger,
        stop_loss=cand.stop_loss,
        target_1=cand.target_1,
        target_2=cand.target_2,
        risk_points=cand.risk_points,
        risk_reward_t1=cand.risk_reward_t1,
        risk_reward_t2=cand.risk_reward_t2,
        is_scalp=cand.is_scalp,
        timeframe=cand.timeframe,
    )
    assert gate.passed is False
    assert gate.reason_code == "SL_WRONG_SIDE"


def test_scalp_confirmation_gate_rejections():
    cand = _valid_candidate(strategy="VWAP_SCALP")
    cand.is_scalp = True
    cand.timeframe = "1M"
    cand.lunch_session = True

    res = scalp_confirmation_engine.validate(
        candidate=cand,
        current_spot=cand.spot_price,
        regime="RANGE",
    )
    assert res.passed is False
    assert res.reason_code == "REJECTED_LUNCH_SESSION"
