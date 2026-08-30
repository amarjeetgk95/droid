from app.services.backtest_service import BacktestService
from app.models.backtest import BacktestPayload


class TestBacktestService:
    def test_presets_catalog(self):
        service = BacktestService()
        presets = service.get_presets()
        assert len(presets) >= 3
        ids = [p.id for p in presets]
        assert "short_straddle" in ids
        assert "iron_condor" in ids

    def test_execute_backtest(self):
        service = BacktestService()
        payload = BacktestPayload(
            strategy_id="short_straddle",
            underlying="NIFTY",
            initial_capital=500000.0,
            num_days=15,
        )
        res = service.execute_backtest(payload)

        assert res.total_trades == 15
        assert len(service.get_history()) >= 1
