"""Trigger-integrity gate + bulk/datewise delete coverage.

Guards the two reported bugs:
1. Fake no-edge signals (trigger = spot ± 1 tick) must never register.
2. Users need multi-select + datewise clearing of accumulated signals.
"""
import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.signals.trigger_gate import check_trigger_integrity
from app.signals.strategies.base import StrategyContext
from app.signals.strategies.mean_reversion import MeanReversionStrategy
from app.signals.strategies.gamma_squeeze import GammaSqueezeStrategy
from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.audit_ledger import signal_audit_ledger


@pytest.fixture
def client():
    return TestClient(app)


def _gate_kwargs(**over):
    base = dict(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        spot_price=Decimal("24900"),
        entry_min=Decimal("24900"),
        entry_max=Decimal("24930"),
        trigger=Decimal("24950"),
        stop_loss=Decimal("24840"),
        target_1=Decimal("24990"),
        target_2=Decimal("25080"),
        risk_points=Decimal("60"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
    )
    base.update(over)
    return base


class TestTriggerGate:
    def test_rejects_spot_plus_tick_born_triggered(self):
        res = check_trigger_integrity(**_gate_kwargs(trigger=Decimal("24900.05")))
        assert res.passed is False
        assert res.reason_code == "TRIGGER_TOO_CLOSE"

    def test_rejects_spot_minus_tick_put(self):
        res = check_trigger_integrity(**_gate_kwargs(
            direction="LONG_PUT",
            entry_min=Decimal("24870"),
            entry_max=Decimal("24900"),
            trigger=Decimal("24899.95"),
            stop_loss=Decimal("24960"),
        ))
        assert res.passed is False
        assert res.reason_code == "TRIGGER_TOO_CLOSE"

    def test_rejects_wrong_side_call(self):
        res = check_trigger_integrity(**_gate_kwargs(trigger=Decimal("24850")))
        assert res.passed is False
        assert res.reason_code == "TRIGGER_WRONG_SIDE"

    def test_accepts_real_breakout_gap(self):
        res = check_trigger_integrity(**_gate_kwargs())
        assert res.passed is True

    def test_rejects_dust_risk(self):
        res = check_trigger_integrity(**_gate_kwargs(
            entry_min=Decimal("24900"),
            entry_max=Decimal("24900.5"),
            trigger=Decimal("24950"),
            stop_loss=Decimal("24899.5"),
            risk_points=Decimal("0.5"),
        ))
        assert res.passed is False
        assert res.reason_code == "RISK_TOO_SMALL"


class TestStrategyTriggerLevels:
    def _ctx(self, **kw):
        base = dict(
            underlying="NIFTY",
            spot_price=Decimal("25000"),
            timeframe="5M",
            indicators={
                "bollinger_bands": {"upper": Decimal("25150"), "middle": Decimal("25000"), "lower": Decimal("25020")},
                "rsi": 25.0,
                "atr": 120.0,
            },
            mtf={"alignment_score": 70.0},
            fno={"pcr": 1.0, "oi_change_pct": 2.0, "atm_iv": 14.0, "max_pain": 25000.0},
            regime="RANGE",
        )
        base.update(kw)
        return StrategyContext(**base)

    def test_mean_reversion_needs_bb_and_rsi(self):
        strat = MeanReversionStrategy()
        # RSI extreme alone, price mid-bands → no signal (was OR → fake)
        ctx = self._ctx(indicators={
            "bollinger_bands": {"upper": Decimal("25300"), "middle": Decimal("25000"), "lower": Decimal("24700")},
            "rsi": 25.0,
            "atr": 120.0,
        })
        assert strat.detect(ctx) is None

    def test_mean_reversion_trigger_has_gap(self):
        strat = MeanReversionStrategy()
        cand = strat.detect(self._ctx())
        assert cand is not None
        res = check_trigger_integrity(
            underlying=cand.underlying, strategy=cand.strategy, direction=cand.direction,
            spot_price=cand.spot_price, entry_min=cand.entry_min, entry_max=cand.entry_max,
            trigger=cand.trigger, stop_loss=cand.stop_loss, target_1=cand.target_1,
            target_2=cand.target_2, risk_points=cand.risk_points,
            risk_reward_t1=cand.risk_reward_t1, risk_reward_t2=cand.risk_reward_t2,
        )
        assert res.passed is True, res.message

    def test_gamma_squeeze_needs_two_of_three(self):
        strat = GammaSqueezeStrategy()
        # OI surge alone with neutral PCR at max pain → only 2 signals? wall+oi = 2 → fires; drop wall:
        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=Decimal("25200"),  # above max_pain*1.002 → wall False for PUT; CALL wall True...
            timeframe="5M",
            indicators={"atr": 150.0},
            mtf={"alignment_score": 70.0},
            fno={"pcr": 1.0, "oi_change_pct": 2.0, "atm_iv": 14.0, "max_pain": 25000.0},
            regime="HIGH_VOL",
        )
        # neutral PCR + no OI surge → only wall → must not fire
        assert strat.detect(ctx) is None

    def test_gamma_squeeze_trigger_has_gap(self):
        strat = GammaSqueezeStrategy()
        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=Decimal("24950"),
            timeframe="5M",
            indicators={"atr": 150.0},
            mtf={"alignment_score": 70.0},
            fno={"pcr": 0.70, "oi_change_pct": 10.0, "atm_iv": 16.0, "max_pain": 24900.0},
            regime="HIGH_VOL",
        )
        cand = strat.detect(ctx)
        assert cand is not None
        res = check_trigger_integrity(
            underlying=cand.underlying, strategy=cand.strategy, direction=cand.direction,
            spot_price=cand.spot_price, entry_min=cand.entry_min, entry_max=cand.entry_max,
            trigger=cand.trigger, stop_loss=cand.stop_loss, target_1=cand.target_1,
            target_2=cand.target_2, risk_points=cand.risk_points,
            risk_reward_t1=cand.risk_reward_t1, risk_reward_t2=cand.risk_reward_t2,
        )
        assert res.passed is True, res.message


def _make_signal(**kw):
    base = dict(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24900"),
        entry_min=Decimal("24900"),
        entry_max=Decimal("24930"),
        trigger=Decimal("24950"),
        stop_loss=Decimal("24840"),
        target_1=Decimal("24990"),
        target_2=Decimal("25080"),
        risk_points=Decimal("60"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=80.0,
    )
    base.update(kw)
    inst = SignalInstance(**base)
    signal_fsm.register(inst)
    return inst.signal_id


class TestBulkDelete:
    def test_bulk_delete_by_ids(self, client):
        ids = [_make_signal(), _make_signal(strategy="ORB")]
        try:
            r = client.post("/api/v1/signals/bulk-delete", json={"signal_ids": ids})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["deleted_count"] == 2
            assert signal_fsm.get(ids[0]) is None
            assert signal_fsm.get(ids[1]) is None
            assert signal_audit_ledger.get(ids[0]) is None
        finally:
            for sid in ids:
                signal_fsm.delete(sid)
                signal_audit_ledger.delete_trade(sid)

    def test_bulk_delete_datewise(self, client):
        old_ms = int(time.time() * 1000) - 10 * 24 * 3600 * 1000
        old_id = _make_signal(created_at_utc=old_ms, expires_at_utc=old_ms + 300000)
        fresh_id = _make_signal()
        try:
            r = client.post("/api/v1/signals/bulk-delete", json={"before_ms": int(time.time() * 1000) - 24 * 3600 * 1000})
            assert r.status_code == 200, r.text
            assert old_id in r.json()["deleted_ids"]
            assert signal_fsm.get(fresh_id) is not None
        finally:
            signal_fsm.delete(old_id)
            signal_audit_ledger.delete_trade(old_id)
            signal_fsm.delete(fresh_id)
            signal_audit_ledger.delete_trade(fresh_id)

    def test_bulk_delete_needs_selector(self, client):
        r = client.post("/api/v1/signals/bulk-delete", json={})
        assert r.status_code == 400

    def test_bulk_delete_all_needs_confirm(self, client):
        r = client.post("/api/v1/signals/bulk-delete", json={"delete_all": True})
        assert r.status_code == 400
