from datetime import datetime, timezone
from app.services.data_quality import DataQualityEngine
from app.models.contracts import TickEvent, EventPriority
from app.models.market import NormalizedCandle


class TestDataQualityEngine:
    def setup_method(self):
        self.dqe = DataQualityEngine()

    def test_valid_tick_passes(self):
        tick = TickEvent(
            timestamp=datetime.now(timezone.utc),
            symbol="NIFTY 50",
            ltp=25000.0,
            volume=1000,
            open_interest=50000,
            bid=24999.0,
            ask=25001.0,
            sequence_number=1,
        )
        res = self.dqe.validate_tick(tick)
        assert res.is_valid is True
        assert res.quarantine is False
        assert res.gap_detected is False

    def test_negative_ltp_quarantined(self):
        tick = TickEvent(
            timestamp=datetime.now(timezone.utc),
            symbol="NIFTY 50",
            ltp=-100.0,
            volume=1000,
        )
        res = self.dqe.validate_tick(tick)
        assert res.is_valid is False
        assert res.quarantine is True
        assert "Invalid non-positive LTP" in (res.reason or "")

    def test_inverted_bid_ask_quarantined(self):
        tick = TickEvent(
            timestamp=datetime.now(timezone.utc),
            symbol="NIFTY 50",
            ltp=25000.0,
            bid=25010.0,  # Bid > Ask
            ask=25000.0,
        )
        res = self.dqe.validate_tick(tick)
        assert res.is_valid is False
        assert res.quarantine is True
        assert "Inverted orderbook" in (res.reason or "")

    def test_sequence_gap_detection(self):
        t1 = TickEvent(
            timestamp=datetime.now(timezone.utc),
            symbol="NIFTY 50",
            ltp=25000.0,
            sequence_number=100,
        )
        t2 = TickEvent(
            timestamp=datetime.now(timezone.utc),
            symbol="NIFTY 50",
            ltp=25005.0,
            sequence_number=105,  # Gap from 100 to 105
        )
        res1 = self.dqe.validate_tick(t1)
        res2 = self.dqe.validate_tick(t2)
        assert res1.gap_detected is False
        assert res2.gap_detected is True
        assert res2.is_valid is True  # Valid data but gap flagged

    def test_candle_high_low_validation(self):
        invalid_candle = NormalizedCandle(
            timestamp=datetime.now(timezone.utc),
            open=25000.0,
            high=24900.0,  # High lower than open
            low=24800.0,
            close=24950.0,
            volume=1000,
        )
        res = self.dqe.validate_candle(invalid_candle)
        assert res.is_valid is False
        assert res.quarantine is True
