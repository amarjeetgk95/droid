"""
Sequence Integrity — Re-exports canonical implementation from app.signals.safety.sequence_validator.
Maintained for backward compatibility.
"""
from app.signals.safety.sequence_validator import (
    SequenceAnomaly,
    SequenceCheckResult,
    SequenceValidator,
    get_sequence_validator,
)

__all__ = [
    "SequenceAnomaly",
    "SequenceCheckResult",
    "SequenceValidator",
    "get_sequence_validator",
]
