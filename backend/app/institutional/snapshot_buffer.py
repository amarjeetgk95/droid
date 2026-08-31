"""
Synchronized Cross-Market Snapshot Buffer — §§22,23,24
Cross-market calculations must not compare independently received values nearby in time.
Buffer creates synchronized snapshots for NIFTY↔BANKNIFTY↔SENSEX etc.
Cross-market Δt < 500 ms by default, else CROSS_MARKET_DATA_NOT_SYNCHRONIZED.
"""
from __future__ import annotations

import time
import asyncio
from dataclasses import dataclass, field
from typing import Literal
import structlog

from app.institutional.events import InstrumentEvent

logger = structlog.get_logger()

SyncStatus = Literal["SYNCHRONIZED", "CROSS_MARKET_DATA_NOT_SYNCHRONIZED", "MISSING_INSTRUMENT", "STALE_INSTRUMENT"]


@dataclass
class SnapshotEntry:
    instrument_id: str
    event: InstrumentEvent
    received_ms: int = field(default_factory=lambda: int(time.time()*1000))


@dataclass
class SynchronizedSnapshot:
    snapshot_timestamp: int  # ms UTC — authoritative event time used for sync
    entries: dict[str, SnapshotEntry]
    delta_ms: int  # max Δt between entries
    status: SyncStatus
    reason: str | None = None

    def is_synchronized(self, threshold_ms: int = 500) -> bool:
        return self.status == "SYNCHRONIZED" and self.delta_ms < threshold_ms

    def price_for(self, instrument_id: str) -> str | None:
        e = self.entries.get(instrument_id.upper())
        return e.event.price if e else None


class SynchronizedSnapshotBuffer:
    """
    In-memory buffer coordinating cross-market alignment.
    Prefer matching event timestamp > matching bar-close > nearest valid within window (§24).
    Keeps source_event_timestamp, snapshot_timestamp, received_timestamp separate.
    """
    def __init__(self, sync_threshold_ms: int = 500, stale_threshold_ms: int = 5000):
        self.sync_threshold_ms = sync_threshold_ms
        self.stale_threshold_ms = stale_threshold_ms
        # Latest per instrument
        self._latest: dict[str, SnapshotEntry] = {}
        self._lock = asyncio.Lock()

    async def ingest(self, event: InstrumentEvent) -> None:
        async with self._lock:
            self._latest[event.instrument_id.upper()] = SnapshotEntry(
                instrument_id=event.instrument_id.upper(),
                event=event,
                received_ms=event.received_timestamp_utc,
            )

    # Synchronous version for non-async paths / tests
    def ingest_sync(self, event: InstrumentEvent) -> None:
        self._latest[event.instrument_id.upper()] = SnapshotEntry(
            instrument_id=event.instrument_id.upper(),
            event=event,
            received_ms=event.received_timestamp_utc,
        )

    def _age_ms(self, entry: SnapshotEntry, now_ms: int) -> int:
        return now_ms - entry.event.canonical_timestamp_utc

    def get_synchronized(
        self,
        instrument_ids: list[str],
        threshold_ms: int | None = None,
        now_ms: int | None = None,
    ) -> SynchronizedSnapshot:
        """
        Create synchronized snapshot for requested relationships.
        Returns CROSS_MARKET_DATA_NOT_SYNCHRONIZED if Δt >= threshold.
        """
        now_ms = now_ms if now_ms is not None else int(time.time()*1000)
        thresh = threshold_ms if threshold_ms is not None else self.sync_threshold_ms
        ids_upper = [i.upper() for i in instrument_ids]

        # Check missing instrument
        for iid in ids_upper:
            if iid not in self._latest:
                return SynchronizedSnapshot(
                    snapshot_timestamp=now_ms, entries={}, delta_ms=999999,
                    status="MISSING_INSTRUMENT", reason=f"missing {iid}",
                )

        entries: dict[str, SnapshotEntry] = {iid: self._latest[iid] for iid in ids_upper}

        # Check stale instrument — critical stale data must invalidate (§68)
        for iid, ent in entries.items():
            age = self._age_ms(ent, now_ms)
            if age > self.stale_threshold_ms:
                return SynchronizedSnapshot(
                    snapshot_timestamp=now_ms, entries=entries, delta_ms=age,
                    status="STALE_INSTRUMENT", reason=f"stale {iid} age {age}ms > {self.stale_threshold_ms}ms",
                )

        # Compute max Δt between event timestamps
        times = [e.event.canonical_timestamp_utc for e in entries.values()]
        delta = max(times) - min(times) if times else 0
        snapshot_ts = int(sum(times) / len(times)) if times else now_ms
        # Prefer matching event timestamp if all equal, else nearest valid within window
        # For MVP we use averaged snapshot_timestamp keeping source_event_timestamps separate
        if delta >= thresh:
            return SynchronizedSnapshot(
                snapshot_timestamp=snapshot_ts, entries=entries, delta_ms=delta,
                status="CROSS_MARKET_DATA_NOT_SYNCHRONIZED",
                reason=f"Δt {delta}ms >= threshold {thresh}ms",
            )
        return SynchronizedSnapshot(
            snapshot_timestamp=snapshot_ts, entries=entries, delta_ms=delta,
            status="SYNCHRONIZED",
        )

    def get_latest(self, instrument_id: str) -> SnapshotEntry | None:
        return self._latest.get(instrument_id.upper())

    def health(self) -> dict:
        now_ms = int(time.time()*1000)
        return {
            instrument: {
                "canonical_timestamp_utc": e.event.canonical_timestamp_utc,
                "received_timestamp_utc": e.received_ms,
                "snapshot_timestamp": e.event.canonical_timestamp_utc,
                "age_ms": now_ms - e.event.canonical_timestamp_utc,
            }
            for instrument, e in self._latest.items()
        }

    def clear(self) -> None:
        self._latest.clear()


# Global singleton for cross-market relationships like NIFTY↔BANKNIFTY
synchronized_buffer = SynchronizedSnapshotBuffer()
