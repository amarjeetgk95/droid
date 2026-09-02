import pytest
from app.services.ai_strategy_service import ai_strategy_service
from app.services.ai_validation_service import ai_validation_service
from app.models.ai import AIOptionsStrategyRequest, AITradeValidationRequest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_options_strategy_recommendation_fallback():
    req = AIOptionsStrategyRequest(
        symbol="NIFTY",
        outlook="BULLISH",
        custom_query="Generate a defined-risk Bull Put Spread",
    )
    rec = await ai_strategy_service.recommend_strategy(req)
    assert rec.symbol == "NIFTY"
    assert len(rec.legs) >= 2
    assert rec.max_profit_pts != ""
    assert rec.risk_reward_ratio != ""


@pytest.mark.asyncio
async def test_trade_validation_service():
    req = AITradeValidationRequest(
        symbol="NIFTY",
        direction="BUY",
        entry_price=24800.0,
        stop_loss=24720.0,
        target_price=25000.0,
        thesis_notes="Bounce from S1 support with high put OI defense",
    )
    val = await ai_validation_service.validate_trade(req)
    assert val.symbol == "NIFTY"
    assert val.decision in ("CONFIRM", "WATCH", "REJECT", "UNCERTAIN")
    assert 0 <= val.score <= 100
    assert val.risk_reward_calculated == 2.5


def test_api_ai_strategy_and_briefing():
    # Strategy recommend API
    res_strat = client.post("/api/v1/ai/strategy/recommend", json={
        "symbol": "NIFTY",
        "outlook": "BULLISH",
    })
    assert res_strat.status_code == 200
    data_strat = res_strat.json()["data"]
    assert data_strat["symbol"] == "NIFTY"
    assert len(data_strat["legs"]) >= 2

    # Trade validate API
    res_val = client.post("/api/v1/ai/trade/validate", json={
        "symbol": "NIFTY",
        "direction": "BUY",
        "entry_price": 24800,
        "stop_loss": 24700,
        "target_price": 25000,
    })
    assert res_val.status_code == 200
    data_val = res_val.json()["data"]
    assert "decision" in data_val
    assert "score" in data_val

    # Market briefing API
    res_brief = client.get("/api/v1/ai/briefing/NIFTY?session_type=PRE_MARKET")
    assert res_brief.status_code == 200
    data_brief = res_brief.json()["data"]
    assert data_brief["symbol"] == "NIFTY"
    assert "key_levels_to_watch" in data_brief
    assert "actionable_playbook" in data_brief
