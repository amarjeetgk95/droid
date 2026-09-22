"""Unit tests for S6 Deterministic Execution Simulator (S6SPEC_v1.3)."""

import pytest
import polars as pl
from datetime import datetime, timezone, timedelta

from app.quant.strategies.s6_config import create_default_config
from app.quant.strategies.s6_events import EntryCandidate
from app.quant.execution.s6_simulator import S6ExecutionSimulator, S6Trade


class TestS6Simulator:

    @pytest.fixture
    def simulator(self) -> S6ExecutionSimulator:
        config = create_default_config()
        return S6ExecutionSimulator(config)

    def _make_candidate(
        self,
        entry_time: datetime,
        direction: int = 1,
        ref_price: float = 25000.0,
        stop_dist: float = 75.0,
        target_dist: float = 125.0,
        atr5: float = 50.0,
    ) -> EntryCandidate:
        return EntryCandidate(
            candidate_id="c1",
            strategy_id="S6",
            variant="S6-A",
            instrument="NIFTY",
            direction=direction,
            signal_time=entry_time - timedelta(minutes=1),
            entry_time=entry_time,
            entry_reference_price=ref_price,
            execution_timeframe="1m",
            context_timeframe="5m",
            atr5=atr5,
            stop_distance=stop_dist,
            target_distance=target_dist,
            episode_id="ep1",
            event_id="evt1",
            regime="TREND_UP",
            volume_ratio=1.5,
            close_location=0.8,
            room_atr=2.0,
        )

    def test_entry_fill_at_next_bar_open_with_slippage(self, simulator: S6Simulator):
        t0 = datetime(2026, 1, 5, 4, 30, tzinfo=timezone.utc)
        cand = self._make_candidate(entry_time=t0, direction=1, atr5=50.0) # slippage = 0.05 * 50 = 2.5 pts

        # Bar t0: open=25000, high=25050, low=24980, close=25020
        df = pl.DataFrame({
            "timestamp": [t0, t0 + timedelta(minutes=1)],
            "open": [25000.0, 25020.0],
            "high": [25050.0, 25030.0],
            "low": [24980.0, 25010.0],
            "close": [25020.0, 25025.0],
            "volume": [1000.0, 1000.0],
        })

        trades = simulator.simulate_candidates([cand], df)
        assert len(trades) == 1
        t = trades[0]
        # Entry fill = open (25000) + slippage (2.5) = 25002.5
        assert t.entry_price == 25002.5
        assert t.stop_price == 25002.5 - 75.0
        assert t.target_price == 25002.5 + 125.0

    def test_missing_bar_cancels_candidate(self, simulator: S6ExecutionSimulator):
        t0 = datetime(2026, 1, 5, 4, 30, tzinfo=timezone.utc)
        cand = self._make_candidate(entry_time=t0)

        # Dataset starts at t0 + 5m (t0 is missing!)
        df = pl.DataFrame({
            "timestamp": [t0 + timedelta(minutes=5)],
            "open": [25000.0],
            "high": [25050.0],
            "low": [24980.0],
            "close": [25020.0],
            "volume": [1000.0],
        })

        trades = simulator.simulate_candidates([cand], df)
        assert len(trades) == 0  # cancelled due to missing t+1 bar

    def test_same_bar_collision_resolves_sl_first(self, simulator: S6ExecutionSimulator):
        t0 = datetime(2026, 1, 5, 4, 30, tzinfo=timezone.utc)
        cand = self._make_candidate(entry_time=t0, direction=1, atr5=50.0) # SL at 25002.5 - 75 = 24927.5, TP at 25127.5

        # Bar t0 has massive range that touches BOTH SL (24900 <= 24927.5) and TP (25150 >= 25127.5)
        df = pl.DataFrame({
            "timestamp": [t0],
            "open": [25000.0],
            "high": [25150.0],
            "low": [24900.0],
            "close": [25050.0],
            "volume": [1000.0],
        })

        trades = simulator.simulate_candidates([cand], df)
        assert len(trades) == 1
        t = trades[0]
        assert t.same_bar_collision is True
        assert t.exit_reason == "SAME_BAR_SL_FIRST"
        assert t.exit_price == t.stop_price  # strictly stopped out

    def test_adverse_gap_fills_at_open(self, simulator: S6ExecutionSimulator):
        t0 = datetime(2026, 1, 5, 4, 30, tzinfo=timezone.utc)
        t1 = t0 + timedelta(minutes=1)
        cand = self._make_candidate(entry_time=t0, direction=1, atr5=50.0) # SL = 24927.5

        # Bar t1 gaps down to 24900.0 (beyond SL 24927.5)
        df = pl.DataFrame({
            "timestamp": [t0, t1],
            "open": [25000.0, 24900.0], # adverse gap
            "high": [25010.0, 24910.0],
            "low": [24990.0, 24880.0],
            "close": [25005.0, 24890.0],
            "volume": [1000.0, 1000.0],
        })

        trades = simulator.simulate_candidates([cand], df)
        assert len(trades) == 1
        t = trades[0]
        assert t.exit_reason == "SL"
        assert t.exit_price == 24900.0  # filled at worse open price!

    def test_favorable_gap_fills_at_tp_no_improvement(self, simulator: S6ExecutionSimulator):
        t0 = datetime(2026, 1, 5, 4, 30, tzinfo=timezone.utc)
        t1 = t0 + timedelta(minutes=1)
        cand = self._make_candidate(entry_time=t0, direction=1, atr5=50.0) # TP = 25127.5

        # Bar t1 gaps up to 25200.0 (beyond TP 25127.5)
        df = pl.DataFrame({
            "timestamp": [t0, t1],
            "open": [25000.0, 25200.0], # favorable gap
            "high": [25010.0, 25220.0],
            "low": [24990.0, 25190.0],
            "close": [25005.0, 25210.0],
            "volume": [1000.0, 1000.0],
        })

        trades = simulator.simulate_candidates([cand], df)
        assert len(trades) == 1
        t = trades[0]
        assert t.exit_reason == "TP"
        assert t.exit_price == t.target_price  # no artificial price improvement beyond TP!
