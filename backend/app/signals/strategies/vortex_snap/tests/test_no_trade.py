"""
Unit tests for Explicit No-Trade Logic (§18).
"""
import pytest
from app.signals.strategies.vortex_snap.feature_engine import VortexFeatureEngine
from app.signals.strategies.vortex_snap.signals.no_trade import NoTradeGate
from app.signals.strategies.vortex_snap.signals.reason_codes import ReasonCode
from app.signals.strategies.vortex_snap.types import MarketRegime
from app.signals.strategies.vortex_snap.tests.conftest import generate_flat_candles


class TestNoTradeGate:
    def setup_method(self):
        self.feature_engine = VortexFeatureEngine()
        self.no_trade_gate = NoTradeGate()

    def test_veto_on_cooldown_active(self):
        candles = generate_flat_candles(25)
        snapshot = self.feature_engine.compute_snapshot("NIFTY", candles)

        res = self.no_trade_gate.evaluate(snapshot, cooldown_active=True)
        assert res.is_no_trade
        assert ReasonCode.COOLDOWN_ACTIVE in res.rejection_reasons

    def test_veto_on_daily_loss_breach(self):
        candles = generate_flat_candles(25)
        snapshot = self.feature_engine.compute_snapshot("NIFTY", candles)

        res = self.no_trade_gate.evaluate(snapshot, daily_loss_limit_breached=True)
        assert res.is_no_trade
        assert ReasonCode.DAILY_LOSS_LIMIT_REACHED in res.rejection_reasons

    def test_veto_on_correlated_exposure(self):
        candles = generate_flat_candles(25)
        snapshot = self.feature_engine.compute_snapshot("NIFTY", candles)

        res = self.no_trade_gate.evaluate(snapshot, active_correlated_exposure=True)
        assert res.is_no_trade
        assert ReasonCode.CORRELATED_EXPOSURE_ACTIVE in res.rejection_reasons

    def test_veto_on_chaotic_regime(self):
        candles = generate_flat_candles(25)
        snapshot = self.feature_engine.compute_snapshot("NIFTY", candles)
        # Force chaotic regime
        snapshot.regime.regime = MarketRegime.CHAOTIC

        res = self.no_trade_gate.evaluate(snapshot)
        assert res.is_no_trade
        assert ReasonCode.REGIME_CHAOTIC in res.rejection_reasons
