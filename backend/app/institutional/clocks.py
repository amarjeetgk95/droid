"""
Time Model — §6
EventClock, MarketSessionClock, MonotonicOrderingClock
Canonical UTC for event time. Sequence IDs for deterministic ordering.
Never use local machine time as substitute for exchange timestamps.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone, date, time as dt_time
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from typing import Literal

IST = ZoneInfo("Asia/Kolkata")

SessionState = Literal["PRE_OPEN", "OPEN", "CLOSING", "CLOSED"]


@dataclass
class ClockMetrics:
    last_canonical_ms: int | None = None
    last_exchange_ms: int | None = None
    last_received_ms: int | None = None
    drift_ms: float | None = None


class EventClock:
    """
    Per-instrument/per-source authoritative clock.
    Preserves event_time, receive_time, processing_time separately.
    Never overwrites event time with server receive time (§5).
    """
    def __init__(self, instrument_id: str, source_id: str = "broker_feed"):
        self.instrument_id = instrument_id
        self.source_id = source_id
        self._metrics = ClockMetrics()
        self._last_canonical_ms: int | None = None

    def ingest(
        self,
        canonical_timestamp_utc: int,
        exchange_timestamp: int | None = None,
        received_timestamp_utc: int | None = None,
    ) -> dict:
        now_ms = int(time.time()*1000)
        received = received_timestamp_utc if received_timestamp_utc is not None else now_ms
        exchange = exchange_timestamp if exchange_timestamp is not None else canonical_timestamp_utc
        # drift = received - canonical (positive means late arrival)
        drift = received - canonical_timestamp_utc if canonical_timestamp_utc else None
        self._metrics = ClockMetrics(
            last_canonical_ms=canonical_timestamp_utc,
            last_exchange_ms=exchange,
            last_received_ms=received,
            drift_ms=float(drift) if drift is not None else None,
        )
        self._last_canonical_ms = canonical_timestamp_utc
        return {
            "canonical_timestamp_utc": canonical_timestamp_utc,
            "exchange_timestamp": exchange,
            "received_timestamp_utc": received,
            "processing_timestamp_utc": now_ms,
            "drift_ms": drift,
        }

    @property
    def metrics(self) -> ClockMetrics:
        return self._metrics

    def age_ms(self, canonical_ms: int | None = None) -> int | None:
        target = canonical_ms if canonical_ms is not None else self._last_canonical_ms
        if target is None:
            return None
        return int(time.time()*1000) - target


class MarketSessionClock:
    """
    Session-aware clock per instrument (§7, §64, §65).
    Indian equity: PRE_OPEN → OPEN → CLOSING → CLOSED via exchange-calendar config
    BTCUSD: continuous 24/7 (always OPEN)
    Must support session init, intraday state, close, EOD flush, settlement, reconciliation.
    """
    # Boundaries in IST for Indian equities
    _PRE_OPEN_START = dt_time(9, 0)
    _OPEN_START = dt_time(9, 15)
    _CLOSING_START = dt_time(15, 30)
    _CLOSE = dt_time(15, 30)  # NSE/BSE close inclusive

    def __init__(self, instrument_id: str, pipeline: str):
        self.instrument_id = instrument_id.upper()
        self.pipeline = pipeline  # INDIAN_EQUITY or CRYPTO
        self._state: SessionState = "CLOSED" if pipeline == "INDIAN_EQUITY" else "OPEN"
        self._last_transition_ms: int | None = None

    def _now_ist(self, now_ms: int | None = None) -> datetime:
        if now_ms is None:
            return datetime.now(IST)
        return datetime.fromtimestamp(now_ms/1000, tz=timezone.utc).astimezone(IST)

    def current_state(self, now_ms: int | None = None, override_date: date | None = None) -> SessionState:
        if self.pipeline == "CRYPTO":
            # 24/7 — always OPEN (§8, §65)
            return "OPEN"
        now_ist = self._now_ist(now_ms)
        # Allow override for tests
        if override_date is not None:
            # synthesize datetime on that date at current IST time-of-day
            now_ist = datetime.combine(override_date, now_ist.time(), tzinfo=IST)
        # Holiday/weekend handling — use calendar_service if available
        try:
            from app.services.calendar_service import calendar_service
            if not calendar_service.is_trading_day(now_ist.date()):
                return "CLOSED"
        except Exception:
            # Fallback weekend check
            if now_ist.weekday() >= 5:
                return "CLOSED"
        t = now_ist.time()
        if t < self._PRE_OPEN_START:
            return "CLOSED"
        if t < self._OPEN_START:
            return "PRE_OPEN"
        if t < self._CLOSING_START:
            return "OPEN"
        # At 15:30 exactly → CLOSING for brief window, then CLOSED
        if t == self._CLOSE:
            return "CLOSING"
        return "CLOSED"

    def is_open(self, now_ms: int | None = None) -> bool:
        return self.current_state(now_ms) == "OPEN"

    def is_tradable(self, now_ms: int | None = None) -> bool:
        # Only OPEN is tradable for equities; PRE_OPEN/CLOSING/CLOSED not
        if self.pipeline == "CRYPTO":
            return True
        return self.current_state(now_ms) == "OPEN"

    def should_flush_eod(self, now_ms: int | None = None, prev_state: SessionState | None = None) -> bool:
        # Transition OPEN/CLOSING → CLOSED signals EOD flush for Indian equities
        cur = self.current_state(now_ms)
        if self.pipeline == "CRYPTO":
            return False
        return cur == "CLOSED" and (prev_state in ("OPEN", "CLOSING") if prev_state else False)

    def session_info(self, now_ms: int | None = None) -> dict:
        state = self.current_state(now_ms)
        now_ist = self._now_ist(now_ms)
        return {
            "instrument_id": self.instrument_id,
            "pipeline": self.pipeline,
            "session_state": state,
            "is_open": state == "OPEN",
            "is_tradable": self.is_tradable(now_ms),
            "now_ist": now_ist.isoformat(),
            "now_utc_ms": int(time.time()*1000) if now_ms is None else now_ms,
        }


class MonotonicOrderingClock:
    """
    Deterministic processing order via sequence IDs — §6.
    Use canonical UTC for event time; use sequence IDs for deterministic processing order.
    """
    def __init__(self):
        self._seq_by_source: dict[str, int] = {}
        self._global_seq: int = 0

    def next_sequence(self, source_key: str) -> int:
        """Per source/instrument deterministic sequence (§10 — where source provides none)"""
        cur = self._seq_by_source.get(source_key, 0) + 1
        self._seq_by_source[source_key] = cur
        self._global_seq += 1
        return cur

    def global_sequence(self) -> int:
        self._global_seq += 1
        return self._global_seq

    def observed(self, source_key: str, seq: int) -> None:
        """Record observed source sequence for future ordering checks"""
        prev = self._seq_by_source.get(source_key, 0)
        if seq > prev:
            self._seq_by_source[source_key] = seq

    def last_for(self, source_key: str) -> int | None:
        return self._seq_by_source.get(source_key)


# Registry of clocks per instrument
_event_clocks: dict[str, EventClock] = {}
_session_clocks: dict[str, MarketSessionClock] = {}
_monotonic = MonotonicOrderingClock()

def get_event_clock(instrument_id: str, source_id: str = "broker_feed") -> EventClock:
    key = f"{instrument_id.upper()}:{source_id}"
    if key not in _event_clocks:
        _event_clocks[key] = EventClock(instrument_id, source_id)
    return _event_clocks[key]

def get_session_clock(instrument_id: str) -> MarketSessionClock:
    from app.institutional.instrument_registry import asset_registry
    prof = asset_registry.get(instrument_id)
    pipeline = prof.pipeline if prof else ("CRYPTO" if instrument_id.upper() == "BTCUSD" else "INDIAN_EQUITY")
    key = instrument_id.upper()
    if key not in _session_clocks:
        _session_clocks[key] = MarketSessionClock(instrument_id, pipeline)
    return _session_clocks[key]

def get_monotonic_clock() -> MonotonicOrderingClock:
    return _monotonic
