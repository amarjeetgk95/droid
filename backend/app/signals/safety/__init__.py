"""
Institutional Safety Package for Signal & Execution Engine
Provides:
  - Feed Circuit Breaker (feed_circuit)
  - Clocks & Time Integrity (get_event_clock, get_session_clock, get_monotonic_clock)
  - Sequence Validation (get_sequence_validator)
  - Exact Decimal Arithmetic (Price, Quantity, Money, normalize_price_to_tick, validate_quantity, D)
  - Global Emergency Kill Switch (kill_switch)
  - Hierarchical 15-Check Execution Guard (final_execution_guard, GuardCheckResult)
"""
from app.signals.safety.decimal_types import (
    D,
    Price,
    Quantity,
    Money,
    Rate,
    Percentage,
    TickSize,
    Notional,
    compute_notional,
    normalize_exposure,
    normalize_price_to_tick,
    validate_quantity,
    serialize_decimal,
    serialize_money,
)
from app.signals.safety.sequence_validator import (
    SequenceAnomaly,
    SequenceCheckResult,
    SequenceValidator,
    get_sequence_validator,
)
from app.signals.safety.feed_circuit import (
    FeedHealth,
    FeedState,
    FeedCircuitBreaker,
    feed_circuit,
)
from app.signals.safety.clocks import (
    ClockMetrics,
    EventClock,
    MarketSessionClock,
    MonotonicOrderingClock,
    get_event_clock,
    get_session_clock,
    get_monotonic_clock,
)
from app.signals.safety.kill_switch import (
    GlobalKillSwitch,
    kill_switch,
)
from app.signals.safety.execution_guard import (
    GuardCheckResult,
    final_execution_guard,
)

__all__ = [
    "D",
    "Price",
    "Quantity",
    "Money",
    "Rate",
    "Percentage",
    "TickSize",
    "Notional",
    "compute_notional",
    "normalize_exposure",
    "normalize_price_to_tick",
    "validate_quantity",
    "serialize_decimal",
    "serialize_money",
    "SequenceAnomaly",
    "SequenceCheckResult",
    "SequenceValidator",
    "get_sequence_validator",
    "FeedHealth",
    "FeedState",
    "FeedCircuitBreaker",
    "feed_circuit",
    "ClockMetrics",
    "EventClock",
    "MarketSessionClock",
    "MonotonicOrderingClock",
    "get_event_clock",
    "get_session_clock",
    "get_monotonic_clock",
    "GlobalKillSwitch",
    "kill_switch",
    "GuardCheckResult",
    "final_execution_guard",
]
