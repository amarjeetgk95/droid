"""Unit tests for Strategy S7: Structural Absorption Reversal (Tier 0)."""

import pytest
import polars as pl
from datetime import datetime, timezone, timedelta

from app.quant.features.feature_engine import CausalFeatureEngine
from app.quant.strategies.s7_config import S7Config, create_s7_default_config
from app.quant.strategies.s7_events import S7EventEngine, AbsorptionEvent
from app.quant.strategies.s7_absorption import S7AbsorptionScanner
from app.quant.strategies.strategies import BaselineStrategyEngine, StrategyS7AbsorptionReversal
from app.quant.backtest.backtest_harness import BacktestHarness
from scripts.fetch_fyers_history import generate_synthetic_history


class TestS7Strategy:

    @pytest.fixture
    def multi_day_dataset(self) -> pl.DataFrame:
        """Generates 3 trading days of synthetic 1m data for testing."""
        return generate_synthetic_history("BSE:SENSEX-INDEX", days=3, base_price=80000.0)

    def test_s7_config_immutability_and_hash(self):
        cfg = create_s7_default_config()
        assert cfg.strategy_id == "S7"
        assert cfg.parameter_hash
        assert isinstance(cfg.parameter_hash, str)

        # Hash is deterministic
        cfg2 = create_s7_default_config()
        assert cfg.parameter_hash == cfg2.parameter_hash

        # Overrides change hash
        cfg_custom = create_s7_default_config(
            absorption=cfg.absorption.__class__(min_volume_ratio=2.0)
        )
        assert cfg.parameter_hash != cfg_custom.parameter_hash

    def test_s7_event_engine_detection(self, multi_day_dataset: pl.DataFrame):
        engine = CausalFeatureEngine()
        df = engine.compute_features(multi_day_dataset)

        event_engine = S7EventEngine()
        events = event_engine.detect_events(df)
        assert isinstance(events, list)

        for ev in events:
            assert isinstance(ev, AbsorptionEvent)
            assert ev.reversal_direction in (1, -1)
            assert ev.volume_ratio >= 1.0
            assert ev.wick_rejection >= 0.0
            assert ev.entry_ref_price > 0.0
            assert ev.level.role in ("SUPPORT", "RESISTANCE")

    def test_s7_scanner_qualification_gates(self, multi_day_dataset: pl.DataFrame):
        engine = CausalFeatureEngine()
        df = engine.compute_features(multi_day_dataset)

        event_engine = S7EventEngine()
        events = event_engine.detect_events(df)

        scanner = S7AbsorptionScanner()
        candidates = scanner.scan_candidates(events, df)
        assert isinstance(candidates, list)

        for c in candidates:
            assert c.strategy_id in ("S7_ABSORPTION_LONG", "S7_ABSORPTION_SHORT")
            assert c.direction in (1, -1)
            assert c.entry_ref_price > 0.0
            assert "k_sl" in c.gate_margins
            assert "k_tp" in c.gate_margins
            assert c.gate_margins["k_sl"] <= 1.0  # Tight stop characteristic of mean-reversion

    def test_s7_in_baseline_strategy_engine(self, multi_day_dataset: pl.DataFrame):
        engine = CausalFeatureEngine()
        df = engine.compute_features(multi_day_dataset)

        strat_engine = BaselineStrategyEngine()
        candidates = strat_engine.scan_s7_absorption_reversal(df)
        assert isinstance(candidates, list)

        strat_wrapper = StrategyS7AbsorptionReversal()
        candidates_wrapper = strat_wrapper.scan(df)
        assert len(candidates) == len(candidates_wrapper)

    def test_s7_in_backtest_harness(self, multi_day_dataset: pl.DataFrame):
        harness = BacktestHarness()
        trades, metrics = harness.run_backtest(multi_day_dataset, strategy_key="S7")

        assert metrics is not None
        assert hasattr(metrics, "gate_g0_verdict")
        assert metrics.gate_g0_verdict in ("PASSED", "FAILED", "INCONCLUSIVE")
        assert metrics.total_trades == len(trades)
