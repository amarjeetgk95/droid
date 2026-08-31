"""
Candle Engine — §7

Maintain 1m/5m/15m/1h/Daily/Weekly
FORMING vs COMPLETED separation, anti look-ahead, dedup
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal
import structlog

from app.algo.money import D

logger = structlog.get_logger()

Timeframe = Literal["1m", "5m", "15m", "1h", "D", "W"]
CandleKind = Literal["FORMING", "COMPLETED"]

TF_MINUTES: dict[Timeframe, int] = {
    "1m": 1, "5m": 5, "15m": 15, "1h": 60, "D": 1440, "W": 10080,
}


@dataclass
class Candle:
    instrument_id: str
    timeframe: Timeframe
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    open_interest: Decimal | None = None
    start_ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    kind: CandleKind = "FORMING"
    is_completed: bool = False

    def to_dict(self) -> dict:
        return {
            "instrument_id": self.instrument_id,
            "timeframe": self.timeframe,
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
            "start_ts": self.start_ts.isoformat(),
            "end_ts": self.end_ts.isoformat(),
            "kind": self.kind,
        }


def _bucket_start(ts: datetime, tf: Timeframe) -> datetime:
    """Floor timestamp to candle bucket start."""
    ts = ts.astimezone(timezone.utc)
    if tf == "D":
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    if tf == "W":
        # Monday 00:00 UTC
        monday = ts - timedelta(days=ts.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    mins = TF_MINUTES[tf]
    total_mins = ts.hour * 60 + ts.minute
    bucket_mins = (total_mins // mins) * mins
    return ts.replace(hour=bucket_mins // 60, minute=bucket_mins % 60, second=0, microsecond=0)


class CandleEngine:
    """
    Per-instrument, per-timeframe candle aggregation.
    Prevents look-ahead leakage — only COMPLETED candles for signals.
    """

    def __init__(self):
        # key: (instrument_id, timeframe, bucket_start) -> Candle
        self._forming: dict[tuple[str, Timeframe, datetime], Candle] = {}
        self._completed: dict[tuple[str, Timeframe, datetime], Candle] = {}
        self._last_seen_ts: dict[str, datetime] = {}

    def ingest_tick(
        self,
        instrument_id: str,
        price: Decimal | float | str,
        volume: Decimal | float | str = 0,
        timestamp: datetime | None = None,
        open_interest: Decimal | None = None,
    ) -> None:
        ts = timestamp or datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        # Detect timestamp corruption / out-of-order (§7)
        last = self._last_seen_ts.get(instrument_id)
        if last and ts < last - timedelta(seconds=1):
            logger.warning("candle_out_of_order_tick", instrument_id=instrument_id, ts=ts.isoformat(), last=last.isoformat())
            # Don't forward-fill — drop or quarantine; here we ignore stale tick for forming logic
            # but still update if significantly earlier? For now ignore
            return
        if last is None or ts > last:
            self._last_seen_ts[instrument_id] = ts

        px = D(price)
        vol = D(volume)

        for tf in TF_MINUTES.keys():
            bucket = _bucket_start(ts, tf)  # type: ignore
            key = (instrument_id, tf, bucket)  # type: ignore
            c = self._forming.get(key)
            if c is None:
                # Close any prior forming for this instrument+tf that's not this bucket -> completed
                self._maybe_complete(instrument_id, tf, bucket)  # type: ignore
                c = Candle(
                    instrument_id=instrument_id,
                    timeframe=tf,  # type: ignore
                    open=px, high=px, low=px, close=px,
                    volume=vol,
                    open_interest=open_interest,
                    start_ts=bucket,
                    end_ts=bucket + timedelta(minutes=TF_MINUTES[tf]),  # type: ignore
                    kind="FORMING",
                    is_completed=False,
                )
                self._forming[key] = c
            else:
                c.high = max(c.high, px)
                c.low = min(c.low, px)
                c.close = px
                c.volume = c.volume + vol
                if open_interest is not None:
                    c.open_interest = open_interest

    def _maybe_complete(self, instrument_id: str, tf: Timeframe, new_bucket: datetime) -> None:
        # Any forming bucket older than new_bucket is now completed
        to_complete = []
        for (iid, t, b), c in self._forming.items():
            if iid == instrument_id and t == tf and b < new_bucket:
                to_complete.append((iid, t, b))
        for key in to_complete:
            c = self._forming.pop(key)
            c.kind = "COMPLETED"
            c.is_completed = True
            # dedup guard
            if key not in self._completed:
                self._completed[key] = c
            else:
                logger.warning("candle_duplicate_prevented", key=str(key))

    def get_forming(self, instrument_id: str, timeframe: Timeframe) -> Candle | None:
        # Return latest forming for instrument+tf
        cands = [(b, c) for (iid, t, b), c in self._forming.items() if iid == instrument_id and t == timeframe]
        if not cands:
            return None
        cands.sort(key=lambda x: x[0])
        return cands[-1][1]

    def get_completed(self, instrument_id: str, timeframe: Timeframe, limit: int = 100) -> list[Candle]:
        rows = [(b, c) for (iid, t, b), c in self._completed.items() if iid == instrument_id and t == timeframe]
        rows.sort(key=lambda x: x[0])
        return [c for _, c in rows[-limit:]]

    def detect_gaps(self, instrument_id: str, timeframe: Timeframe) -> list[datetime]:
        """Return missing bucket starts."""
        completed = self.get_completed(instrument_id, timeframe, limit=1000)
        if len(completed) < 2:
            return []
        gaps: list[datetime] = []
        mins = TF_MINUTES[timeframe]
        for i in range(1, len(completed)):
            expected = completed[i-1].start_ts + timedelta(minutes=mins)
            if completed[i].start_ts > expected:
                cur = expected
                while cur < completed[i].start_ts:
                    gaps.append(cur)
                    cur += timedelta(minutes=mins)
        return gaps

    def detect_extreme_move(self, instrument_id: str, timeframe: Timeframe = "1m", threshold_pct: Decimal = D("5")) -> bool:
        """§57 extreme tick jump detection."""
        completed = self.get_completed(instrument_id, timeframe, limit=2)
        if len(completed) < 2:
            return False
        prev, cur = completed[-2], completed[-1]
        if prev.close == 0:
            return False
        move_pct = abs((cur.close - prev.close) / prev.close * D(100))
        return move_pct >= threshold_pct
