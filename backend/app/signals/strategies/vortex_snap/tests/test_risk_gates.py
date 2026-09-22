"""
Unit tests for Risk, Compliance and Realism Gates (§29, §38, §39, §40).
"""
import time
import pytest
from app.signals.strategies.vortex_snap.risk.data_quality import DataQualityGate
from app.signals.strategies.vortex_snap.risk.daily_gates import DailyRiskGate
from app.signals.strategies.vortex_snap.risk.correlation import CorrelationController
from app.signals.strategies.vortex_snap.risk.execution_realism import ExecutionRealismModel
from app.signals.strategies.vortex_snap.signals.reason_codes import ReasonCode
from app.signals.strategies.vortex_snap.types import Candle
from app.signals.strategies.vortex_snap.tests.conftest import create_candle


class TestRiskGates:
    def test_data_quality_stale_data_rejection(self):
        gate = DataQualityGate(max_staleness_ms=5000)
        # Candle is from 1 hour ago
        stale_t = int(time.time() * 1000) - 3600000
        candles = [create_candle(stale_t, 24000, 24010, 23990, 24005)]

        res = gate.validate(candles)
        assert not res.is_valid
        assert res.rejection_reason == ReasonCode.DATA_STALE

    def test_data_quality_negative_volume_rejection(self):
        gate = DataQualityGate()
        now = int(time.time() * 1000)
        candles = [
            Candle.model_construct(
                timestamp=now,
                open=24000.0,
                high=24010.0,
                low=23990.0,
                close=24005.0,
                volume=-100.0,
            )
        ]

        res = gate.validate(candles)
        assert not res.is_valid
        assert res.rejection_reason == ReasonCode.DATA_QUALITY_FAIL

    def test_daily_risk_limits(self):
        gate = DailyRiskGate()
        assert gate.can_open_position()[0] is True

        # Simulate 3 consecutive small losses (sum = -30 < max daily loss 120)
        gate.record_trade_outcome(-10.0)
        gate.record_trade_outcome(-10.0)
        gate.record_trade_outcome(-10.0)

        can_open, reason = gate.can_open_position()
        assert can_open is False
        assert reason == ReasonCode.CONSECUTIVE_LOSS_LIMIT

    def test_correlation_clustering(self):
        ctrl = CorrelationController(cluster_window_seconds=120)
        t0 = int(time.time() * 1000)

        # NIFTY emits LONG signal
        c1 = ctrl.register_and_evaluate("NIFTY", direction=1, timestamp_ms=t0)
        assert c1 is None  # Single signal, no cluster yet

        # 10 seconds later, BANKNIFTY emits aligned LONG signal
        c2 = ctrl.register_and_evaluate("BANKNIFTY", direction=1, timestamp_ms=t0 + 10000)
        assert c2 is not None
        assert "NIFTY" in c2.instruments
        assert "BANKNIFTY" in c2.instruments
        assert c2.direction == 1
        assert c2.correlation_score >= 0.85

    def test_execution_realism_cost_model(self):
        model = ExecutionRealismModel(base_slippage_points=1.5)
        # NIFTY call buy at 120, sold at 150
        costs = model.calculate_trade_costs("NIFTY", entry_price=120.0, exit_price=150.0, lots=1, lot_size=25)

        assert costs.brokerage == 40.0
        assert costs.exchange_charges > 0.0
        assert costs.stt > 0.0
        assert costs.gst > 0.0
        assert costs.stamp_duty > 0.0
        assert costs.total_statutory_fees > 45.0
        assert costs.slippage_cost == 1.5 * 2 * 25  # 75.0 Rs
        assert costs.total_friction_cost > 120.0
