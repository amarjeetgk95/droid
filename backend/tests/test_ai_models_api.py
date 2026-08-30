from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.services.openrouter_catalog import clear_cache
import pytest

client = TestClient(app)

SAMPLE_FIN_FREE = {
    "id": "inclusionai/ling-3.0-flash-fin:free",
    "name": "Ling 3.0 Flash Fin",
    "description": "Finance-specialized model",
    "pricing": {"prompt": "0", "completion": "0"},
    "context_length": 262144,
    "architecture": {"input_modalities": ["text"]},
    "supported_parameters": ["tools"],
}
SAMPLE_PAID = {
    "id": "anthropic/claude-3.7-sonnet",
    "name": "Claude 3.7 Sonnet",
    "pricing": {"prompt": "0.003", "completion": "0.015"},
    "context_length": 200000,
    "architecture": {"input_modalities": ["text"]},
}
SAMPLE_REASON_FREE = {
    "id": "deepseek/deepseek-r1:free",
    "name": "DeepSeek R1",
    "description": "reasoning",
    "pricing": {"prompt": "0", "completion": "0"},
    "context_length": 131072,
    "architecture": {"input_modalities": ["text"]},
}


@pytest.mark.asyncio
async def test_models_endpoint_free_only():
    await clear_cache()
    with patch("app.services.openrouter_catalog.fetch_openrouter_catalog_raw", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [SAMPLE_FIN_FREE, SAMPLE_PAID, SAMPLE_REASON_FREE]
        with patch("app.api.ai.get_model_catalog") as mock_cat:
            # Actually test via httpx mock inside get_model_catalog; easier to mock fetch
            pass
        # Directly call endpoint; it will call get_model_catalog which will call mocked fetch
        response = client.get("/api/v1/ai/models?free_only=true")
        # Note: need async handling? TestClient runs sync, but get_model_catalog is async. Mock needs to be setup before.
        # Instead we patch fetch...
        # We'll do manual mocking via patch in endpoint call
        pass

# Simpler sync tests using monkeypatch of catalog fetch
def test_models_api_free_filter():
    import asyncio
    # Use TestClient with mocked service
    async def mock_catalog(*args, **kwargs):
        from datetime import datetime, timezone
        return {
            "provider": "openrouter",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "free_only": True,
            "pricing_filter": "FREE",
            "models": [
                {
                    "id": SAMPLE_FIN_FREE["id"],
                    "name": SAMPLE_FIN_FREE["name"],
                    "is_free": True,
                    "context_length": 262144,
                    "input_price": 0,
                    "output_price": 0,
                    "pricing": {"prompt": "0", "completion": "0"},
                    "supports_tools": True,
                    "supports_vision": False,
                    "description": "Finance",
                    "category": "Finance",
                    "trading_rank": 150,
                    "recommended_for_trading": True,
                    "badges": ["FREE", "FINANCE"],
                    "architecture": {},
                }
            ],
            "default_model": {
                "id": SAMPLE_FIN_FREE["id"],
                "name": SAMPLE_FIN_FREE["name"],
                "is_free": True,
                "category": "Finance",
                "trading_rank": 150,
                "recommended_for_trading": True,
            },
            "total_count": 1,
            "free_count": 1,
            "paid_count": 0,
            "using_cached": False,
            "cache_age_seconds": 0,
        }

    with patch("app.api.ai.get_model_catalog", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = asyncio.run(mock_catalog()) if False else mock_catalog  # tricky
        # Use proper async mock
        import asyncio
        mock_get.side_effect = lambda *a, **kw: mock_catalog(*a, **kw)

        # Need to handle async: patch with AsyncMock returning dict
        async def ret(*a, **kw):
            return await mock_catalog(*a, **kw)
        mock_get.side_effect = ret

        # Actually simpler: use patch with AsyncMock
        with patch("app.api.ai.get_model_catalog", new_callable=AsyncMock) as m2:
            # Setup return
            async def fake_catalog(*a, **kw):
                from datetime import datetime, timezone
                return {
                    "provider": "openrouter",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "free_only": True,
                    "pricing_filter": "FREE",
                    "models": [
                        {
                            "id": SAMPLE_FIN_FREE["id"],
                            "name": SAMPLE_FIN_FREE["name"],
                            "is_free": True,
                            "context_length": 262144,
                            "input_price": 0,
                            "output_price": 0,
                            "pricing": {"prompt": "0", "completion": "0"},
                            "supports_tools": True,
                            "supports_vision": False,
                            "description": "Finance",
                            "category": "Finance",
                            "trading_rank": 150,
                            "recommended_for_trading": True,
                            "badges": ["FREE", "FINANCE"],
                            "architecture": {},
                        }
                    ],
                    "default_model": {
                        "id": SAMPLE_FIN_FREE["id"],
                        "name": SAMPLE_FIN_FREE["name"],
                        "is_free": True,
                        "category": "Finance",
                        "trading_rank": 150,
                        "recommended_for_trading": True,
                    },
                    "total_count": 1,
                    "free_count": 1,
                    "paid_count": 0,
                    "using_cached": False,
                    "cache_age_seconds": 0,
                }
            m2.side_effect = fake_catalog
            r = client.get("/api/v1/ai/models")
            assert r.status_code == 200
            body = r.json()
            assert "data" in body
            assert body["data"]["provider"] == "openrouter"
            assert body["data"]["free_only"] is True
            assert len(body["data"]["models"]) == 1
            assert body["data"]["models"][0]["is_free"] is True
            assert body["data"]["default_model"]["id"] == SAMPLE_FIN_FREE["id"]
            # Check fields per spec
            m = body["data"]["models"][0]
            assert "id" in m
            assert "name" in m
            assert "is_free" in m
            assert "context_length" in m
            assert "input_price" in m
            assert "output_price" in m
            assert "supports_tools" in m
            assert "supports_vision" in m
            assert "category" in m
            assert "trading_rank" in m
            assert "recommended_for_trading" in m


def test_compat_alias():
    # Test /api/ai/models compat
    async def fake_catalog(*a, **kw):
        from datetime import datetime, timezone
        return {
            "provider": "openrouter",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "free_only": True,
            "pricing_filter": "FREE",
            "models": [],
            "default_model": None,
            "total_count": 0,
            "free_count": 0,
            "paid_count": 0,
            "using_cached": False,
            "cache_age_seconds": 0,
        }
    with patch("app.api.ai.get_model_catalog", new_callable=AsyncMock) as m2:
        m2.side_effect = fake_catalog
        r = client.get("/api/ai/models")
        assert r.status_code == 200
        assert r.json()["data"]["provider"] == "openrouter"


def test_paid_protection_rejects():
    # Test /api/v1/ai/analyze with paid model while free_only=true -> 403
    async def fake_validate(*a, **kw):
        raise ValueError("Paid models are disabled. Select a currently free OpenRouter model.")
    with patch("app.api.ai.validate_model_or_raise", new_callable=AsyncMock) as m:
        m.side_effect = fake_validate
        r = client.post("/api/v1/ai/analyze", json={"model": "anthropic/claude-3.7-sonnet", "symbol": "NIFTY"})
        assert r.status_code == 403
        assert "Paid models are disabled" in r.json()["detail"]


def test_no_free_model_error():
    async def fake_validate(*a, **kw):
        raise ValueError("No eligible free model is currently available.")
    with patch("app.api.ai.validate_model_or_raise", new_callable=AsyncMock) as m:
        m.side_effect = fake_validate
        r = client.post("/api/v1/ai/analyze", json={"model": "auto", "symbol": "NIFTY"})
        assert r.status_code == 403
        assert "No eligible free model" in r.json()["detail"]


def test_analyze_free_model_success_mocked():
    # Mock successful analysis
    from app.models.ai import AIInsightResponse
    from datetime import datetime, timezone
    fake_insight = AIInsightResponse(
        symbol="NIFTY",
        timestamp=datetime.now(timezone.utc),
        market_bias="BULLISH",
        confidence=85.0,
        executive_summary="Test summary",
        options_interpretation="opt",
        futures_flow_analysis="fut",
        regime_and_levels="reg",
        recommended_strategy_framework="strat",
        risk_management_notes="risk",
        provider_used="openrouter:inclusionai/ling-3.0-flash-fin:free",
    )
    async def fake_validate_ok(*a, **kw):
        return {"id": "inclusionai/ling-3.0-flash-fin:free", "is_free": True}
    async def fake_gen(*a, **kw):
        return fake_insight
    with patch("app.api.ai.validate_model_or_raise", new_callable=AsyncMock) as m1:
        m1.side_effect = fake_validate_ok
        with patch("app.services.ai_service.ai_service.generate_market_analysis", new_callable=AsyncMock) as m2:
            m2.return_value = fake_insight
            r = client.post("/api/v1/ai/analyze", json={"model": "inclusionai/ling-3.0-flash-fin:free", "symbol": "NIFTY"})
            assert r.status_code == 200
            body = r.json()
            assert body["data"]["symbol"] == "NIFTY"
            assert body["data"]["market_bias"] == "BULLISH"
