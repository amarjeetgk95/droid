import pytest
from app.services.historical_service import HistoricalService


class TestHistoricalService:
    @pytest.mark.asyncio
    async def test_scan_patterns(self):
        service = HistoricalService()
        patterns = await service.scan_patterns("NIFTY", "5m")
        # Patterns might be empty or present depending on candles, but should return a list
        assert isinstance(patterns, list)

    @pytest.mark.asyncio
    async def test_get_historical_shifts(self):
        service = HistoricalService()
        shifts_res = await service.get_historical_shifts("NIFTY", days=7)

        assert shifts_res.symbol == "NIFTY"
        assert len(shifts_res.shifts) == 7
        assert shifts_res.shifts[0].max_pain_strike > 0
        assert shifts_res.shifts[0].pcr_oi > 0

    def test_get_seasonality(self):
        service = HistoricalService()
        seasonality = service.get_seasonality("NIFTY")

        assert len(seasonality.days) == 5
        assert seasonality.days[0].day_name == "Monday"
        assert len(seasonality.best_day_for_buyers) > 0

    @pytest.mark.asyncio
    async def test_watchlist_operations(self):
        service = HistoricalService()
        items = await service.get_watchlist()
        assert len(items) >= 1

        service.add_to_watchlist("RELIANCE")
        assert "RELIANCE" in service._watchlist

        service.remove_from_watchlist("RELIANCE")
        assert "RELIANCE" not in service._watchlist
