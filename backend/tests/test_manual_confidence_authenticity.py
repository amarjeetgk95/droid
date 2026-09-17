"""Manual confidence authenticity: breakdown computed, never echoed; F&O->VALIDATED."""
from tests.conftest import PINNED_FEED


def _gen(client, **over):
    base = {
        "underlying": "NIFTY", "strategy": "BREAKOUT", "direction": "LONG_CALL",
        "timeframe": "5M", "notify_telegram": False, "allow_closed_market": True,
    }
    base.update(over)
    return client.post("/api/v1/signals/generate", json=base)


def test_confidence_95_not_echoed(client, mock_market_feed, mock_market_open):
    ltp = PINNED_FEED["NIFTY 50"]
    res = _gen(client, current_price=ltp, confidence=95.0)
    assert res.status_code == 200, res.text
    sig = res.json()["signal"]
    bd = sig.get("confluence_breakdown") or {}
    for k in ("technical", "mtf", "fno", "regime", "ai"):
        assert k in bd, f"breakdown missing {k}"
    # Never a flat echo of the input: breakdown is a 5-domain dict.
    assert not (len(bd) == 1 and 95.0 in list(bd.values()))
    assert 0 < float(sig["confidence"]) <= 100


def test_fno_degraded_caps_at_validated(mock_market_open):
    """FSM refuses ARMED/TRIGGERED/CONFIRMED when fno_degraded (max VALIDATED)."""
    from decimal import Decimal
    from app.signals.fsm import SignalInstance, apply_fsm_transition_pure

    sig = SignalInstance(
        underlying="NIFTY", strategy="BREAKOUT", direction="LONG_CALL",
        timeframe="5M", spot_price=Decimal("24870"),
        entry_min=Decimal("24880"), entry_max=Decimal("24890"),
        trigger=Decimal("24885"), stop_loss=Decimal("24800"),
        target_1=Decimal("25000"), target_2=Decimal("25100"),
        risk_points=Decimal("85"), risk_reward_t1=1.5, risk_reward_t2=3.0,
        confidence=70.0,
        confluence_breakdown={"fno_degraded": True},
        fsm_state="VALIDATED",
    )
    ok, err = apply_fsm_transition_pure(sig, "ARMED")
    assert ok is False
    assert "FNO_DATA_DEGRADED" in (err or "")


def test_enrich_forces_validated_when_fno_degraded():
    import asyncio
    from decimal import Decimal
    from app.signals.pipeline.enrichment import enrich_candidate
    from app.signals.strategies.base import SignalCandidate
    from types import SimpleNamespace

    cand = SignalCandidate(
        underlying="NIFTY", strategy="BREAKOUT", direction="LONG_CALL",
        timeframe="5M", spot_price=Decimal("24870"),
        entry_min=Decimal("24880"), entry_max=Decimal("24890"),
        trigger=Decimal("24885"), stop_loss=Decimal("24800"),
        target_1=Decimal("25000"), target_2=Decimal("25100"),
        risk_points=Decimal("85"), risk_reward_t1=1.5, risk_reward_t2=3.0,
        technical_score=90, mtf_score=90, fno_score=90, regime_score=90,
    )
    risk = SimpleNamespace(lots=1, quantity=75)
    out = asyncio.run(enrich_candidate(
        cand=cand, active_candles=[], fno_data={}, fno_is_degraded=True,
        risk_decision=risk, overlay=None, rejected_gates=[]))
    state = out[3]  # (fused, overlay, explain, state, ai, ml)
    # F&O-degraded caps at VALIDATED (REJECT on empty PIT is stricter, also ok).
    assert state in ("VALIDATED", "REJECT"), state
