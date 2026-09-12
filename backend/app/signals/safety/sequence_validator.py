"""
Sequence Integrity Validator
Preserves source sequence, detects duplicate/missing/out-of-order/regression/jump.
Where source does not provide, generates deterministic internal sequence_id per source/instrument.
"""
from __future__ import annotations

from dataclasses import dataclass
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


class SequenceValidator:
    """
    Per instrument/source validator.
    Triggers: missing, duplicate, out-of-order, regression, unexpected jump.
    """
    UNEXPECTED_JUMP_THRESHOLD: int = 100

    def __init__(self, instrument_id: str, source_id: str = "broker_feed"):
        self.instrument_id = instrument_id.upper()
        self.source_id = source_id
        self._last_source_seq: int | None = None
        self._seen: set[int] = set()
        self._internal_seq: int = 0
        self._gap_detected: bool = False

    def _next_internal(self) -> int:
        self._internal_seq += 1
        return self._internal_seq

    def check(self, source_sequence_id: int | None, sequence_id: int | None = None) -> SequenceCheckResult:
        if source_sequence_id is None:
            gen = self._next_internal()
            return SequenceCheckResult(
                anomaly="NONE",
                expected=None,
                received=gen,
                is_anomaly=False,
                message="generated internal sequence",
            )

        received = source_sequence_id

        # Duplicate detection
        if received in self._seen:
            logger.warning("sequence_duplicate", instrument=self.instrument_id, seq=received)
            return SequenceCheckResult(
                anomaly="DUPLICATE",
                expected=self._last_source_seq,
                received=received,
                is_anomaly=True,
                message=f"duplicate sequence {received}",
            )

        # First observation
        if self._last_source_seq is None:
            self._last_source_seq = received
            self._seen.add(received)
            if len(self._seen) > 10000:
                self._seen = set(list(self._seen)[-5000:])
            return SequenceCheckResult(anomaly="NONE", expected=None, received=received)

        expected = self._last_source_seq + 1

        # Regression (received < last)
        if received < self._last_source_seq:
            logger.warning(
                "sequence_regression",
                instrument=self.instrument_id,
                expected=expected,
                received=received,
                last=self._last_source_seq,
            )
            return SequenceCheckResult(
                anomaly="REGRESSION",
                expected=expected,
                received=received,
                is_anomaly=True,
                message=f"regression {received} < {self._last_source_seq}",
            )

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
                self._seen.add(received)
                self._last_source_seq = received
                return SequenceCheckResult(
                    anomaly="UNEXPECTED_JUMP",
                    expected=expected,
                    received=received,
                    gap_size=gap,
                    is_anomaly=True,
                    message=f"unexpected jump gap {gap}",
                )
            logger.warning("sequence_missing", instrument=self.instrument_id, expected=expected, received=received, gap=gap)
            self._seen.add(received)
            self._last_source_seq = received
            if len(self._seen) > 10000:
                self._seen = set(list(self._seen)[-5000:])
            return SequenceCheckResult(
                anomaly="MISSING",
                expected=expected,
                received=received,
                gap_size=gap,
                is_anomaly=True,
                message=f"missing {gap} sequence(s)",
            )

        # Exactly expected → healthy
        self._last_source_seq = received
        self._seen.add(received)
        if len(self._seen) > 10000:
            self._seen = set(list(self._seen)[-5000:])
        return SequenceCheckResult(anomaly="NONE", expected=expected, received=received, is_anomaly=False)

    @property
    def last_seq(self) -> int | None:
        return self._last_source_seq

    def reset(self, to_seq: int | None = None) -> None:
        self._last_source_seq = to_seq
        self._seen.clear()
        self._internal_seq = to_seq if to_seq is not None else 0


_validators: dict[str, SequenceValidator] = {}


def get_sequence_validator(instrument_id: str, source_id: str = "broker_feed") -> SequenceValidator:
    key = f"{instrument_id.upper()}:{source_id}"
    if key not in _validators:
        _validators[key] = SequenceValidator(instrument_id, source_id)
    return _validators[key]
