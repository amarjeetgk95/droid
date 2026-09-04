import asyncio
import gzip
import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Sequence
from app.models.timeseries import CandleRecord
from app.models.contracts import TickEvent
import structlog

logger = structlog.get_logger()


class TimeSeriesStore:
    """High-Performance Time-Series Storage and Dynamic Resampling Engine.
    
    Adheres strictly to Section 20 (Time-Series Storage) and Section 27 (Compression).
    Provides in-memory fast indexing and on-the-fly OHLCV candle aggregation.
    """

    def __init__(self):
        # Key: (symbol, timeframe) -> sorted list of CandleRecords
        self._candle_store: dict[tuple[str, str], list[CandleRecord]] = defaultdict(list)
        # Key: symbol -> list of recent TickEvents (rolling buffer)
        self._tick_store: dict[str, list[TickEvent]] = defaultdict(list)
        self._lock = asyncio.Lock()

        # Telemetry
        self.total_candles_inserted: int = 0
        self.total_ticks_inserted: int = 0

    async def insert_candle(self, candle: CandleRecord) -> None:
        """Insert a single candle record into the time-series store."""
        async with self._lock:
            key = (candle.symbol, candle.timeframe)
            self._candle_store[key].append(candle)
            self.total_candles_inserted += 1

    async def insert_candles_batch(self, candles: Sequence[CandleRecord]) -> None:
        """Insert a batch of candle records."""
        async with self._lock:
            for c in candles:
                key = (c.symbol, c.timeframe)
                self._candle_store[key].append(c)
                self.total_candles_inserted += 1

    async def insert_tick(self, tick: TickEvent) -> None:
        """Insert a live tick event into the rolling tick store."""
        async with self._lock:
            store = self._tick_store[tick.symbol]
            store.append(tick)
            # Retain last 5000 ticks per symbol
            if len(store) > 5000:
                self._tick_store[tick.symbol] = store[-5000:]
            self.total_ticks_inserted += 1

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "5m",
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> list[CandleRecord]:
        """Retrieve candles within range or resample from base 1m candles if needed."""
        async with self._lock:
            key = (symbol, timeframe)
            candles = self._candle_store.get(key, [])

            # If target timeframe not directly available but 1m is, resample dynamically
            if not candles and timeframe != "1m":
                base_1m = self._candle_store.get((symbol, "1m"), [])
                if base_1m:
                    candles = self.resample_candles(base_1m, target_timeframe=timeframe)

            filtered = candles
            if start_time:
                filtered = [c for c in filtered if c.timestamp >= start_time]
            if end_time:
                filtered = [c for c in filtered if c.timestamp <= end_time]

            return filtered[-limit:]

    @staticmethod
    def resample_candles(
        source_candles: list[CandleRecord],
        target_timeframe: str = "5m",
    ) -> list[CandleRecord]:
        """Resample a list of 1-minute candles into higher timeframes.
        
        Aggregates Open (first), High (max), Low (min), Close (last),
        Volume (sum), and cumulative VWAP.
        """
        if not source_candles:
            return []

        tf_minutes_map = {
            "5m": 5,
            "15m": 15,
            "1h": 60,
            "1D": 1440,
        }
        mins = tf_minutes_map.get(target_timeframe, 5)
        bucket_delta = timedelta(minutes=mins)

        resampled: list[CandleRecord] = []
        current_bucket: list[CandleRecord] = []
        current_bucket_start: datetime | None = None

        for c in source_candles:
            # Determine bucket window start
            bucket_start = c.timestamp.replace(
                minute=(c.timestamp.minute // mins) * mins if mins < 60 else 0,
                second=0,
                microsecond=0,
            )

            if current_bucket_start is None:
                current_bucket_start = bucket_start

            if bucket_start == current_bucket_start:
                current_bucket.append(c)
            else:
                # Flush completed bucket
                if current_bucket:
                    resampled.append(TimeSeriesStore._aggregate_bucket(current_bucket, current_bucket_start, target_timeframe))
                current_bucket_start = bucket_start
                current_bucket = [c]

        # Flush final bucket
        if current_bucket and current_bucket_start:
            resampled.append(TimeSeriesStore._aggregate_bucket(current_bucket, current_bucket_start, target_timeframe))

        return resampled

    @staticmethod
    def _aggregate_bucket(
        bucket: list[CandleRecord],
        bucket_time: datetime,
        timeframe: str,
    ) -> CandleRecord:
        open_val = bucket[0].open
        high_val = max(c.high for c in bucket)
        low_val = min(c.low for c in bucket)
        close_val = bucket[-1].close
        total_vol = sum(c.volume for c in bucket)
        
        # Calculate VWAP: sum(typical_price * vol) / total_vol
        total_typ_vol = sum(((c.high + c.low + c.close) / 3.0) * c.volume for c in bucket)
        vwap_val = round(total_typ_vol / total_vol, 2) if total_vol > 0 else None
        last_oi = bucket[-1].open_interest

        return CandleRecord(
            timestamp=bucket_time,
            symbol=bucket[0].symbol,
            timeframe=timeframe,
            open=open_val,
            high=high_val,
            low=low_val,
            close=close_val,
            volume=total_vol,
            vwap=vwap_val,
            open_interest=last_oi,
        )

    @staticmethod
    def compress_candles(candles: list[CandleRecord]) -> bytes:
        """Compress candle array to gzip binary for efficient historical transfer."""
        raw_json = json.dumps([c.model_dump(mode="json") for c in candles])
        return gzip.compress(raw_json.encode("utf-8"))

    @staticmethod
    def decompress_candles(compressed_data: bytes) -> list[CandleRecord]:
        """Decompress gzip binary back into CandleRecord array."""
        raw_json = gzip.decompress(compressed_data).decode("utf-8")
        data_list = json.loads(raw_json)
        return [CandleRecord(**item) for item in data_list]

    def get_stats(self) -> dict:
        return {
            "total_candles_stored": self.total_candles_inserted,
            "total_ticks_stored": self.total_ticks_inserted,
            "tracked_series": len(self._candle_store),
        }


timeseries_store = TimeSeriesStore()
