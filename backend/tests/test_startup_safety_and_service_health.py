"""Startup-safety and service-readiness contracts.

Pins the guarantees the local CMD runtime relies on:
  - the single-instance port probe (free / occupied / released),
  - the pytest skip so TestClient boots never trip the guard,
  - the dev-bypass bind-posture guard,
  - the /live and /ready alias contracts (top-level, cheap, honest).
"""
from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from app.core.startup_safety import (
    PortConflictError,
    assert_safe_bind_posture,
    assert_single_instance,
    probe_port_available,
)


def _listener(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, port))
    sock.listen(1)
    return sock


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class TestSingleInstancePortGuard:
    def test_free_port_is_reported_available(self):
        port = _free_port()
        free, detail = probe_port_available("127.0.0.1", port)
        assert free is True
        assert detail == ""

    def test_occupied_port_is_reported_unavailable_and_released(self):
        port = _free_port()
        listener = _listener("127.0.0.1", port)
        try:
            free, detail = probe_port_available("127.0.0.1", port)
            assert free is False
            assert "already in use" in detail
        finally:
            listener.close()
        # The probe socket must always be released, never left bound.
        free, _ = probe_port_available("127.0.0.1", port)
        assert free is True

    def test_assert_single_instance_raises_on_conflict(self):
        port = _free_port()
        listener = _listener("127.0.0.1", port)
        try:
            with pytest.raises(PortConflictError):
                assert_single_instance("127.0.0.1", port)
        finally:
            listener.close()

    def test_assert_single_instance_passes_when_free(self):
        assert_single_instance("127.0.0.1", _free_port())


class TestBindPostureGuard:
    def test_loopback_with_dev_bypass_is_allowed(self):
        # Default settings bind to 127.0.0.1 with AUTH_REQUIRED=false — valid.
        assert_safe_bind_posture()

    def test_nonloopback_dev_bypass_is_refused(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "backend_host", "0.0.0.0")
        monkeypatch.setattr(settings, "auth_required", False)
        monkeypatch.setattr(settings, "app_env", "development")
        monkeypatch.setattr(settings, "app_mode", "development")
        with pytest.raises(RuntimeError, match="Unsafe bind posture"):
            assert_safe_bind_posture()

    def test_nonloopback_production_is_allowed(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "backend_host", "0.0.0.0")
        monkeypatch.setattr(settings, "auth_required", False)
        # Production suppresses the dev bypass, so the bind is not unsafe.
        monkeypatch.setattr(settings, "app_env", "production")
        assert_safe_bind_posture()


@pytest.fixture()
def client() -> TestClient:
    # Portal-less TestClient (no context manager): the lifespan is NOT run —
    # these contracts target the deployment-independent HTTP surface, and a
    # full lifespan boot costs ~50 s of FYERS retry waits.
    return TestClient(
        __import__("app.main", fromlist=["app"]).app, raise_server_exceptions=False
    )


class TestServiceHealthAliases:
    def test_live_alias_matches_health_live(self, client):
        r_live = client.get("/live")
        r_hl = client.get("/health/live")
        assert r_live.status_code == r_hl.status_code == 200
        assert r_live.json()["status"] == "ok"

    def test_ready_alias_tracks_health_ready(self, client):
        # Without a lifespan the central feed is down → honest 503 on BOTH.
        # Bodies agree except the timestamp (two probes, two instants).
        r_ready = client.get("/ready")
        r_hr = client.get("/health/ready")
        assert r_ready.status_code == r_hr.status_code
        b1, b2 = r_ready.json(), r_hr.json()
        b1.pop("timestamp"), b2.pop("timestamp")
        assert b1 == b2

    def test_ready_includes_dependency_checks(self, client):
        body = client.get("/ready").json()
        for key in ("central_feed", "database", "signal_worker", "trading_posture"):
            assert key in body["checks"]
        assert body["checks"]["trading_posture"] == "paper_first"
