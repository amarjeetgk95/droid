import pytest
from app.services.futures_service import FuturesService


class TestFuturesService:
    def test_oi_buildup_classification_four_quadrants(self):
        # 1. Long Buildup: Price UP, OI UP
        lb = FuturesService.classify_oi_buildup(
            symbol="NIFTY-FUT", underlying="NIFTY", ltp=25100.0,
            price_change=120.0, price_change_percent=0.48,
            open_interest=1000000, oi_change=60000, oi_change_percent=6.0
        )
        assert lb.buildup_type == "LONG_BUILDUP"
        assert lb.strength == "STRONG"
        assert "Bullish" in lb.interpretation

        # 2. Short Buildup: Price DOWN, OI UP
        sb = FuturesService.classify_oi_buildup(
            symbol="NIFTY-FUT", underlying="NIFTY", ltp=24900.0,
            price_change=-100.0, price_change_percent=-0.40,
            open_interest=1000000, oi_change=30000, oi_change_percent=3.0
        )
        assert sb.buildup_type == "SHORT_BUILDUP"
        assert sb.strength == "MODERATE"
        assert "Bearish" in sb.interpretation

        # 3. Long Unwinding: Price DOWN, OI DOWN
        lu = FuturesService.classify_oi_buildup(
            symbol="NIFTY-FUT", underlying="NIFTY", ltp=24850.0,
            price_change=-150.0, price_change_percent=-0.60,
            open_interest=1000000, oi_change=-70000, oi_change_percent=-7.0
        )
        assert lu.buildup_type == "LONG_UNWINDING"
        assert lu.strength == "STRONG"

        # 4. Short Covering: Price UP, OI DOWN
        sc = FuturesService.classify_oi_buildup(
            symbol="NIFTY-FUT", underlying="NIFTY", ltp=25200.0,
            price_change=200.0, price_change_percent=0.80,
            open_interest=1000000, oi_change=-15000, oi_change_percent=-1.5
        )
        assert sc.buildup_type == "SHORT_COVERING"
        assert sc.strength == "WEAK"

    @pytest.mark.asyncio
    async def test_get_term_structure(self):
        service = FuturesService()
        term = await service.get_term_structure("NIFTY")

        assert term.underlying == "NIFTY"
        assert term.spot_price > 0
        assert len(term.contracts) >= 2
        assert term.curve_state in ["CONTANGO", "BACKWARDATION", "FLAT"]

        near = term.contracts[0]
        assert near.tenor == "NEAR"
        assert near.ltp > 0
        assert near.basis != 0
        assert near.cost_of_carry_percent != 0
        assert near.fair_value > 0
        assert near.days_to_expiry > 0

    @pytest.mark.asyncio
    async def test_get_rollover_metrics(self):
        service = FuturesService()
        rollover = await service.get_rollover_metrics("NIFTY")

        assert rollover.underlying == "NIFTY"
        assert rollover.rollover_percent > 0
        assert rollover.total_futures_oi > 0
        assert rollover.rollover_pace in ["AHEAD", "IN_LINE", "BEHIND"]

    @pytest.mark.asyncio
    async def test_get_futures_overview(self):
        service = FuturesService()
        overview = await service.get_futures_overview("NIFTY")

        assert overview.underlying == "NIFTY"
        assert overview.spot_price > 0
        assert overview.buildup is not None
        assert overview.rollover is not None
        assert len(overview.all_tracked_buildups) >= 1
