"""
Cooldown Manager (§37) & Signal Deduplication (§36).

Prevents revenge scalping and multiple redundant signals emitted during the
same single compression-release event.
"""
from __future__ import annotations

import time
from typing import Dict, Optional, Set
from pydantic import BaseModel, Field


class CooldownManager:
    """Manages post-trade and post-event cooling off periods."""

    def __init__(
        self,
        target_cooldown_seconds: int = 120,
        stop_cooldown_seconds: int = 300,
        invalidation_cooldown_seconds: int = 180,
    ) -> None:
        self.target_cooldown = target_cooldown_seconds
        self.stop_cooldown = stop_cooldown_seconds
        self.invalidation_cooldown = invalidation_cooldown_seconds
        # instrument -> expiry_timestamp_ms
        self._cooldowns: Dict[str, int] = {}

    def trigger_cooldown(self, instrument: str, reason: str, timestamp_ms: int) -> None:
        """Set a cooldown timer for an instrument."""
        if reason in ("TARGET", "TARGET_1", "TARGET_2"):
            cd_secs = self.target_cooldown
        elif reason in ("STOP", "STOP_LOSS", "TRAP_FAIL"):
            cd_secs = self.stop_cooldown
        else:
            cd_secs = self.invalidation_cooldown

        self._cooldowns[instrument] = timestamp_ms + (cd_secs * 1000)

    def is_in_cooldown(self, instrument: str, timestamp_ms: int) -> bool:
        """Check if an instrument is currently under an active cooldown window."""
        expiry = self._cooldowns.get(instrument, 0)
        return timestamp_ms < expiry

    def reset(self, instrument: Optional[str] = None) -> None:
        """Reset cooldown state."""
        if instrument:
            self._cooldowns.pop(instrument, None)
        else:
            self._cooldowns.clear()


class SignalDeduplicator:
    """Enforces one primary signal per compression-release event (§36)."""

    def __init__(self, event_ttl_seconds: int = 600) -> None:
        self.event_ttl_ms = event_ttl_seconds * 1000
        # event_key -> trigger_timestamp_ms
        self._active_events: Dict[str, int] = {}

    def is_duplicate(
        self,
        instrument: str,
        level_price: float,
        direction: int,
        timestamp_ms: int,
    ) -> bool:
        """Check if a signal for this level and direction was already emitted recently."""
        # Round level price to avoid micro-float diffs
        event_key = f"{instrument}_{round(level_price, 1)}_{direction}"

        # Clean expired events
        expired = [k for k, exp_t in self._active_events.items() if timestamp_ms - exp_t > self.event_ttl_ms]
        for k in expired:
            del self._active_events[k]

        if event_key in self._active_events:
            return True

        # Register event
        self._active_events[event_key] = timestamp_ms
        return False

    def reset(self) -> None:
        self._active_events.clear()
