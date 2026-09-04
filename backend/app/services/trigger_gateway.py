"""
State-Change Trigger Gateway — §7

Do NOT call the LLM on every tick or every candle.
Invoke AI only when meaningful events occur.

Supported triggers:
REGIME_CHANGE, BREAKOUT, BREAKDOWN, P50_S_R_CROSS, P50_VWAP_CROSS,
OI_SPIKE, VOLUME_SPIKE, OFI_SHIFT, VOLATILITY_SHIFT, NEWS_EVENT,
FORECAST_DISTRIBUTION_SHIFT, MANUAL_ANALYSIS

Adds: cooldown, event deduplication, state hashing, minimum significance thresholds, event priority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.core.market_state import hash_market_state


class TriggerType(str, Enum):
    REGIME_CHANGE = "REGIME_CHANGE"
    BREAKOUT = "BREAKOUT"
    BREAKDOWN = "BREAKDOWN"
    P50_S_R_CROSS = "P50_S_R_CROSS"
    P50_VWAP_CROSS = "P50_VWAP_CROSS"
    OI_SPIKE = "OI_SPIKE"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    OFI_SHIFT = "OFI_SHIFT"
    VOLATILITY_SHIFT = "VOLATILITY_SHIFT"
    NEWS_EVENT = "NEWS_EVENT"
    FORECAST_DISTRIBUTION_SHIFT = "FORECAST_DISTRIBUTION_SHIFT"
    MANUAL_ANALYSIS = "MANUAL_ANALYSIS"


# Priority: higher number = more urgent
TRIGGER_PRIORITY: dict[TriggerType, int] = {
    TriggerType.REGIME_CHANGE: 10,
    TriggerType.BREAKOUT: 9,
    TriggerType.BREAKDOWN: 9,
    TriggerType.NEWS_EVENT: 8,
    TriggerType.VOLATILITY_SHIFT: 7,
    TriggerType.FORECAST_DISTRIBUTION_SHIFT: 7,
    TriggerType.P50_S_R_CROSS: 6,
    TriggerType.P50_VWAP_CROSS: 6,
    TriggerType.OI_SPIKE: 5,
    TriggerType.VOLUME_SPIKE: 5,
    TriggerType.OFI_SHIFT: 5,
    TriggerType.MANUAL_ANALYSIS: 1,
}

# Minimum significance thresholds (tunable)
DEFAULT_THRESHOLDS: dict[str, float] = {
    "oi_spike_pct": 20.0,          # OI change % to be significant
    "volume_spike_multiple": 1.8,  # volume vs avg
    "volatility_shift_atr_pct": 15.0,
    "ofi_shift_delta": 0.3,
    "forecast_shift_pct": 0.5,     # P50 move % of price
    "price_breakout_atr_multiple": 0.8,
}


@dataclass
class TriggerEvent:
    trigger_type: TriggerType
    symbol: str
    state_version: int
    timestamp: datetime
    significance: float = 0.0
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    state_hash: str = ""


class TriggerGateway:
    """
    Controls AI invocation frequency per §7.
    - Cooldown per symbol+trigger
    - Event deduplication via state hashing
    - Minimum significance thresholds
    - Priority ordering
    """

    def __init__(
        self,
        cooldown_seconds: float = 60.0,
        thresholds: dict[str, float] | None = None,
    ):
        self.cooldown_seconds = cooldown_seconds
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        # last trigger time per (symbol, trigger_type)
        self._last_trigger_ts: dict[tuple[str, TriggerType], datetime] = {}
        # last state hash per symbol (dedup)
        self._last_state_hash: dict[str, str] = {}
        # recent events log (for observability)
        self._recent_events: list[TriggerEvent] = []

    def should_trigger(
        self,
        trigger_type: TriggerType,
        symbol: str,
        market_snapshot: dict,
        significance: float | None = None,
        force: bool = False,
    ) -> tuple[bool, str]:
        """
        Returns (should_call_ai: bool, reason: str)
        """
        now = datetime.now(timezone.utc)
        key = (symbol, trigger_type)

        # 1. Cooldown check (unless MANUAL_ANALYSIS forced)
        if not force and key in self._last_trigger_ts:
            elapsed = (now - self._last_trigger_ts[key]).total_seconds()
            if elapsed < self.cooldown_seconds:
                return False, f"cooldown {elapsed:.1f}s < {self.cooldown_seconds}s for {trigger_type.value}"

        # 2. Significance threshold
        if significance is not None:
            min_sig = self._get_min_significance(trigger_type)
            if significance < min_sig:
                return False, f"insignificant {significance:.3f} < {min_sig:.3f}"

        # 3. State hashing deduplication
        state_hash = hash_market_state(market_snapshot)
        if not force and self._last_state_hash.get(symbol) == state_hash:
            return False, "duplicate state_hash – no structural change"

        # 4. Otherwise trigger
        return True, "trigger approved"

    def _get_min_significance(self, trigger_type: TriggerType) -> float:
        # Map trigger to threshold
        thresholds_map = {
            TriggerType.OI_SPIKE: self.thresholds["oi_spike_pct"] / 100.0,
            TriggerType.VOLUME_SPIKE: 0.5,  # significance normalized
            TriggerType.VOLATILITY_SHIFT: self.thresholds["volatility_shift_atr_pct"] / 100.0,
            TriggerType.OFI_SHIFT: self.thresholds["ofi_shift_delta"],
            TriggerType.FORECAST_DISTRIBUTION_SHIFT: self.thresholds["forecast_shift_pct"] / 100.0,
            TriggerType.BREAKOUT: 0.5,
            TriggerType.BREAKDOWN: 0.5,
        }
        return thresholds_map.get(trigger_type, 0.0)

    def record_trigger(
        self,
        trigger_type: TriggerType,
        symbol: str,
        state_version: int,
        market_snapshot: dict,
        significance: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> TriggerEvent:
        now = datetime.now(timezone.utc)
        state_hash = hash_market_state(market_snapshot)
        event = TriggerEvent(
            trigger_type=trigger_type,
            symbol=symbol,
            state_version=state_version,
            timestamp=now,
            significance=significance,
            priority=TRIGGER_PRIORITY.get(trigger_type, 0),
            metadata=metadata or {},
            state_hash=state_hash,
        )
        self._last_trigger_ts[(symbol, trigger_type)] = now
        self._last_state_hash[symbol] = state_hash
        self._recent_events.insert(0, event)
        self._recent_events = self._recent_events[:100]
        return event

    def get_recent_events(self, limit: int = 20) -> list[TriggerEvent]:
        return self._recent_events[:limit]

    def is_cooldown_active(self, symbol: str, trigger_type: TriggerType) -> bool:
        key = (symbol, trigger_type)
        if key not in self._last_trigger_ts:
            return False
        elapsed = (datetime.now(timezone.utc) - self._last_trigger_ts[key]).total_seconds()
        return elapsed < self.cooldown_seconds


# Singleton
trigger_gateway = TriggerGateway()
