"""Live 1m candle aggregation tests (FYERS HSM ws tick source of truth).

Proves the honesty contract:
- closed candles only (partial minute never returned as a finished bar)
- no ticks => NO_DATA, never invented prices
- stale ticks reported with age
- broker cumulative volume folded without inventing a first delta
- out-of-order ticks never rewrite closed history
- HUD endpoint serves live WS candles with a truthful data_source when present
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.contracts import TickEvent
from app.services.live_candles import LiveCandleAggregator, canonical_symbol


def _tick(minute: datetime, ltp: float, symbol: str = "SENSEX", volume: int = 0) -> TickEvent:
    return TickEvent(timestamp=minute, symbol=symbol, ltp=ltp, volume=volume)


class TestAggregation:
    def setup_method(self):
        self.agg = LiveCandleAggregator()
        self.t0 = datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc)  # 09:30 IST

    def test_ticks_fold_into_closed_candles(self):
        m0, m1, m2 = self.t0, self.t0 + timedelta(minutes=1), self.t0 + timedelta(minutes=2)
        self.agg.on_tick(_tick(m0, 100.0))
        self.agg.on_tick(_tick(m0 + timedelta(seconds=20), 102.0))
        self.agg.on_tick(_tick(m0 + timedelta(seconds=40), 99.0))
        self.agg.on_tick(_tick(m1, 101.0))  # closes m0
        self.agg.on_tick(_tick(m1 + timedelta(seconds=30), 103.0))
        self.agg.on_tick(_tick(m2, 102.0))  # closes m1

        bars, status = self.agg.get_candles("SENSEX", 10)
        assert len(bars) == 2
        first, second = bars
        assert first.open == 100.0 and first.high == 102.0 and first.low == 99.0 and first.close == 99.0
        assert second.open == 101.0 and second.high == 103.0 and second.low == 101.0 and second.close == 103.0
        assert int(first.timestamp / 1000) == int(m0.timestamp())
        assert status["bars"] == 2
        assert status["last_candle_close"] == 103.0
        assert status["provider"] == "fyers_hsm_ws"

    def test_partial_minute_never_returned_as_closed(self):
        self.agg.on_tick(_tick(self.t0, 100.0))
        bars, status = self.agg.get_candles("SENSEX", 10)
        assert bars == []
        assert status["bars"] == 0
        assert status["partial_ticks"] == 1
        assert status["partial_close"] == 100.0

    def test_no_ticks_is_no_data_never_invented(self):
        bars, status = self.agg.get_candles("SENSEX", 10)
        assert bars == []
        assert status["status"] == "NO_DATA"
        assert status["age_s"] is None
        assert status["last_candle_timestamp_ms"] is None

    def test_stale_ticks_reported_with_age(self):
        old = datetime.now(timezone.utc) - timedelta(minutes=10)
        self.agg.on_tick(_tick(old, 100.0))
        self.agg.on_tick(_tick(old + timedelta(minutes=1), 101.0))
        bars, status = self.agg.get_candles("SENSEX", 10)
        assert len(bars) == 1
        assert status["status"] in ("STALE", "DOWN")
        assert status["age_s"] is not None and status["age_s"] > 120

    def test_cumulative_volume_never_invents_first_delta(self):
        m0, m1 = self.t0, self.t0 + timedelta(minutes=1)
        self.agg.on_tick(_tick(m0, 100.0, volume=1000))
        self.agg.on_tick(_tick(m0 + timedelta(seconds=10), 100.5, volume=1050))
        self.agg.on_tick(_tick(m0 + timedelta(seconds=20), 100.8, volume=1120))
        self.agg.on_tick(_tick(m1, 101.0, volume=1200))  # closes m0
        bars, _ = self.agg.get_candles("SENSEX", 10)
        assert len(bars) == 1
        # baseline sample is dropped (delta unknown), then +50 +70 = 120
        assert bars[0].volume == 120.0

    def test_index_zero_volume_is_measured_zero(self):
        m0, m1 = self.t0, self.t0 + timedelta(minutes=1)
        self.agg.on_tick(_tick(m0, 100.0))
        self.agg.on_tick(_tick(m1, 101.0))
        bars, status = self.agg.get_candles("SENSEX", 10)
        assert bars[0].volume == 0.0
        assert status["volume_available"] is False

    def test_out_of_order_ticks_do_not_rewrite_history(self):
        m0, m1, m2 = self.t0, self.t0 + timedelta(minutes=1), self.t0 + timedelta(minutes=2)
        self.agg.on_tick(_tick(m0, 100.0))
        self.agg.on_tick(_tick(m1, 101.0))
        self.agg.on_tick(_tick(m2, 102.0))  # closes m0, m1
        self.agg.on_tick(_tick(m0 + timedelta(seconds=30), 999.0))  # late replay
        bars, _ = self.agg.get_candles("SENSEX", 10)
        assert [b.close for b in bars] == [100.0, 101.0]

    def test_symbol_alias_matches_feed_symbol(self):
        assert canonical_symbol("NIFTY") == "NIFTY 50"
        self.agg.on_tick(_tick(self.t0, 24000.0, symbol="NIFTY 50"))
        self.agg.on_tick(_tick(self.t0 + timedelta(minutes=1), 24010.0, symbol="NIFTY 50"))
        bars, status = self.agg.get_candles("NIFTY", 10)
        assert len(bars) == 1
        assert status["symbol"] == "NIFTY 50"


class TestHudServesLiveWs:
    @pytest.fixture()
    def client(self):
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def _clean_live_state(self):
        from app.services.live_candles import live_candles
        live_candles.reset()
        yield
        live_candles.reset()

    def test_hud_serves_live_ws_candles_when_feed_has_bars(self, client):
        from app.services.live_candles import live_candles

        # 31 closed minutes of real ticks => live path is usable (>= min bars).
        base = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=40)
        for i in range(32):
            live_candles.on_tick(
                _tick(base + timedelta(minutes=i), 80000.0 + i * 2)
            )

        resp = client.get("/api/v1/strategies/vortex-snap/microstructure/SENSEX?bars=60")
        assert resp.status_code == 200
        data = resp.json()["data"]
        src = data["data_source"]
        assert src["type"] == "fyers_ws_live"
        assert src["is_simulated"] is False
        assert src["provenance_verified"] is True
        assert src["live"]["bars"] >= 30
        # Last *closed* minute is base+30 (the current minute is still partial).
        assert data["latest_close"] == 80000.0 + 30 * 2
        assert data["last_candle_timestamp_ms"] > 0
