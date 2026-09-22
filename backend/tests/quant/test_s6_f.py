"""Unit tests for S6-F Failed-Breakout Reversal Scanner (S6SPEC_v1.3)."""

import pytest
from datetime import datetime, timezone, timedelta

from app.quant.strategies.s6_config import create_default_config, S6Variant
from app.quant.strategies.s6_events import FailureEvent
from app.quant.strategies.s6_f import S6FScanner


class TestS6FScanner:

    @pytest.fixture
    def scanner(self) -> S6FScanner:
        config = create_default_config(variant=S6Variant.S6_F)
        return S6FScanner(config)

    def test_s6_f_reversal_direction_and_stop(self, scanner: S6FScanner):
        # Failed LONG breakout -> Short failure trade (direction = -1)
        fe = FailureEvent(
            event_id="fe1",
            breakout_event_id="bo1",
            instrument="NIFTY",
            direction=-1,
            failure_time=datetime(2026, 1, 5, 4, 35, tzinfo=timezone.utc), # 10:05 IST
            failure_price=25085.0,
            reentry_distance_atr=0.15,
            bars_since_breakout=3,
            failure_extreme=25120.0,
        )
        atr5_lookup = {"bo1": 50.0}

        candidates = scanner.scan_candidates([fe], atr5_lookup=atr5_lookup)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.variant == "S6-F"
        assert c.direction == -1  # Short reversal
        # Failure extreme = 25120.0, failure price = 25085.0 -> diff = 35.0
        # stop_buffer = 0.25 * 50 = 12.5 -> stop_dist = 35 + 12.5 = 47.5 pts (< 2.0 ATR cap = 100.0)
        assert c.stop_distance == 47.5
        assert c.target_distance == 2.0 * 50.0  # 100.0 pts

    def test_s6_f_stop_capping_at_2_atr(self, scanner: S6FScanner):
        # If extreme is very far away, stop must be capped at 2.0 ATR
        fe = FailureEvent(
            event_id="fe2",
            breakout_event_id="bo2",
            instrument="NIFTY",
            direction=-1,
            failure_time=datetime(2026, 1, 5, 4, 40, tzinfo=timezone.utc),
            failure_price=25080.0,
            reentry_distance_atr=0.20,
            bars_since_breakout=4,
            failure_extreme=25300.0,  # 220 pts away!
        )
        atr5_lookup = {"bo2": 50.0}
        candidates = scanner.scan_candidates([fe], atr5_lookup=atr5_lookup)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.stop_distance == 2.0 * 50.0  # strictly capped at 2.0 ATR
