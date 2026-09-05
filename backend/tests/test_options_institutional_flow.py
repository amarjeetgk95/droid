from datetime import datetime, timezone
from unittest.mock import AsyncMock
import pytest
from app.services.options_service import options_service
from app.models.market import NormalizedOptionQuote, NormalizedQuote, DataStatus


def _create_sample_chain(underlying: str = "NIFTY", base: float = 24000.0) -> list[NormalizedOptionQuote]:
    now = datetime.now(timezone.utc)
    exp = datetime(2026, 9, 10, tzinfo=timezone.utc)
    quotes = []
    for offset in (-100.0, -50.0, 0.0, 50.0, 100.0):
        strike = base + offset
        quotes.append(NormalizedOptionQuote(
            timestamp=now,
            provider="test",
            instrument="OPT",
            contract_id=f"{underlying}{int(strike)}CE",
            underlying=underlying,
            expiry=exp,
            strike=strike,
            option_type="CE",
            ltp=max(10.0, 200.0 - offset),
            volume=5000,
            oi=20000,
        ))
        quotes.append(NormalizedOptionQuote(
            timestamp=now,
            provider="test",
            instrument="OPT",
            contract_id=f"{underlying}{int(strike)}PE",
            underlying=underlying,
            expiry=exp,
            strike=strike,
            option_type="PE",
            ltp=max(10.0, 200.0 + offset),
            volume=4000,
            oi=18000,
        ))
    return quotes


@pytest.mark.asyncio
async def test_options_institutional_flow_calculation():
    options_service.market_service.get_quote = AsyncMock(return_value=NormalizedQuote(
        symbol="NIFTY", display_name="NIFTY", timestamp=datetime.now(timezone.utc),
        ltp=24000.0, open=23950.0, high=24050.0, low=23900.0, previous_close=23900.0,
        change=100.0, change_percent=0.4, volume=1000000, status=DataStatus.LIVE, provider="test",
    ))
    options_service.market_service.get_option_chain = AsyncMock(return_value=_create_sample_chain("NIFTY", 24000.0))

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
