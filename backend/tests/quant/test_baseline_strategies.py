"""Unit tests for Baseline Strategies (Tier 0)."""

import pytest
import polars as pl
from datetime import datetime, timezone, timedelta

from app.quant.features.feature_engine import CausalFeatureEngine
from app.quant.strategies.strategies import BaselineStrategyEngine, DEFAULT_SESSION_WINDOWS
from app.quant.backtest.backtest_harness import BacktestHarness
from scripts.fetch_fyers_history import generate_synthetic_history


class TestBaselineStrategies:

    @pytest.fixture
    def dataset(self) -> pl.DataFrame:
        return generate_synthetic_history("BSE:SENSEX-INDEX", days=2, base_price=80000.0)

    def test_s1_orb_generation(self, dataset: pl.DataFrame):
        engine = CausalFeatureEngine()
        df = engine.compute_features(dataset)
        strat = BaselineStrategyEngine()

        candidates = strat.scan_s1_orb(df)
        assert isinstance(candidates, list)
        for c in candidates:
            assert c.strategy_id in ("S1_ORB_LONG", "S1_ORB_SHORT")
            assert c.direction in (1, -1)
            assert c.bar_index >= 15  # must be after OR window

    def test_s2_momentum_generation(self, dataset: pl.DataFrame):
        engine = CausalFeatureEngine()
        df = engine.compute_features(dataset)
        strat = BaselineStrategyEngine(momentum_lookback=20)

        candidates = strat.scan_s2_momentum(df)
        assert isinstance(candidates, list)
        for c in candidates:
            assert c.strategy_id in ("S2_MOM_LONG", "S2_MOM_SHORT")
            assert c.direction in (1, -1)
            assert c.bar_index >= 20

    def test_s3_vwap_reclaim_generation(self, dataset: pl.DataFrame):
        engine = CausalFeatureEngine()
        df = engine.compute_features(dataset)
        strat = BaselineStrategyEngine()

        candidates = strat.scan_s3_vwap_reclaim(df)
        assert isinstance(candidates, list)
        for c in candidates:
            assert "VWAP" in c.strategy_id
            assert c.direction in (1, -1)

    def test_s4_volatility_squeeze_generation(self, dataset: pl.DataFrame):
        engine = CausalFeatureEngine()
        df = engine.compute_features(dataset)
        strat = BaselineStrategyEngine(squeeze_lookback=10, squeeze_compression_ratio=0.98)

        candidates = strat.scan_s4_volatility_squeeze(df)
        assert isinstance(candidates, list)
        for c in candidates:
            assert c.strategy_id in ("S4_SQUEEZE_LONG", "S4_SQUEEZE_SHORT")
            assert c.direction in (1, -1)
            assert c.bar_index >= 25

    def test_random_baseline_generation(self):
        strat = BaselineStrategyEngine()
        r_candidates = strat.generate_random_filter_baseline(total_bars=500, target_count=20, seed=123)
        assert len(r_candidates) == 20
        for c in r_candidates:
            assert c.strategy_id == "R_RANDOM_BASELINE"
            assert c.direction in (1, -1)

    def test_session_filter_restricts_candidates(self, dataset: pl.DataFrame):
        """Verifies session filter strictly restricts candidate signals to institutional windows."""
        engine = CausalFeatureEngine()
        df = engine.compute_features(dataset)
        ist_minutes = df["minute_of_day"].to_list() if "minute_of_day" in df.columns else [
            (t.hour * 60 + t.minute + 330) % 1440 for t in df["timestamp"].to_list()
        ]

        strat_unfiltered = BaselineStrategyEngine(session_filter=False)
        strat_filtered = BaselineStrategyEngine(session_filter=True)

        assert strat_filtered.session_filter is True
        assert strat_filtered.allowed_windows == DEFAULT_SESSION_WINDOWS

        # Evaluate S1, S2, S3, S4, S5 with session filter
        for scan_func, strat_name in [
            (strat_filtered.scan_s1_orb, "S1"),
            (strat_filtered.scan_s2_momentum, "S2"),
            (strat_filtered.scan_s3_vwap_reclaim, "S3"),
            (strat_filtered.scan_s4_volatility_squeeze, "S4"),
            (strat_filtered.scan_s5_structural_breakout, "S5"),
        ]:
            cands = scan_func(df)
            for c in cands:
                cand_min = ist_minutes[c.bar_index]
                # Must satisfy either 09:20-10:30 (560-630) or 14:15-15:15 (855-915)
                is_allowed = (560 <= cand_min <= 630) or (855 <= cand_min <= 915)
                assert is_allowed, f"{strat_name} candidate at bar {c.bar_index} emitted at minute {cand_min} (outside session)"
                assert strat_filtered.is_session_allowed(cand_min)

    def test_s5_structural_breakout_generation(self, dataset: pl.DataFrame):
        engine = CausalFeatureEngine()
        df = engine.compute_features(dataset)
        strat = BaselineStrategyEngine(s5_cooldown=5)

        candidates = strat.scan_s5_structural_breakout(df)
        assert isinstance(candidates, list)
        for c in candidates:
            assert c.strategy_id in ("S5_STRUCT_LONG", "S5_STRUCT_SHORT")
            assert c.direction in (1, -1)
            assert c.bar_index >= 50
            assert "k_sl" in c.gate_margins
            assert "k_tp" in c.gate_margins
            assert c.gate_margins["k_sl"] == 1.5
            assert c.gate_margins["k_tp"] == 2.5

    def test_baseline_strategies_registry(self):
        from app.quant.strategies.strategies import (
            BASELINE_STRATEGIES,
            StrategyS5StructuralBreakout,
        )
        assert "S5" in BASELINE_STRATEGIES
        assert BASELINE_STRATEGIES["S5"] is StrategyS5StructuralBreakout
        assert set(BASELINE_STRATEGIES.keys()) >= {"S1", "S2", "S3", "S4", "S5"}
        s5_instance = BASELINE_STRATEGIES["S5"]()
        assert s5_instance.key == "S5"
        assert s5_instance.k_sl == 1.5
        assert s5_instance.k_tp == 2.5

    def test_custom_session_windows(self, dataset: pl.DataFrame):
        """Verifies custom allowed windows configuration."""
        engine = CausalFeatureEngine()
        df = engine.compute_features(dataset)
        ist_minutes = [(t.hour * 60 + t.minute + 330) % 1440 for t in df["timestamp"].to_list()]

        custom_windows = [("10:00", "11:00")]
        strat = BaselineStrategyEngine(allowed_windows=custom_windows)
        assert strat.session_filter is True

        cands = strat.scan_s2_momentum(df)
        for c in cands:
            cand_min = ist_minutes[c.bar_index]
            assert 600 <= cand_min <= 660, f"Candidate at minute {cand_min} not in 10:00-11:00"

    def test_backtest_harness_session_filter(self, dataset: pl.DataFrame):
        """Verifies BacktestHarness suppresses candidate entry outside session windows."""
        harness_baseline = BacktestHarness(session_filter=False)
        trades_base, metrics_base = harness_baseline.run_backtest(dataset, strategy_key="ALL")

        harness_session = BacktestHarness(session_filter=True)
        trades_session, metrics_session = harness_session.run_backtest(dataset, strategy_key="ALL")

        # Every trade in session-filtered backtest must have entered within allowed windows
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        for trade in trades_session:
            entry_dt = trade.entry_time.astimezone(ist_tz) if trade.entry_time.tzinfo else trade.entry_time
            m_of_day = (entry_dt.hour * 60 + entry_dt.minute) if trade.entry_time.tzinfo else ((entry_dt.hour * 60 + entry_dt.minute + 330) % 1440)
            is_in_window = (560 <= m_of_day <= 630) or (855 <= m_of_day <= 915)
            assert is_in_window, f"Trade entered at {trade.entry_time} ({m_of_day} IST), outside session windows"
