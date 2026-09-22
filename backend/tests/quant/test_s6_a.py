"""Unit tests for S6-A Continuation Scanner (S6SPEC_v1.3)."""

import pytest
from datetime import datetime, timezone, timedelta

from app.quant.strategies.s6_config import create_default_config, S6Variant
from app.quant.strategies.s6_events import RawBreakoutEvent
from app.quant.strategies.s6_a import S6AScanner


class TestS6AScanner:

    @pytest.fixture
    def scanner(self) -> S6AScanner:
        config = create_default_config(variant=S6Variant.S6_A)
        return S6AScanner(config)

    def _make_breakout(
        self,
        event_id: str = "evt1",
        regime: str = "TREND_UP",
        volume_ratio: float = 1.5,
        close_location: float = 0.8,
        room_atr: float = 2.0,
        breakout_time: datetime = datetime(2026, 1, 5, 4, 30, tzinfo=timezone.utc), # 10:00 IST
    ) -> RawBreakoutEvent:
        return RawBreakoutEvent(
            event_id=event_id,
            episode_id="ep1",
            instrument="NIFTY",
            timeframe="1m",
            direction=1,
            breakout_time=breakout_time,
            breakout_price=25100.0,
            atr5=50.0,
            volume_ratio=volume_ratio,
            close_location=close_location,
            breakout_distance_atr=0.15,
            structure_level=25090.0,
            room_atr=room_atr,
            regime=regime,
        )

    def test_s6_a_valid_breakout_emits_candidate(self, scanner: S6AScanner):
        bo = self._make_breakout()
        candidates = scanner.scan_candidates([bo])
        assert len(candidates) == 1
        c = candidates[0]
        assert c.variant == "S6-A"
        assert c.direction == 1
        assert c.stop_distance == 1.5 * 50.0
        assert c.target_distance == 2.5 * 50.0
        assert c.entry_time == bo.breakout_time + timedelta(minutes=1)

    def test_s6_a_rejects_weak_volume(self, scanner: S6AScanner):
        bo = self._make_breakout(volume_ratio=1.1)  # < 1.30 min
        candidates = scanner.scan_candidates([bo])
        assert len(candidates) == 0

    def test_s6_a_rejects_weak_close_location(self, scanner: S6AScanner):
        bo = self._make_breakout(close_location=0.4)  # < 0.60 min
        candidates = scanner.scan_candidates([bo])
        assert len(candidates) == 0

    def test_s6_a_rejects_insufficient_room(self, scanner: S6AScanner):
        bo = self._make_breakout(room_atr=1.0)  # < 1.50 min
        candidates = scanner.scan_candidates([bo])
        assert len(candidates) == 0

    def test_s6_a_rejects_unstable_regime(self, scanner: S6AScanner):
        bo = self._make_breakout(regime="UNSTABLE")
        candidates = scanner.scan_candidates([bo])
        assert len(candidates) == 0

    def test_s6_a_enforces_daily_cap(self, scanner: S6AScanner):
        base_t = datetime(2026, 1, 5, 4, 30, tzinfo=timezone.utc)
        events = [
            self._make_breakout(event_id=f"e_{i}", breakout_time=base_t + timedelta(minutes=i * 20))
            for i in range(6)
        ]
        candidates = scanner.scan_candidates(events)
        assert len(candidates) == 4  # max 4 trades per day
