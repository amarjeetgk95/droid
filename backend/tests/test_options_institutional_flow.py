import pytest
from app.services.options_service import options_service


@pytest.mark.asyncio
async def test_options_institutional_flow_calculation():
    flow = await options_service.get_institutional_oi_flow("NIFTY")
    assert flow.symbol == "NIFTY"
    assert flow.spot_price > 0
    assert flow.atm_strike > 0
    assert flow.pcr_oi > 0
    assert flow.call_wall_strike > 0
    assert flow.put_floor_strike > 0
    assert flow.institutional_sentiment in (
        "STRONG_BULLISH", "BULLISH", "NEUTRAL", "BEARISH", "STRONG_BEARISH"
    )
    assert 0.0 <= flow.institutional_score <= 100.0
    assert len(flow.strike_flows) > 0

    first_strike = flow.strike_flows[0]
    assert first_strike.call_buildup in (
        "LONG_BUILDUP", "SHORT_BUILDUP", "SHORT_COVERING", "LONG_UNWINDING", "NEUTRAL"
    )
    assert first_strike.put_buildup in (
        "LONG_BUILDUP", "SHORT_BUILDUP", "SHORT_COVERING", "LONG_UNWINDING", "NEUTRAL"
    )
