import pytest
from app.ai.tools import execute_tool, AI_TOOLS_SCHEMA


@pytest.mark.asyncio
async def test_ai_tools_schema_validity():
    assert len(AI_TOOLS_SCHEMA) >= 5
    tool_names = [t["function"]["name"] for t in AI_TOOLS_SCHEMA]
    assert "get_market_quote" in tool_names
    assert "get_regime_analytics" in tool_names
    assert "get_option_chain_summary" in tool_names
    assert "get_futures_overview" in tool_names
    assert "get_institutional_flow" in tool_names
    assert "calculate_options_strategy_payoff" in tool_names


@pytest.mark.asyncio
async def test_execute_get_market_quote():
    res = await execute_tool("get_market_quote", {"symbol": "NIFTY"})
    assert "symbol" in res
    assert res["symbol"] == "NIFTY"
    assert "ltp" in res


@pytest.mark.asyncio
async def test_execute_get_regime_analytics():
    res = await execute_tool("get_regime_analytics", {"symbol": "NIFTY"})
    assert res["symbol"] == "NIFTY"
    assert "spot_price" in res
    assert "regime_state" in res
    assert "key_levels" in res
    assert "indicators" in res


@pytest.mark.asyncio
async def test_execute_get_option_chain_summary():
    res = await execute_tool("get_option_chain_summary", {"symbol": "NIFTY"})
    assert res["symbol"] == "NIFTY"
    assert "pcr_oi" in res
    assert "atm_iv" in res


@pytest.mark.asyncio
async def test_execute_get_futures_overview():
    # When futures is unavailable, return status without fake data
    res = await execute_tool("get_futures_overview", {"symbol": "NIFTY"})
    assert res["symbol"] == "NIFTY"
    assert res.get("status") == "futures_data_unavailable"

    # With mocked futures provider
    from types import SimpleNamespace
    from unittest.mock import patch, AsyncMock

    mock_futures = SimpleNamespace(
        spot_price=25000.0,
        term_structure=SimpleNamespace(
            contracts=[SimpleNamespace(ltp=25020.0, basis=20.0, basis_percent=0.08, cost_of_carry_percent=5.0, open_interest=10000, oi_change_percent=2.5)],
            curve_state="CONTANGO",
        ),
        buildup=SimpleNamespace(buildup_type="LONG_BUILDUP", interpretation="Bullish", strength="STRONG"),
        rollover=SimpleNamespace(rollover_percent=75.0, rollover_pace="IN_LINE", three_month_avg_rollover=72.5),
    )
    with patch("app.ai.tools._fetch_futures_safe", new=AsyncMock(return_value=mock_futures)):
        res_mock = await execute_tool("get_futures_overview", {"symbol": "NIFTY"})
        assert res_mock["symbol"] == "NIFTY"
        assert "buildup" in res_mock
        assert "term_structure_curve" in res_mock


@pytest.mark.asyncio
async def test_execute_get_institutional_flow():
    res = await execute_tool("get_institutional_flow", {})
    assert "positioning" in res
    assert len(res["positioning"]) > 0
    fii = next((p for p in res["positioning"] if p["category"] == "FII"), None)
    assert fii is not None
    assert "long_short_ratio" in fii


@pytest.mark.asyncio
async def test_execute_calculate_options_strategy_payoff():
    legs = [
        {"strike": 24800, "option_type": "PE", "action": "SELL", "premium": 80.0, "delta": -0.3, "theta": 10.0},
        {"strike": 24600, "option_type": "PE", "action": "BUY", "premium": 25.0, "delta": -0.1, "theta": -3.0},
    ]
    res = await execute_tool("calculate_options_strategy_payoff", {
        "symbol": "NIFTY",
        "spot_price": 24850.0,
        "legs": legs,
    })
    assert res["symbol"] == "NIFTY"
    assert res["structure_type"] == "NET_CREDIT"
    assert res["net_premium_points"] == 55.0
    assert res["leg_count"] == 2
