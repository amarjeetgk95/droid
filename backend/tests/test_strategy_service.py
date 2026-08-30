import pytest
from app.services.strategy_service import StrategyService
from app.models.strategy import StrategyPayload, StrategyLegModel


class TestStrategyService:
    def test_get_templates_catalog(self):
        service = StrategyService()
        templates = service.get_templates()

        assert len(templates) >= 8
        ids = {t.id for t in templates}
        assert "bull_call_spread" in ids
        assert "iron_condor" in ids
        assert "long_straddle" in ids

    @pytest.mark.asyncio
    async def test_build_template_execution(self):
        service = StrategyService()
        result = await service.build_template("iron_condor", "NIFTY")

        assert result.underlying == "NIFTY"
        assert result.spot_price > 0
        assert len(result.legs) == 4
        assert len(result.payoff_curve) > 0
        assert result.premium_type == "CREDIT"
        assert result.max_profit is not None
        assert result.pop_percent > 0

    @pytest.mark.asyncio
    async def test_scan_strategies(self):
        service = StrategyService()
        opportunities = await service.scan_strategies(outlook="NEUTRAL", min_pop=30.0)

        assert len(opportunities) > 0
        for opp in opportunities:
            assert opp.outlook == "NEUTRAL"
            assert opp.pop_percent >= 30.0
            assert len(opp.legs) > 0
