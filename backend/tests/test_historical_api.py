"""Tests for Historical Data REST API endpoints."""

import pytest
from starlette.testclient import TestClient
from app.main import app
from app.historical_data.storage.db_repository import db_repo
from app.historical_data.models.dataset import HistoricalDataset


@pytest.fixture
def client():
    return TestClient(app)


def test_list_datasets_endpoint(client):
    response = client.get("/api/v1/historical-data/datasets")
    assert response.status_code == 200
    data = response.json()
    assert "datasets" in data
    assert isinstance(data["datasets"], list)


def test_get_jobs_endpoint(client):
    response = client.get("/api/v1/historical-data/jobs")
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert isinstance(data["jobs"], list)


def test_trigger_download_endpoint(client):
    payload = {
        "symbol": "SENSEX",
        "timeframe": "1m",
        "range_from": "2026-01-01",
        "range_to": "2026-01-10",
        "force_refresh": True,
    }
    response = client.post("/api/v1/historical-data/download", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "enqueued"
    assert "job" in data
    assert data["job"]["symbol"] == "SENSEX"
