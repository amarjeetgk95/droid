"""Unit tests for confluence (AND) multi-strategy filtering."""

import pytest
import polars as pl

from app.copilot.analogue.feature_engine import CausalFeatureEngine
from app.copilot.analogue.baseline_strategies import BaselineStrategyEngine
from scripts.fetch_fyers_history import generate_synthetic_history


def _features(days: int = 3) -> pl.DataFrame:
    raw = generate_synthetic_history("BSE:SENSEX-INDEX", days=days, base_price=80000.0)
    return CausalFeatureEngine().compute_features(raw)


class TestConfluence:
    def test_intersection_is_subset_of_primary(self):
        df = _features()
        engine = BaselineStrategyEngine(trend_aligned=False)
        primary = engine.scan_single(df, "S4")
        merged = engine.scan_confluence(df, ["S4", "S2"])
        assert len(merged) <= len(primary)
        assert merged, "confluence produced no candidates; the assertions below would pass vacuously"
        for m in merged:
            # Tag joins legs with '+' (CONF_S4+S2_LONG), not '_'.
            assert m.strategy_id.startswith("CONF_S4+S2_")
            assert m.direction in (1, -1)

    def test_confirming_leg_vetoes(self):
        df = _features()
        engine = BaselineStrategyEngine(trend_aligned=False)
        s2_only = engine.scan_single(df, "S2")
        merged = engine.scan_confluence(df, ["S4", "S2"])
        # Every merged signal must sit within tolerance of an S2 signal
        # with matching direction.
        s2_by_bar: dict[int, list[int]] = {}
        for c in s2_only:
            s2_by_bar.setdefault(c.bar_index, []).append(c.direction)
        for m in merged:
            assert any(
                m.direction in s2_by_bar.get(b, [])
                for b in range(m.bar_index - 1, m.bar_index + 2)
            )

    def test_unknown_leg_rejected(self):
        df = _features()
        engine = BaselineStrategyEngine()
        with pytest.raises(ValueError):
            engine.scan_single(df, "S9")
        with pytest.raises(ValueError):
            engine.scan_confluence(df, ["S4"])
