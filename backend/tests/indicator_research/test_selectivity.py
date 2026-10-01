import pytest

from app.indicator_research.backtesting.models import BacktestSettings
from app.indicator_research.enums import SampleSizeFlag
from app.indicator_research.research.features import IndicatorSpec
from app.indicator_research.research.selectivity import sweep_selectivity


def test_selectivity_sweep_monotonic_curve(candles):
    specs = [IndicatorSpec("fisher", {"length": 9, "signal_length": 1}, "primary")]
    thresholds = [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0]

    result = sweep_selectivity(
        candles=candles,
        specs=specs,
        feature="fisher",
        operator=">",
        thresholds=thresholds,
        direction="long",
        settings=BacktestSettings(),
        forward_horizon=5,
        min_trades=5,
        instrument="NIFTY",
        timeframe="5m",
    )

    assert result["ok"] is True
    assert len(result["rows"]) == len(thresholds)
    # Stricter '>' thresholds should produce non-increasing signal counts
    counts = [r["signal_count"] for r in result["rows"]]
    assert all(counts[i] >= counts[i + 1] for i in range(len(counts) - 1))
    assert result["monotonic"] is True

    # Sample size flags should exist on every row
    for row in result["rows"]:
        assert row["sample_size_flag"] in (
            SampleSizeFlag.SUFFICIENT.value,
            SampleSizeFlag.MARGINAL.value,
            SampleSizeFlag.INSUFFICIENT.value,
        )
        assert "forward_stats" in row
        assert row["forward_stats"]["horizon_bars"] == 5


def test_selectivity_missing_feature_fails_cleanly(candles):
    specs = [IndicatorSpec("fisher", {"length": 9, "signal_length": 1}, "primary")]

    result = sweep_selectivity(
        candles=candles,
        specs=specs,
        feature="non_existent_feature",
        operator=">",
        thresholds=[1.0, 2.0],
    )

    assert result["ok"] is False
    assert "not found in available features" in result["error"]
