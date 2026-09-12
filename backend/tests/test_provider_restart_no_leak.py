"""Restart must stop the live instance (no leaked poller emitting AUTH_EXPIRED).

Regression for the CONNECTED/AUTH_EXPIRED 1s flapping seen after FYERS
OAuth restart: restart_provider_stream() stopped _previous_provider BEFORE
reset_provider() moved the live instance there, so the old poller loop ran
forever next to the new stream.
"""

import pytest

from app.core import service_lifecycle
from app.providers import registry


class StubProvider:
    provider_name = "stub"

    def __init__(self):
        self.starts = 0
        self.stops = 0
        self.running = False

    async def start_stream(self):
        self.starts += 1
        self.running = True

    async def stop_stream(self):
        self.stops += 1
        self.running = False


@pytest.mark.asyncio
async def test_restart_stops_live_instance(monkeypatch):
    old = StubProvider()
    new = StubProvider()
    monkeypatch.setattr(registry, "_provider_instance", old)
    monkeypatch.setattr(registry, "_previous_provider", None)
    monkeypatch.setattr(registry, "_create_provider", lambda: new)

    got = await service_lifecycle.restart_provider_stream(reason="test")

    assert got is new
    assert new.starts == 1
    assert old.stops == 1, "live instance must be stopped exactly once"
    assert old.running is False
    assert registry._previous_provider is None, "previous handle must be cleared"


@pytest.mark.asyncio
async def test_restart_without_existing_instance(monkeypatch):
    new = StubProvider()
    monkeypatch.setattr(registry, "_provider_instance", None)
    monkeypatch.setattr(registry, "_previous_provider", None)
    monkeypatch.setattr(registry, "_create_provider", lambda: new)

    got = await service_lifecycle.restart_provider_stream(reason="test")

    assert got is new
    assert new.starts == 1
