from app.quant.backtester import run_strategy_backtest


class TestBacktesterEngine:
    def test_short_straddle_backtest(self):
        res = run_strategy_backtest(
            strategy_id="short_straddle",
            underlying="NIFTY",
            initial_capital=500000.0,
            num_days=30,
            seed=42,
        )

        assert res.total_trades == 30
        assert res.final_equity > 0
        assert 0 <= res.win_rate_percent <= 100
        assert len(res.equity_curve) == 30
        assert len(res.trades) == 30
        assert res.trades[0].trade_id == "TRD-030"
        assert res.profit_factor >= 0

    def test_iron_condor_backtest(self):
        res = run_strategy_backtest(
            strategy_id="iron_condor",
            underlying="BANKNIFTY",
            initial_capital=1000000.0,
            num_days=20,
            seed=42,
        )

        assert res.total_trades == 20
        assert res.winning_trades + res.losing_trades == 20
        assert len(res.monthly_pnl) >= 1
