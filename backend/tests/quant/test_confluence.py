"""Unit tests for confluence (AND) multi-strategy filtering."""

import pytest
import polars as pl

from app.quant.features.feature_engine import CausalFeatureEngine
from app.quant.strategies.strategies import BaselineStrategyEngine
from app.quant.backtest.backtest_harness import BacktestHarness
from scripts.fetch_fyers_history import generate_synthetic_history


def _features(days: int = 3) -> pl.DataFrame:
    raw = generate_synthetic_history("BSE:SENSEX-INDEX", days=days, base_price=80000.0)
    return CausalFeatureEngine().compute_features(raw)


class TestConfluence:
    def test_intersection_is_subset_of_primary(self):
        df = _features()
        engine = BaselineStrategyEngine(trend_aligned=False)
        primary = engine.scan_single(df, "S4")
        merged = engine.scan_confluence(df, ["S4", "S8"])
        assert len(merged) <= len(primary)
        for m in merged:
            assert m.strategy_id.startswith("CONF_S4_S8_")
            assert m.direction in (1, -1)

    def test_confirming_leg_vetoes(self):
        df = _features()
        engine = BaselineStrategyEngine(trend_aligned=False)
        s8_only = engine.scan_single(df, "S8")
        merged = engine.scan_confluence(df, ["S4", "S8"])
        # Every merged signal must sit within tolerance of an S8 signal
        # with matching direction.
        s8_by_bar: dict[int, list[int]] = {}
        for c in s8_only:
            s8_by_bar.setdefault(c.bar_index, []).append(c.direction)
        for m in merged:
            assert any(
                m.direction in s8_by_bar.get(b, [])
                for b in range(m.bar_index - 1, m.bar_index + 2)
            )

    def test_unknown_leg_rejected(self):
        df = _features()
        engine = BaselineStrategyEngine()
        with pytest.raises(ValueError):
            engine.scan_single(df, "S9")
        with pytest.raises(ValueError):
            engine.scan_confluence(df, ["S4"])
        harness = BacktestHarness()
        with pytest.raises(ValueError):
            harness.run_backtest(df=df, strategy_key="S4+S9")

    def test_harness_confluence_trade_bound(self):
        raw = generate_synthetic_history("BSE:SENSEX-INDEX", days=3, base_price=80000.0)
        harness = BacktestHarness(trend_aligned=False)
        _, m_s4 = harness.run_backtest(df=raw, strategy_key="S4")
        _, m_conf = harness.run_backtest(df=raw, strategy_key="S4+S8")
        # Each confluence trade derives from a primary S4 candidate.
        assert m_conf.total_trades <= m_s4.total_trades
        assert m_conf.gate_g0_verdict in ("PASSED", "FAILED", "INCONCLUSIVE")
