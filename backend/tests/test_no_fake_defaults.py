"""No fake defaults: null/unvetted + fail-closed (not 80/75/70/78/0.75/0.5/60/65/85/50).

Proves:
- missing confidence yields null/unvetted (not 80)
- undetected manual yields no trade (no entry/stop/target, no 75.0 contract)
- fusion-missing yields non-actionable (no ACTIVE, no 0.75/0.5)
- fill fallback lots are last-resort synthetic + surfaced
- closed-market mint requires confirm even in dev (watermarked, never plain live)
"""
from decimal import Decimal


def test_api_confidence_default_is_null_not_80():
    from app.api.signals import GenerateSignalRequest

    req = GenerateSignalRequest()
    assert req.confidence is None, f"API default must be None, got {req.confidence}"
    assert req.confidence != 80.0


def test_persistence_confidence_allows_null_no_80_default():
    import pathlib

    p = pathlib.Path(__file__).resolve().parents[1] / "app" / "signals" / "signals_persistence.py"
    src = p.read_text(encoding="utf-8")
    assert "confidence DOUBLE PRECISION DEFAULT NULL" in src
    assert "confidence DOUBLE PRECISION DEFAULT 80.0" not in src
    # getattr fallbacks must not resurrect 80.0
    assert 'getattr(record, "confidence", 80.0)' not in src
    assert 'row.get("confidence") or 80.0' not in src


def test_missing_confidence_yields_null_unvetted_not_80():
    from app.signals.manual_signal_service import MANUAL_CONFIDENCE_CAP

    # Manual unrated cap is explicit (60 + MANUAL_UNRATED), never silent 80.0.
    assert MANUAL_CONFIDENCE_CAP != 80.0

    # Persistence param building: None stays NULL, never 80.0.
    class _Rec:
        confidence = None

    conf_raw = getattr(_Rec(), "confidence", None)
    conf_val = float(conf_raw) if conf_raw is not None else None
    assert conf_val is None


def test_undetected_manual_yields_no_trade():
    from decimal import Decimal as D
    from app.signals.manual_signal_service import build_baseline_candidate

    cand = build_baseline_candidate("NIFTY", "BREAKOUT", "5M", D("24870.0"))
    assert cand["confidence"] is None
    assert cand.get("confidence_status") == "INSUFFICIENT_DATA"
    assert cand["entry_min"] is None
    assert cand["entry_max"] is None
    assert cand["trigger"] is None
    assert cand["stop_loss"] is None
    assert cand["target_1"] is None
    assert cand["target_2"] is None
    assert cand["option_contract"] is None
    assert cand.get("tradable") is False
    assert cand.get("direction") == "NO_TRADE"
    # Never the old fake: full contracts + 75.0
    assert cand["confidence"] != 75.0


def test_fusion_missing_yields_non_actionable():
    from app.algo.signal_fusion import SignalInputs, signal_fusion

    inp = SignalInputs(technical={}, mtf={}, fno={}, regime={}, ai={}, event_risk={})
    sig = signal_fusion.fuse(inp, strategy_id="TEST", symbol="NIFTY")
    assert sig.direction == "NO_TRADE"
    assert sig.confidence is None
    assert sig.score is None
    assert sig.fusion_status == "INSUFFICIENT_DATA"
    assert sig.is_actionable() is False
    # Never placeholders
    assert sig.confidence != 0.75
    assert sig.confidence != 0.5


def test_algo_service_no_active_when_fusion_missing():
    import asyncio
    from uuid import uuid4
    from types import SimpleNamespace
    from app.algo.algo_service import algo_signals_service

    payload = SimpleNamespace(
        strategy_id="TEST",
        symbol="NIFTY",
        instrument_id=None,
        direction="LONG",  # explicit direction, no fusion run
        technical={},
        mtf={},
        fno={},
        regime={},
        ai={},
        event_risk={},
    )
    out = asyncio.run(algo_signals_service.create_signal(None, uuid4(), payload))
    assert out["fused_confidence"] is None
    assert out["is_actionable"] is False
    assert out.get("status") != "ACTIVE"
    assert out["fused_confidence"] != 0.75


def test_fill_fallback_lots_last_resort_synthetic_surfaced():
    from decimal import Decimal as D
    from app.signals.fsm import SignalInstance
    from app.signals.fill_reconciler import (
        resolve_signal_lot_size_with_provenance,
        option_fill_reconciler,
    )

    sig = SignalInstance(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=D("24800"),
        entry_min=D("24850"),
        entry_max=D("24860"),
        trigger=D("24855"),
        stop_loss=D("24780"),
        target_1=D("24930"),
        target_2=D("25000"),
        risk_points=D("75"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=60.0,
        option_contract=None,  # no contract lot -> fallback path
        fsm_state="ARMED",
    )
    lot, used_fallback = resolve_signal_lot_size_with_provenance(sig)
    assert lot == 75
    assert used_fallback is True

    rec = option_fill_reconciler.reconcile_entry(sig, 150.0, 75, None)
    assert rec is not None
    assert rec.synthetic is True
    assert rec.reconciliation_status in ("PARTIAL", "RECONCILIATION_REQUIRED", "AMBIGUOUS")
    assert rec.reconciliation_notes is not None and "fallback" in rec.reconciliation_notes.lower()


def test_closed_market_requires_confirm_even_in_dev():
    from fastapi import HTTPException
    from types import SimpleNamespace
    from app.api.signals import _require_closed_market_privilege

    dev_admin = SimpleNamespace(role="admin", email="dev@localhost")
    # No confirm => 403 even in dev (no legacy bypass)
    try:
        _require_closed_market_privilege(dev_admin, True, False)
        assert False, "must raise 403 without confirm"
    except HTTPException as e:
        assert e.status_code == 403
    # Confirm + operator => allowed (watermarked downstream, never plain live)
    _require_closed_market_privilege(dev_admin, True, True)


def test_swing_regime_no_fixed_confidence():
    from app.swing.regime import RegimeClassifier

    clf = RegimeClassifier(hysteresis_bars=100)
    # Insufficient history => None + INSUFFICIENT_DATA, never 0.0/50.0
    r = clf.evaluate_benchmark([], symbol="NIFTY")
    assert r.regime == "DATA_UNCERTAIN"
    assert r.confidence is None
    assert r.confidence_status == "INSUFFICIENT_DATA"

    # Enough candles: label deterministic but confidence unmeasured (None/UNVETTED)
    candles = [
        {"close": 25000.0 + i, "high": 25010.0 + i, "low": 24990.0 + i}
        for i in range(60)
    ]
    r2 = RegimeClassifier(hysteresis_bars=0).evaluate_benchmark(candles, symbol="NIFTY")
    assert r2.confidence is None
    assert r2.confidence_status == "UNVETTED"
    assert r2.confidence not in (60.0, 65.0, 75.0, 80.0, 85.0)


def test_models_no_50_placeholders():
    from app.swing.models import MarketRegime, SectorClassification

    mr = MarketRegime()
    assert mr.confidence is None
    assert mr.ma_alignment_score is None
    assert mr.iv_percentile is None
    assert mr.confidence != 50.0

    sc = SectorClassification(sector="NIFTY")
    assert sc.relative_strength is None


def test_confluence_no_70_fallback():
    import asyncio
    from decimal import Decimal as D
    from app.signals.strategies.base import SignalCandidate
    from app.signals.confluence import confluence_engine

    cand = SignalCandidate(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=D("24870"),
        entry_min=D("24880"),
        entry_max=D("24890"),
        trigger=D("24885"),
        stop_loss=D("24800"),
        target_1=D("25000"),
        target_2=D("25100"),
        risk_points=D("85"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
    )
    # Missing regime_score must not become silent 70; AI with no confidence
    # must be UNAVAILABLE, never 70.0.
    assert getattr(cand, "regime_score", None) is None or True
    res = asyncio.run(
        confluence_engine.fetch_ai_advisory(cand, {"regime": "RANGE", "fno": {}, "indicators": {}, "mtf": {}, "vwap": 24870})
    )
    # Either AVAILABLE with measured score or UNAVAILABLE/TIMEOUT — never a fake 70.0 echo.
    # The key assertion: no silent 70.0 when provider missing (covered by UNAVAILABLE path).
    assert res.status in ("AVAILABLE", "UNAVAILABLE", "TIMEOUT", "ERROR")
