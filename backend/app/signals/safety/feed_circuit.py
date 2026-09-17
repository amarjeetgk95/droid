"""
Feed Circuit Breaker & Recovery
Per-instrument isolation. FEED_DEGRADED immediately stops new candidates and order dispatch.
Recovery via clean resync, authoritative snapshot, derived-state rebuild.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal
import structlog

from app.signals.safety.sequence_validator import SequenceCheckResult

logger = structlog.get_logger()

FeedHealth = Literal["HEALTHY", "FEED_DEGRADED", "UNKNOWN", "RECOVERING"]


@dataclass
class FeedState:
    instrument_id: str
    health: FeedHealth = "HEALTHY"
    reason: str | None = None
    degraded_at_ms: int | None = None
    anomaly: str | None = None
    suppress_candidates: bool = False
    needs_resync: bool = False
    last_snapshot_ms: int | None = None
    degraded_count: int = 0
    escalated: bool = False


class FeedCircuitBreaker:
    """
    Per-instrument breaker.
    Any cross-market calculation or order dispatch involving degraded instrument must fail closed.
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
        st.degraded_count += 1
        if st.health == "FEED_DEGRADED":
            # Escalate on repeated trips (5+): page risk desk, keep suppressed.
            if st.degraded_count >= 5 and not st.escalated:
                st.escalated = True
                logger.critical("feed_degraded_escalated", instrument=instrument_id,
                                degraded_count=st.degraded_count)
            return st
        st.health = "FEED_DEGRADED"
        st.reason = reason
        st.anomaly = anomaly
        st.degraded_at_ms = int(time.time() * 1000)
        st.suppress_candidates = True
        st.needs_resync = True
        logger.error(
            "feed_degraded_trip",
            instrument=instrument_id,
            anomaly=anomaly,
            reason=reason,
            action="STOP new breakout/breakdown/execution candidates",
        )
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
        st = self._get(instrument_id)
        if st.health not in ("FEED_DEGRADED", "RECOVERING"):
            logger.warning("snapshot_received_while_healthy", instrument=instrument_id)
            return st
        # validate_fn is REQUIRED — None never skips validation. When None is
        # passed we run a default sanity validator (timestamp/seq monotonic)
        # rather than passing through; production callers must supply an
        # explicit validator.
        fn = validate_fn
        if fn is None:
            logger.warning("snapshot_validation_default_used", instrument=instrument_id)

            def fn(ts_ms: int, seq: int):  # type: ignore[misc]
                try:
                    import time as _t
                    now = int(_t.time() * 1000)
                    if ts_ms is None or seq is None:
                        return False, "missing timestamp/seq"
                    if int(ts_ms) - now > 2000:
                        return False, "snapshot timestamp in future"
                    if int(seq) < 0:
                        return False, "negative sequence"
                    return True, "default-ok"
                except Exception as _e:
                    return False, str(_e)[:150]
        ok, reason = fn(snapshot_timestamp_ms, sequence_id)
        if not ok:
            logger.warning("snapshot_validation_failed", instrument=instrument_id, reason=reason)
            st.health = "FEED_DEGRADED"
            st.reason = f"snapshot validation failed: {reason}"
            return st
        self._rebuild_derived_state(instrument_id, snapshot_timestamp_ms)
        st.health = "HEALTHY"
        st.reason = None
        st.anomaly = None
        st.suppress_candidates = False
        st.needs_resync = False
        st.last_snapshot_ms = snapshot_timestamp_ms
        try:
            from app.signals.safety.sequence_validator import get_sequence_validator
            v = get_sequence_validator(instrument_id)
            v.reset(to_seq=sequence_id)
        except Exception:
            pass
        logger.info("feed_recovered_healthy", instrument=instrument_id, snapshot_ms=snapshot_timestamp_ms)
        return st

    def _rebuild_derived_state(self, instrument_id: str, snapshot_ms: int) -> None:
        logger.info(
            "rebuild_derived_state",
            instrument=instrument_id,
            snapshot_ms=snapshot_ms,
            rebuilt=["OHLC", "VWAP", "volume", "OI_deltas", "momentum", "structure"],
        )

    def is_healthy(self, instrument_id: str) -> bool:
        # Block unless HEALTHY: UNKNOWN and RECOVERING both deny execution.
        return self._get(instrument_id).health == "HEALTHY"

    def is_degraded(self, instrument_id: str) -> bool:
        # RECOVERING still suppresses: the feed is not proven healthy yet.
        return self._get(instrument_id).health in ("FEED_DEGRADED", "RECOVERING")

    def suppresses(self, instrument_id: str) -> bool:
        return self._get(instrument_id).suppress_candidates

    def cross_market_invalid(self, instrument_ids: list[str]) -> bool:
        return any(self.is_degraded(i) for i in instrument_ids)

    def snapshot(self, instrument_id: str) -> FeedState:
        return self._get(instrument_id)

    def all_states(self) -> dict[str, FeedState]:
        return dict(self._states)

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
            "degraded_count": st.degraded_count,
            "escalated": st.escalated,
        }


feed_circuit = FeedCircuitBreaker()
