"""
Feed Circuit Breaker — Re-exports canonical implementation from app.signals.safety.feed_circuit.
Maintained for backward compatibility.
"""
from app.signals.safety.feed_circuit import (
    FeedHealth,
    FeedState,
    FeedCircuitBreaker,
    feed_circuit,
)

__all__ = [
    "FeedHealth",
    "FeedState",
    "FeedCircuitBreaker",
    "feed_circuit",
]
