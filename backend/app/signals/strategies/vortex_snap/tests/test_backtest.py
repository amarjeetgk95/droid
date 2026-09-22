"""
Unit and integration tests for VORTEX-SNAP Backtesting & Research Engine.
Covers data loading, cost model, simulation engine, walk-forward, ablation,
robustness testing, and reporting (§30-§35, §50-§53).
"""
from datetime import datetime, timezone
from decimal import Decimal
import pytest

from app.signals.strategies.vortex_snap.backtest.data_loader import HistoricalDataLoader, HistoricalBarContext
from app.signals.strategies.vortex_snap.backtest.cost_model import TransactionCostModel
from app.signals.strategies.vortex_snap.backtest.metrics import calculate_metrics, BacktestTradeRecord
from app.signals.strategies.vortex_snap.backtest.engine import VortexBacktestEngine
from app.signals.strategies.vortex_snap.backtest.walk_forward import RollingWalkForwardValidator
from app.signals.strategies.vortex_snap.backtest.ablation import ComponentAblationRunner
from app.signals.strategies.vortex_snap.backtest.robustness import RobustnessTester
from app.signals.strategies.vortex_snap.backtest.report import ResearchReportGenerator


class TestVortexBacktest:
    @pytest.fixture
    def synthetic_three_days(self):
        """Generate 3 consecutive trading days of synthetic market data."""
        days = [
            datetime(2026, 9, 21, tzinfo=timezone.utc),  # Monday
            datetime(2026, 9, 22, tzinfo=timezone.utc),  # Tuesday
            datetime(2026, 9, 23, tzinfo=timezone.utc),  # Wednesday
        ]
        all_candles = []
        curr_price = 24000.0
        for idx, d in enumerate(days):
            candles = HistoricalDataLoader.generate_synthetic_session(
                date_obj=d,
                start_price=curr_price,
                drift=30.0 if idx == 0 else -15.0,
                volatility=8.0,
                add_compression_and_breakout=True,
                seed=42 + idx,
            )
            all_candles.extend(candles)
            curr_price = candles[-1].close

        contexts = HistoricalDataLoader.compute_session_levels(all_candles)
        return contexts

    def test_synthetic_session_generation(self):
        d = datetime(2026, 9, 21, tzinfo=timezone.utc)
        candles = HistoricalDataLoader.generate_synthetic_session(d, start_price=24000.0, seed=123)
        assert len(candles) == 375  # Exactly 375 1-minute bars in a session
        # Volume profile should be positive
        assert all(c.volume > 0 for c in candles)
        # Check chronological order
        for i in range(1, len(candles)):
            assert candles[i].timestamp == candles[i - 1].timestamp + 60000

    def test_resample_5m_closed_boundaries(self):
        d = datetime(2026, 9, 21, tzinfo=timezone.utc)
        candles = HistoricalDataLoader.generate_synthetic_session(d, start_price=24000.0)
        c5m = HistoricalDataLoader.resample_5m(candles)
        # 375 1m bars / 5 = 75 5m bars
        assert len(c5m) == 75
        for c in c5m:
            assert c.high >= max(c.open, c.close)
            assert c.low <= min(c.open, c.close)

    def test_session_level_continuity(self, synthetic_three_days):
        contexts = synthetic_three_days
        assert len(contexts) == 375 * 3

        # Day 1: PDH, PDL, PDC should be None (no prior day in dataset)
        assert contexts[0].pdh is None
        assert contexts[0].cdo is not None
        assert contexts[0].vwap is not None

        # Day 2 (bar 375): PDH, PDL, PDC should be set from Day 1
        day2_bar0 = contexts[375]
        day1_bars = [c.candle_1m for c in contexts[:375]]
        assert day2_bar0.pdh == max(c.high for c in day1_bars)
        assert day2_bar0.pdl == min(c.low for c in day1_bars)
        assert day2_bar0.pdc == day1_bars[-1].close

    def test_transaction_cost_model(self):
        cm = TransactionCostModel(brokerage_per_order=20.0)
        friction = cm.calculate_round_trip(
            instrument="NIFTY",
            entry_price=120.0,
            exit_price=150.0,
            quantity=25,
            is_option=True,
            atr_1m=8.0,
        )
        assert friction.brokerage == 40.0  # ₹20 buy + ₹20 sell
        assert friction.stt > 0.0
        assert friction.exchange_charges > 0.0
        assert friction.gst > 0.0
        assert friction.total_friction > friction.brokerage
        assert friction.entry_slippage_points > 0.0

    def test_backtest_engine_execution(self, synthetic_three_days):
        engine = VortexBacktestEngine(
            lot_size=25,
            enable_dynamic_exits=True,
            enable_time_decay=True,
        )
        metrics = engine.run(synthetic_three_days, instrument="NIFTY")

        assert metrics is not None
        assert metrics.total_trades >= 0
        assert len(metrics.equity_curve) >= 1
        assert metrics.equity_curve[0] == 500000.0
        if metrics.total_trades > 0:
            assert metrics.win_rate_pct + metrics.loss_rate_pct <= 100.01
            assert metrics.profit_factor >= 0.0
            assert metrics.max_drawdown_pct >= 0.0

    def test_walk_forward_validator(self, synthetic_three_days):
        validator = RollingWalkForwardValidator(n_folds=2, embargo_bars=60)
        wf_summary = validator.evaluate(synthetic_three_days, instrument="NIFTY")

        assert wf_summary.total_folds >= 1
        assert len(wf_summary.folds) == wf_summary.total_folds
        for f in wf_summary.folds:
            assert f.train_bars_count > 0
            assert f.test_bars_count > 0
            assert f.walk_forward_efficiency >= 0.0

    def test_component_ablation_runner(self, synthetic_three_days):
        runner = ComponentAblationRunner()
        report = runner.run_study(synthetic_three_days, instrument="NIFTY")

        assert len(report.stages) == 9
        stage_letters = [s.stage_letter for s in report.stages]
        assert stage_letters == ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
        assert isinstance(report.primary_hypothesis_supported, bool)
        assert isinstance(report.primary_hypothesis_delta_sharpe, float)

    def test_robustness_tester(self, synthetic_three_days):
        tester = RobustnessTester()
        report = tester.run_all(synthetic_three_days, instrument="NIFTY", mc_iterations=50)

        assert len(report.cost_stress) == 4
        assert len(report.latency_stress) == 3
        assert len(report.parameter_perturbations) == 6
        assert report.monte_carlo.iterations == 50
        assert 0.0 <= report.monte_carlo.probability_of_ruin_pct <= 100.0
        assert isinstance(report.is_fragile, bool)

    def test_research_report_generation(self, synthetic_three_days, tmp_path):
        engine = VortexBacktestEngine()
        baseline = engine.run(synthetic_three_days, instrument="NIFTY")

        gen = ResearchReportGenerator(output_dir=tmp_path)
        md_path, json_path = gen.save_report(
            instrument="NIFTY",
            baseline=baseline,
            filename_prefix="test_report",
        )

        assert md_path.exists()
        assert json_path.exists()
        md_content = md_path.read_text(encoding="utf-8")
        assert "# DROID VORTEX-SNAP Quantitative Research Report" in md_content
        assert "## 1. Baseline Performance Summary" in md_content
