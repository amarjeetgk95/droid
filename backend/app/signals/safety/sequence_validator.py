"""
Sequence Integrity Validator
Preserves source sequence, detects duplicate/missing/out-of-order/regression/jump.
Where source does not provide, generates deterministic internal sequence_id per source/instrument.
LRU via OrderedDict (bounded), OUT_OF_ORDER emission, _last persisted, wired to feed_circuit.
"""
from __future__ import annotations

import json
from collections import OrderedDict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import structlog

logger = structlog.get_logger()

SequenceAnomaly = Literal[
    "NONE",
    "DUPLICATE",
    "MISSING",
    "OUT_OF_ORDER",
    "REGRESSION",
    "UNEXPECTED_JUMP",
]


@dataclass
class SequenceCheckResult:
    anomaly: SequenceAnomaly
    expected: int | None
    received: int | None
    gap_size: int | None = None
    is_anomaly: bool = False
    message: str = ""


_SEQ_STATE_FILE = Path(__file__).resolve().parents[4] / "sequence_state.json"


class SequenceValidator:
    """
    Per instrument/source validator.
    Triggers: missing, duplicate, out-of-order, regression, unexpected jump.
    """

    UNEXPECTED_JUMP_THRESHOLD: int = 100
    _LRU_CAP: int = 5000

    def __init__(self, instrument_id: str, source_id: str = "broker_feed"):
        self.instrument_id = instrument_id.upper()
        self.source_id = source_id
        self._last_source_seq: int | None = None
        # OrderedDict LRU: seq -> None (bounded, no set-slice copy)
        self._seen: OrderedDict[int, None] = OrderedDict()
        self._recent: deque[int] = deque(maxlen=100)
        self._internal_seq: int = 0
        self._gap_detected: bool = False
        self._restore_last()

    def _next_internal(self) -> int:
        self._internal_seq += 1
        return self._internal_seq

    def _remember(self, seq: int) -> None:
        self._seen[seq] = None
        self._seen.move_to_end(seq)
        while len(self._seen) > self._LRU_CAP:
            self._seen.popitem(last=False)
        self._recent.append(seq)

    def _persist_last(self) -> None:
        try:
            key = f"{self.instrument_id}:{self.source_id}"
            data: dict = {}
            if _SEQ_STATE_FILE.exists():
                try:
                    data = json.loads(_SEQ_STATE_FILE.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            data[key] = self._last_source_seq
            tmp = _SEQ_STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(_SEQ_STATE_FILE)
        except Exception:
            pass

    def _restore_last(self) -> None:
        try:
            if _SEQ_STATE_FILE.exists():
                data = json.loads(_SEQ_STATE_FILE.read_text(encoding="utf-8"))
                v = data.get(f"{self.instrument_id}:{self.source_id}")
                if isinstance(v, int):
                    self._last_source_seq = v
        except Exception:
            pass

    def check(self, source_sequence_id: int | None, sequence_id: int | None = None) -> SequenceCheckResult:
        # sequence_id fallback: prefer source_sequence_id, else sequence_id, else internal.
        recv = source_sequence_id if source_sequence_id is not None else sequence_id
        if recv is None:
            gen = self._next_internal()
            return SequenceCheckResult(
                anomaly="NONE",
                expected=None,
                received=gen,
                is_anomaly=False,
                message="generated internal sequence",
            )

        received = int(recv)

        # Duplicate detection (LRU)
        if received in self._seen:
            logger.warning("sequence_duplicate", instrument=self.instrument_id, seq=received)
            res = SequenceCheckResult(
                anomaly="DUPLICATE",
                expected=self._last_source_seq,
                received=received,
                is_anomaly=True,
                message=f"duplicate sequence {received}",
            )
            self._wire_circuit(res)
            return res

        # First observation
        if self._last_source_seq is None:
            self._last_source_seq = received
            self._remember(received)
            self._persist_last()
            return SequenceCheckResult(anomaly="NONE", expected=None, received=received)

        expected = self._last_source_seq + 1

        # Out-of-order: within recent window but not duplicate and below last
        # (late arrival after gap already advanced _last). Distinguish from
        # hard regression (far behind).
        if received < self._last_source_seq:
            if received in list(self._recent)[-20:]:
                res = SequenceCheckResult(
                    anomaly="OUT_OF_ORDER",
                    expected=expected,
                    received=received,
                    is_anomaly=True,
                    message=f"out-of-order {received} (expected {expected})",
                )
                logger.warning("sequence_out_of_order", instrument=self.instrument_id,
                               expected=expected, received=received)
                self._wire_circuit(res)
                return res
            logger.warning(
                "sequence_regression",
                instrument=self.instrument_id,
                expected=expected,
                received=received,
                last=self._last_source_seq,
            )
            res = SequenceCheckResult(
                anomaly="REGRESSION",
                expected=expected,
                received=received,
                is_anomaly=True,
                message=f"regression {received} < {self._last_source_seq}",
            )
            self._wire_circuit(res)
            return res

        # Missing (gap)
        if received > expected:
            gap = received - expected
            if gap >= self.UNEXPECTED_JUMP_THRESHOLD:
                logger.warning(
                    "sequence_unexpected_jump",
                    instrument=self.instrument_id,
                    expected=expected,
                    received=received,
                    gap=gap,
                )
                self._remember(received)
                self._last_source_seq = received
                self._persist_last()
                res = SequenceCheckResult(
                    anomaly="UNEXPECTED_JUMP",
                    expected=expected,
                    received=received,
                    gap_size=gap,
                    is_anomaly=True,
                    message=f"unexpected jump gap {gap}",
                )
                self._wire_circuit(res)
                return res
            logger.warning("sequence_missing", instrument=self.instrument_id, expected=expected, received=received, gap=gap)
            self._remember(received)
            self._last_source_seq = received
            self._persist_last()
            res = SequenceCheckResult(
                anomaly="MISSING",
                expected=expected,
                received=received,
                gap_size=gap,
                is_anomaly=True,
                message=f"missing {gap} sequence(s)",
            )
            self._wire_circuit(res)
            return res

        # Exactly expected → healthy
        self._last_source_seq = received
        self._remember(received)
        self._persist_last()
        return SequenceCheckResult(anomaly="NONE", expected=expected, received=received, is_anomaly=False)

    def _wire_circuit(self, res: SequenceCheckResult) -> None:
        """Wire check → feed_circuit at ingestion: anomalies trip the breaker."""
        try:
            from app.signals.safety.feed_circuit import feed_circuit
            if res.is_anomaly:
                feed_circuit.on_sequence_result(self.instrument_id, res)
        except Exception:
            pass

    @property
    def last_seq(self) -> int | None:
        return self._last_source_seq

    @property
    def _last(self) -> int | None:
        return self._last_source_seq

    def reset(self, to_seq: int | None = None) -> None:
        self._last_source_seq = to_seq
        self._seen.clear()
        self._recent.clear()
        self._internal_seq = to_seq if to_seq is not None else 0
        self._persist_last()


_validators: dict[str, SequenceValidator] = {}


def get_sequence_validator(instrument_id: str, source_id: str = "broker_feed") -> SequenceValidator:
    key = f"{instrument_id.upper()}:{source_id}"
    if key not in _validators:
        _validators[key] = SequenceValidator(instrument_id, source_id)
    return _validators[key]
