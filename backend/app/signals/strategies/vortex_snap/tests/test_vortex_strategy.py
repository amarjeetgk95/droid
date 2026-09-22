"""
Unit and integration tests for VortexSnapStrategy adapter.
"""
import time
from decimal import Decimal
import pytest

from app.signals.strategies.base import StrategyContext
from app.signals.strategies.vortex_snap.strategy import VortexSnapStrategy
from app.signals.strategies.vortex_snap.tests.conftest import create_candle, generate_flat_candles


from app.signals.strategies.vortex_snap.tests.test_session import make_ist_timestamp


class TestVortexSnapStrategy:
    def setup_method(self):
        self.strategy = VortexSnapStrategy()

    def test_fails_closed_without_candles(self):
        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=Decimal("24000.0"),
            indicators={},
            candles=[],
        )
        assert self.strategy.detect(ctx) is None

    def test_fails_closed_with_insufficient_candles(self):
        # Less than 20 bars
        candles = [
            {"open": 24000, "high": 24005, "low": 23995, "close": 24000, "volume": 1000}
            for _ in range(10)
        ]
        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=Decimal("24000.0"),
            indicators={},
            candles=candles,
        )
        assert self.strategy.detect(ctx) is None

    def test_successful_continuation_candidate_generation(self):
        # Monday 11:30 AM IST (Normal Intraday trading phase)
        now = make_ist_timestamp(2026, 9, 21, 11, 30)
        candles_raw = [
            {
                "timestamp": now - (32 - i) * 60000,
                "open": 24000.0 + (1.0 if i % 2 == 0 else -1.0),
                "high": 24003.0,
                "low": 23998.0,
                "close": 24000.0 - (1.0 if i % 2 == 0 else -1.0),
                "volume": 800.0,
            }
            for i in range(30)
        ]
        # Bar 31: Breakout above resistance at 24020
        candles_raw.append({
            "timestamp": now - 60000,
            "open": 24005.0,
            "high": 24035.0,
            "low": 24004.0,
            "close": 24030.0,
            "volume": 4000.0,
        })
        # Bar 32: Follow-through confirmation closing at 24038
        candles_raw.append({
            "timestamp": now,
            "open": 24030.0,
            "high": 24042.0,
            "low": 24028.0,
            "close": 24038.0,
            "volume": 3500.0,
        })

        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=Decimal("24038.0"),
            timestamp_ms=now,
            indicators={"pdh": 24020.0, "vwap": 24010.0},
            candles=candles_raw,
        )

        candidate = self.strategy.detect(ctx)
        assert candidate is not None
        assert candidate.strategy == "VORTEX_SNAP"
        assert candidate.direction == "LONG_CALL"
        assert candidate.is_scalp is True
        assert candidate.trigger > Decimal("0")
        assert candidate.stop_loss < candidate.trigger
        assert candidate.target_1 > candidate.trigger
        assert candidate.target_2 > candidate.target_1
        assert candidate.overall_confidence >= 50.0
        assert candidate.option_contract is not None
        assert candidate.option_contract.option_type == "CE"
        assert len(candidate.rationale) >= 2
