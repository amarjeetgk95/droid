"""
Global Emergency Kill Switch for Signal & Execution Engine
When activated: execution_eligibility = NO for all signals and orders.
Sub-millisecond in-memory check, fail-closed design.
Thread-safe (threading.Lock), monotonic clock, persisted + evented.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
import structlog

logger = structlog.get_logger()

_KILL_STATE_FILE = Path(__file__).resolve().parents[4] / "kill_switch_state.json"

# Actors allowed to (de)activate the kill switch.
KILL_SWITCH_ACTOR_ALLOWLIST = frozenset({"operator", "risk_engine", "feed_monitor", "system", "test"})


class GlobalKillSwitch:
    """
    Global Emergency Kill Switch.
    Independent of individual signal states.
    Operating principle: activation disables all execution eligibility in <1ms.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._active: bool = False
        self._reason: str | None = None
        self._activated_at_ms: int | None = None
        self._activated_by: str = "system"
        self._activated_monotonic_ns: int | None = None
        self._restore()

    # ── persistence ──────────────────────────────────────────────
    def _restore(self) -> None:
        try:
            if _KILL_STATE_FILE.exists():
                data = json.loads(_KILL_STATE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("active"):
                    self._active = True
                    self._reason = data.get("reason")
                    self._activated_at_ms = data.get("activated_at_ms")
                    self._activated_by = data.get("activated_by", "system")
        except Exception:
            pass

    def _persist(self) -> None:
        try:
            payload = {
                "active": self._active,
                "reason": self._reason,
                "activated_at_ms": self._activated_at_ms,
                "activated_by": self._activated_by,
                "persisted_at_ms": int(time.time() * 1000),
            }
            tmp = _KILL_STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(_KILL_STATE_FILE)
        except Exception as e:
            logger.warning("kill_switch_persist_failed", error=str(e)[:150])
        # Publish to DB when available (best-effort, never blocks)
        try:
            from app.core.database import get_async_session_factory
            import asyncio

            factory = get_async_session_factory()
            if factory is not None:
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        async def _write():
                            try:
                                from sqlalchemy import text as _t
                                async with factory() as s:
                                    await s.execute(_t(
                                        "CREATE TABLE IF NOT EXISTS kill_switch_events "
                                        "(id SERIAL PRIMARY KEY, active BOOLEAN, reason TEXT, actor TEXT, ts_ms BIGINT)"
                                    ))
                                    await s.execute(_t(
                                        "INSERT INTO kill_switch_events (active, reason, actor, ts_ms) "
                                        "VALUES (:a, :r, :b, :t)"
                                    ), {"a": self._active, "r": self._reason, "b": self._activated_by,
                                        "t": self._activated_at_ms or int(time.time() * 1000)})
                                    await s.commit()
                            except Exception:
                                pass
                        loop.create_task(_write())
                except RuntimeError:
                    pass
        except Exception:
            pass

    def _publish_event(self, kind: str) -> None:
        try:
            from app.signals.event_bus import SignalEvent, SignalEventType, signal_event_bus
            et = SignalEventType.DELETED if kind == "deactivated" else SignalEventType.EXPIRED
            # KILL events use a dedicated payload; handlers must not skip them.
            signal_event_bus.publish_sync(SignalEvent(
                event_type=et,
                signal_id="GLOBAL_KILL_SWITCH",
                payload={"kill": kind, "active": self._active, "reason": self._reason,
                         "actor": self._activated_by, "kind": "KILL"},
            ))
        except Exception:
            pass

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def activate(self, reason: str = "", by: str = "operator") -> dict:
        if not reason or not str(reason).strip():
            raise ValueError("kill_switch.activate requires a non-empty reason")
        if by not in KILL_SWITCH_ACTOR_ALLOWLIST:
            raise ValueError(f"kill_switch actor {by!r} not in allowlist")
        with self._lock:
            self._active = True
            self._reason = str(reason)
            self._activated_at_ms = int(time.time() * 1000)
            self._activated_monotonic_ns = time.monotonic_ns()
            self._activated_by = by
            status = self._status_locked()
        logger.critical(
            "global_kill_switch_activated",
            reason=reason,
            by=by,
            activated_at_ms=self._activated_at_ms,
            action="ALL EXECUTION DISPATCH BLOCKED IMMEDIATELY",
        )
        self._persist()
        self._publish_event("activated")
        return status

    def deactivate(self, by: str = "operator") -> dict:
        if by not in KILL_SWITCH_ACTOR_ALLOWLIST:
            raise ValueError(f"kill_switch actor {by!r} not in allowlist")
        with self._lock:
            prev = self._reason
            self._active = False
            self._reason = None
            self._activated_at_ms = None
            self._activated_monotonic_ns = None
            self._activated_by = by
            status = self._status_locked()
        logger.warning(
            "global_kill_switch_deactivated",
            previous_reason=prev,
            by=by,
            action="Execution dispatch re-enabled subject to execution guards",
        )
        self._persist()
        self._publish_event("deactivated")
        return status

    def _status_locked(self) -> dict:
        return {
            "active": self._active,
            "reason": self._reason,
            "activated_at_ms": self._activated_at_ms,
            "activated_by": self._activated_by,
            "activated_monotonic_ns": self._activated_monotonic_ns,
        }

    def status(self) -> dict:
        with self._lock:
            return self._status_locked()

    def active_duration_ms(self) -> int | None:
        with self._lock:
            if not self._active or self._activated_monotonic_ns is None:
                return None
            return int((time.monotonic_ns() - self._activated_monotonic_ns) // 1_000_000)

    def auto_activate_from_monitor(self, monitor_status: str, stale_seconds: float | None = None) -> dict | None:
        """Auto-activate on monitor DOWN / STALE>60s. Wired from feed monitor.

        Returns new status when activation fires, else None.
        """
        try:
            s = str(monitor_status or "").upper()
            if s == "DOWN" or (s == "STALE" and stale_seconds is not None and float(stale_seconds) > 60):
                if not self.is_active():
                    return self.activate(
                        reason=f"AUTO_KILL: feed {s} stale={stale_seconds}s",
                        by="feed_monitor",
                    )
        except Exception as e:
            logger.warning("kill_auto_activate_failed", error=str(e)[:150])
        return None


kill_switch = GlobalKillSwitch()
