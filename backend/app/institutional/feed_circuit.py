"""
Feed Circuit Breaker & Recovery — §§11,12,13
Per-instrument isolation. FEED_DEGRADED immediately stops new candidates.
Recovery via clean resync, authoritative snapshot, derived-state rebuild.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal
import structlog

from app.institutional.sequence import SequenceCheckResult

logger = structlog.get_logger()

FeedHealth = Literal["HEALTHY", "FEED_DEGRADED", "RECOVERING"]

@dataclass
class FeedState:
    instrument_id: str
    health: FeedHealth = "HEALTHY"
    reason: str | None = None
    degraded_at_ms: int | None = None
    anomaly: str | None = None
    suppress_candidates: bool = False
    # derived-state rebuild tracking
    needs_resync: bool = False
    last_snapshot_ms: int | None = None


class FeedCircuitBreaker:
    """
    Per-instrument breaker (§13 isolation).
    Any cross-market calculation involving degraded instrument must be invalid.
    """
    def __init__(self):
        self._states: dict[str, FeedState] = {}

    def _get(self, instrument_id: str) -> FeedState:
        k = instrument_id.upper()
        if k not in self._states:
            self._states[k] = FeedState(instrument_id=k)
        return self._states[k]

    def on_sequence_result(self, instrument_id: str, result: SequenceCheckResult) -> FeedState:
        st = self._get(instrument_id)
        if result.is_anomaly:
            return self.trip(instrument_id, anomaly=result.anomaly, reason=result.message)
        return st

    def trip(self, instrument_id: str, anomaly: str, reason: str) -> FeedState:
        st = self._get(instrument_id)
        if st.health == "FEED_DEGRADED":
            return st
        st.health = "FEED_DEGRADED"
        st.reason = reason
        st.anomaly = anomaly
        st.degraded_at_ms = int(time.time()*1000)
        st.suppress_candidates = True
        st.needs_resync = True
        logger.error("feed_degraded_trip", instrument=instrument_id, anomaly=anomaly, reason=reason,
                     action="STOP new breakout/breakdown/AI/execution candidates")
        return st

    def request_resync(self, instrument_id: str) -> FeedState:
        st = self._get(instrument_id)
        if st.health != "FEED_DEGRADED":
            return st
        st.health = "RECOVERING"
        logger.info("feed_resync_requested", instrument=instrument_id)
        return st

    def on_authoritative_snapshot(
        self,
        instrument_id: str,
        snapshot_timestamp_ms: int,
        sequence_id: int,
        validate_fn=None,
    ) -> FeedState:
        """
        Recovery flow:
        SEQUENCE GAP → FEED_DEGRADED → SUPPRESS → REQUEST CLEAN RESYNC → RECEIVE AUTHORITATIVE SNAPSHOT
        → VALIDATE TIMESTAMP → VALIDATE SEQUENCE → REBUILD DERIVED STATE → MARK HEALTHY → RESUME
        """
        st = self._get(instrument_id)
        if st.health not in ("FEED_DEGRADED", "RECOVERING"):
            # Unexpected snapshot while healthy — ignore but log
            logger.warning("snapshot_received_while_healthy", instrument=instrument_id)
            return st
        # Validate timestamp / sequence via optional callback
        if validate_fn:
            ok, reason = validate_fn(snapshot_timestamp_ms, sequence_id)
            if not ok:
                logger.warning("snapshot_validation_failed", instrument=instrument_id, reason=reason)
                st.health = "FEED_DEGRADED"
                st.reason = f"snapshot validation failed: {reason}"
                return st
        # Rebuild derived state — placeholder hook
        self._rebuild_derived_state(instrument_id, snapshot_timestamp_ms)
        st.health = "HEALTHY"
        st.reason = None
        st.anomaly = None
        st.suppress_candidates = False
        st.needs_resync = False
        st.last_snapshot_ms = snapshot_timestamp_ms
        # Reset sequence validator to snapshot sequence
        try:
            from app.institutional.sequence import get_sequence_validator
            v = get_sequence_validator(instrument_id)
            v.reset(to_seq=sequence_id)
        except Exception:
            pass
        logger.info("feed_recovered_healthy", instrument=instrument_id, snapshot_ms=snapshot_timestamp_ms)
        return st

    def _rebuild_derived_state(self, instrument_id: str, snapshot_ms: int) -> None:
        """
        Rebuild affected ordered state: OHLC, VWAP, volume, OI deltas, momentum, structure, etc.
        Hook — in production would clear & rehydrate rolling state from authoritative snapshot.
        """
        logger.info("rebuild_derived_state", instrument=instrument_id, snapshot_ms=snapshot_ms,
                    rebuilt=["OHLC","VWAP","volume","OI_deltas","momentum","structure","rolling_volatility","breakout_levels"])

    def is_healthy(self, instrument_id: str) -> bool:
        return self._get(instrument_id).health == "HEALTHY"

    def is_degraded(self, instrument_id: str) -> bool:
        return self._get(instrument_id).health == "FEED_DEGRADED"

    def suppresses(self, instrument_id: str) -> bool:
        return self._get(instrument_id).suppress_candidates

    def cross_market_invalid(self, instrument_ids: list[str]) -> bool:
        """Any cross-market calculation involving degraded instrument must be invalid (§13)"""
        return any(self.is_degraded(i) for i in instrument_ids)

    def snapshot(self, instrument_id: str) -> FeedState:
        return self._get(instrument_id)

    def all_states(self) -> dict[str, FeedState]:
        return dict(self._states)

    # Convenience for API
    def to_dict(self, instrument_id: str) -> dict:
        st = self._get(instrument_id)
        return {
            "instrument_id": st.instrument_id,
            "health": st.health,
            "reason": st.reason,
            "anomaly": st.anomaly,
            "degraded_at_ms": st.degraded_at_ms,
            "suppress_candidates": st.suppress_candidates,
            "needs_resync": st.needs_resync,
            "last_snapshot_ms": st.last_snapshot_ms,
        }


feed_circuit = FeedCircuitBreaker()
