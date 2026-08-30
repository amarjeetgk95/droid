import pytest
from datetime import datetime, timezone, timedelta
from app.services.timeseries_store import TimeSeriesStore
from app.models.timeseries import CandleRecord


class TestTimeSeriesStore:
    @pytest.mark.asyncio
    async def test_insert_and_query_candles(self):
        store = TimeSeriesStore()
        now = datetime.now(timezone.utc)
        c1 = CandleRecord(
            timestamp=now - timedelta(minutes=5),
            symbol="NIFTY 50",
            timeframe="5m",
            open=25000.0,
            high=25050.0,
            low=24980.0,
            close=25030.0,
            volume=10000,
        )
        await store.insert_candle(c1)
        res = await store.get_candles("NIFTY 50", "5m")
        assert len(res) == 1
        assert res[0].symbol == "NIFTY 50"
        assert res[0].close == 25030.0

    def test_dynamic_resampling_1m_to_5m(self):
        store = TimeSeriesStore()
        base_time = datetime(2026, 8, 28, 9, 15, tzinfo=timezone.utc)
        candles_1m = []

        # Create five 1-minute candles
        for i in range(5):
            candles_1m.append(CandleRecord(
                timestamp=base_time + timedelta(minutes=i),
                symbol="NIFTY 50",
                timeframe="1m",
                open=25000.0 + i * 5,
                high=25010.0 + i * 5,
                low=24995.0 + i * 5,
                close=25005.0 + i * 5,
                volume=1000,
            ))

        resampled_5m = store.resample_candles(candles_1m, target_timeframe="5m")
        assert len(resampled_5m) == 1
        agg = resampled_5m[0]
        assert agg.open == 25000.0   # First open
        assert agg.high == 25030.0   # Max high (25010 + 20)
        assert agg.low == 24995.0    # Min low
        assert agg.close == 25025.0  # Last close (25005 + 20)
        assert agg.volume == 5000    # Total volume (1000 * 5)
        assert agg.vwap is not None

    def test_compression_and_decompression(self):
        store = TimeSeriesStore()
        now = datetime.now(timezone.utc)
        candles = [
            CandleRecord(
                timestamp=now,
                symbol="NIFTY 50",
                timeframe="5m",
                open=25000.0,
                high=25050.0,
                low=24980.0,
                close=25030.0,
                volume=10000,
            )
        ]
        compressed = store.compress_candles(candles)
        assert isinstance(compressed, bytes)
        assert len(compressed) > 0

        decompressed = store.decompress_candles(compressed)
        assert len(decompressed) == 1
        assert decompressed[0].symbol == "NIFTY 50"
        assert decompressed[0].close == 25030.0
