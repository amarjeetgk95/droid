"""
Global Emergency Kill Switch for Signal & Execution Engine
When activated: execution_eligibility = NO for all signals and orders.
Sub-millisecond in-memory check, fail-closed design.
"""
from __future__ import annotations

import time
import structlog

logger = structlog.get_logger()


class GlobalKillSwitch:
    """
    Global Emergency Kill Switch.
    Independent of individual signal states.
    Operating principle: activation disables all execution eligibility in <1ms.
    """
    def __init__(self):
        self._active: bool = False
        self._reason: str | None = None
        self._activated_at_ms: int | None = None
        self._activated_by: str = "system"

    def is_active(self) -> bool:
        return self._active

    def activate(self, reason: str = "Emergency manual trigger", by: str = "operator") -> dict:
        self._active = True
        self._reason = reason
        self._activated_at_ms = int(time.time() * 1000)
        self._activated_by = by
        logger.critical(
            "global_kill_switch_activated",
            reason=reason,
            by=by,
            activated_at_ms=self._activated_at_ms,
            action="ALL EXECUTION DISPATCH BLOCKED IMMEDIATELY",
        )
        return self.status()

    def deactivate(self, by: str = "operator") -> dict:
        logger.warning(
            "global_kill_switch_deactivated",
            previous_reason=self._reason,
            by=by,
            action="Execution dispatch re-enabled subject to execution guards",
        )
        self._active = False
        self._reason = None
        self._activated_at_ms = None
        self._activated_by = by
        return self.status()

    def status(self) -> dict:
        return {
            "active": self._active,
            "reason": self._reason,
            "activated_at_ms": self._activated_at_ms,
            "activated_by": self._activated_by,
        }


kill_switch = GlobalKillSwitch()
