import pytest
from app.services.morning_briefing_service import morning_briefing_service
from app.institutional.telegram_templates import format_morning_briefing


@pytest.mark.asyncio
async def test_morning_briefing_data_generation():
    data = await morning_briefing_service.generate_briefing_data()
    assert "date_str" in data
    assert "nifty_spot" in data
    assert "nifty_range" in data
    assert "nifty_max_pain" in data
    assert "call_wall" in data
    assert "put_floor" in data


def test_format_morning_briefing_template():
    sample_data = {
        "date_str": "Thursday, 03 Sep 2026",
        "bias": "MILDLY BULLISH",
        "india_vix": "13.40",
        "nifty_spot": "24,300.00",
        "nifty_range": "24,150 – 24,450 (±150 pts)",
        "nifty_max_pain": "24300",
        "nifty_pcr": "1.15",
        "call_wall": "24500 CE",
        "put_floor": "24000 PE",
        "bank_spot": "51,400.00",
        "bank_range": "51,000 – 51,800 (±400 pts)",
        "bank_max_pain": "51200",
        "radar_stocks": ["RELIANCE — Breakout setup", "HDFCBANK — Strong OI"],
    }
    rendered = format_morning_briefing(sample_data)
    assert "DROID PRE-MARKET BRIEFING" in rendered
    assert "24,300.00" in rendered
    assert "Max Pain: `24300`" in rendered
    assert "RELIANCE" in rendered
