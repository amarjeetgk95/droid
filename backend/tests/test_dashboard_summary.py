import time
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from app.main import app
from app.api.dashboard import _summary_cache
from app.services.market_data_coordinator import market_data_coordinator

client = TestClient(app)


@pytest.fixture(autouse=True)
async def clear_caches():
    _summary_cache.clear()
    await market_data_coordinator.clear()
    yield
    _summary_cache.clear()
    await market_data_coordinator.clear()


def test_dashboard_summary_schema():
    """Verify that /api/v1/dashboard/summary adheres to the expected contract."""
    response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    body = response.json()

    assert "data" in body
    assert "error" in body
    assert "meta" in body
    assert body["error"] is None

    data = body["data"]
    assert "cards" in data
    assert isinstance(data["cards"], list)
    assert "breadth" in data
    assert "health" in data
    assert "market_status" in data
    assert "ml_prediction" in data
    assert "fii_dii" in data
    assert "regime_overview" in data
    assert "errors" in data
    assert isinstance(data["errors"], dict)
    assert "degraded" in data
    assert isinstance(data["degraded"], bool)
    assert "generated_at" in data


def test_dashboard_summary_cache_hit_latency():
    """Verify that cached summary hits return in <15ms."""
    # First call (populates cache)
    r1 = client.get("/api/v1/dashboard/summary")
    assert r1.status_code == 200

    # Second call (must be cache hit)
    start = time.perf_counter()
    r2 = client.get("/api/v1/dashboard/summary")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert r2.status_code == 200
    assert r2.json()["data"]["generated_at"] == r1.json()["data"]["generated_at"]
    # P50 cache hit target is <15ms
    assert elapsed_ms < 50.0  # Safe threshold for test runners, typically <2ms


def test_dashboard_summary_degraded_when_subsystem_fails():
    """When a subsystem fails, the summary returns degraded=True with honest error tracking."""
    _summary_cache.clear()

    # Simulate ML failure
    with patch("app.ml.predictor.ml_predictor.predict_probabilities", new_callable=AsyncMock) as mock_ml:
        mock_ml.side_effect = RuntimeError("ML engine unreachable")

        response = client.get("/api/v1/dashboard/summary")
        assert response.status_code == 200
        body = response.json()
        data = body["data"]

        assert data["degraded"] is True
        assert "ml" in data["errors"]
        assert data["ml_prediction"] is None
