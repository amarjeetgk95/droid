"""Startup safety checks for the DROID backend.

Runs at the very top of the app lifespan, BEFORE any engine/worker starts:

  1. Single-instance port guard — refuse to boot a second backend instance
     on the same 127.0.0.1:8000 address. Uvicorn binds sockets with
     SO_REUSEADDR, and on Windows a second SO_REUSEADDR bind SUCCEEDS, so two
     backends can silently share one port and split the tick feed. The probe
     here binds WITHOUT SO_REUSEADDR, which fails (WinError 10048) while any
     real listener holds the port, then immediately releases it. This makes
     two backends impossible instead of silent — the usual cause is a leftover
     'DROID backend :8000' window (or a raw uvicorn command) from another shell.

     Placement is load-bearing: uvicorn runs the FastAPI lifespan BEFORE it
     binds its own sockets, and on a lifespan exception it exits with
     STARTUP_FAILURE without leaving a half-bound listener behind. So a
     RuntimeError raised here fails the service start cleanly (WinSW logs it
     and honours the 10 s restart cooldown), and no worker ever starts.

  2. Dev-bypass posture guard — refuse to serve the anonymous dev-admin over
     a non-loopback bind (suppressed in production; loopback-only otherwise).

  3. Trading-safety posture log — an explicit, persisted startup record of
     the effective trading posture. The backend is paper-oriented by design:
     the signal engine auto-executes to the PAPER book only (see
     app/signals/paper_engine.py), and live order transmission requires the
     explicit live-adapter path (app/algo/execution.py, fail-closed).
     No runtime flag is flipped here — this only makes the posture VISIBLE
     and verifies the fail-closed defaults are in place.

No external service is contacted: these checks are local, fast (< 50 ms)
and never depend on FYERS/Supabase availability.
"""
from __future__ import annotations

import logging
import socket
import sys

import structlog

from app.core.config import settings

logger = structlog.get_logger()

_log = logging.getLogger(__name__)


class PortConflictError(RuntimeError):
    """Another listener already holds the backend address."""


def probe_port_available(host: str, port: int) -> tuple[bool, str]:
    """Check whether host:port is free to bind, without binding permanently.

    Binds WITHOUT SO_REUSEADDR: on Windows that fails with 10048 while any
    real listener (including a uvicorn instance using SO_REUSEADDR) holds the
    port. The socket is always closed before returning — the port is never
    left occupied.

    Returns (is_free, detail_message). Never raises.
    """
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind((host, port))
            probe.listen(1)
        finally:
            probe.close()
        return True, ""
    except OSError as exc:
        winerror = getattr(exc, "winerror", None)
        if winerror == 10048 or exc.errno in (48, 98):
            return False, f"{host}:{port} is already in use (WinError 10048)"
        return False, f"{host}:{port} probe failed: {exc}"


def assert_single_instance(host: str | None = None, port: int | None = None) -> None:
    """Fail the startup (raise PortConflictError) when the address is taken.

    The no-argument form (used by the lifespan) is skipped under pytest:
    TestClient boots the lifespan without binding any socket, so the guard
    must not run there (and the real backend may legitimately be listening
    on 8000 while the suite runs). Explicit host/port calls are always
    enforced, so the guard itself stays unit-testable.
    """
    if host is None and port is None and "pytest" in sys.modules:
        return
    host = host or settings.backend_host
    port = port if port is not None else settings.backend_port

    free, detail = probe_port_available(host, port)
    if not free:
        logger.error(
            "startup_single_instance_guard_failed",
            host=host,
            port=port,
            detail=detail,
            hint=(
                "Another DROID backend is probably running. Stop the other instance "
                "first: close the 'DROID backend :8000' window, or find its PID with "
                "`netstat -ano | findstr :8000` and end that task."
            ),
        )
        raise PortConflictError(
            f"Cannot start: {detail}. Stop the other backend instance first "
            "(close the 'DROID backend :8000' window, or netstat -ano | findstr :8000)."
        )
    logger.info("startup_single_instance_guard_ok", host=host, port=port)


def assert_safe_bind_posture() -> None:
    """Refuse the anonymous dev-admin posture on a non-loopback bind.

    Mirrors the auth middleware: the dev bypass only serves loopback Host
    requests, so binding to 0.0.0.0 with AUTH_REQUIRED=false would advertise
    an unauthenticated admin API to the LAN. Fail loud instead.
    """
    host = settings.backend_host
    loopback = host in ("127.0.0.1", "localhost", "::1")
    if not settings.auth_required and not loopback and "production" not in {
        settings.app_env,
        settings.app_mode,
    }:
        logger.error(
            "startup_unsafe_bind_posture",
            host=host,
            auth_required=settings.auth_required,
            hint=(
                "AUTH_REQUIRED=false with a non-loopback bind would expose the "
                "anonymous dev-admin to the network. Set AUTH_REQUIRED=true or "
                "bind to 127.0.0.1 (BACKEND_HOST)."
            ),
        )
        raise RuntimeError(
            f"Unsafe bind posture: BACKEND_HOST={host} with AUTH_REQUIRED=false. "
            "Bind to 127.0.0.1 or set AUTH_REQUIRED=true."
        )


def log_trading_safety_posture() -> None:
    """Log the effective trading posture as an explicit startup record.

    Paper-first by construction (no flag flips here): the signal engine's
    automated execution goes to the paper book; the live broker adapter is a
    separate, fail-closed path that requires explicit credentials AND an
    explicit API call — a plain backend restart can never arm it by itself.
    Restarting the service therefore cannot silently enable live trading.
    """
    posture = {
        "mode": "paper_first",
        "app_env": settings.app_env,
        "app_mode": settings.app_mode,
        "institutional_live_mode": bool(settings.institutional_live_mode),
        "in_production": "production" in {settings.app_env, settings.app_mode},
    }
    logger.info("startup_trading_safety_posture", **posture)
    if posture["institutional_live_mode"]:
        # Loud on purpose: this is the one flag that relaxes fail-closed
        # behaviour, so a restart must surface it unmissably.
        logger.warning(
            "startup_live_mode_flag_active",
            detail="INSTITUTIONAL_LIVE_MODE=true is persisted in configuration.",
        )
    # Belt-and-braces: the execution guard must be importable and wired, or
    # the paper-first claim is hollow.
    try:
        from app.signals.safety.execution_guard import final_execution_guard  # noqa: F401

        _log.debug("startup_execution_guard_importable")
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("startup_execution_guard_import_failed", error=str(exc)[:200])
