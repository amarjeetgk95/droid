"""Tests for ML Challenger & Model Info Endpoints."""
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_ml_model_info():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/ml/model-info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["horizon_minutes"] == 15
        assert data["data"]["artifacts"]["xgb_exists"] is True
        assert data["data"]["artifacts"]["lgb_exists"] is True


@pytest.mark.asyncio
async def test_ml_challenger_info():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/ml/challenger-info")
        assert resp.status_code == 200
        data = resp.json()
        assert "challenger_models" in data["data"]
        manifests = data["data"]["challenger_models"]
        assert "regime_meta" in manifests
        assert "direction_h15_meta" in manifests


@pytest.mark.asyncio
async def test_ml_current_regime():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/ml/current-regime")
        assert resp.status_code == 200
        data = resp.json()
        assert "regime" in data["data"]
        assert "probabilities" in data["data"]
        probs = data["data"]["probabilities"]
        assert sum(probs.values()) > 0.99


@pytest.mark.asyncio
async def test_ml_champion_info():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/ml/champion-info")
        assert resp.status_code == 200
        data = resp.json()
        assert "champion_models" in data["data"]
        manifests = data["data"]["champion_models"]
        assert "trade_outcome_meta" in manifests
        assert "breakout_meta" in manifests
