import pytest

from app.indicator_research.backtesting.models import BacktestSettings
from app.indicator_research.enums import OrderFlowProvenance
from app.indicator_research.indicators.base import Candle
from app.indicator_research.research.features import IndicatorSpec
from app.indicator_research.research.runner import run_once
from app.indicator_research.research.walkforward import walk_forward


def test_order_flow_provenance_guard_blocks_run_without_data():
    # Synthetic candles with NO volume and NO order flow
    empty_flow_candles: list[Candle] = [
        {
            "timestamp": f"2026-01-05T09:{15+i:02d}:00+05:30",
            "open": 24000.0 + i,
            "high": 24010.0 + i,
            "low": 23990.0 + i,
            "close": 24005.0 + i,
            "volume": 0.0,
        }
        for i in range(60)
    ]

    specs = [IndicatorSpec("cvd", {"anchor": "session"}, "primary")]
    long_rule = {
        "operator": "AND",
        "conditions": [{"left": "cvd", "operator": ">", "right": 0.0}],
    }

    outcome = run_once(
        candles=empty_flow_candles,
        specs=specs,
        long_rule=long_rule,
        short_rule=None,
        settings=BacktestSettings(),
        verify_causality=False,
    )

    assert outcome.ok is False
    assert "Order flow data is UNAVAILABLE" in str(outcome.error)


def test_order_flow_provenance_detection_real_and_proxy(candles):
    from app.indicator_research.data import CandleSeries, load_candles_sync

    # Candles fixture contains buy_volume and sell_volume -> REAL
    series = CandleSeries(
        instrument="NIFTY",
        dataset_symbol="NIFTY",
        timeframe="5m",
        availability="available",
        candles=candles,
    )
    # Check sample candles
    sample = series.candles[:50]
    has_real = any(
        c.get("trades") or (c.get("buy_volume") is not None and c.get("sell_volume") is not None)
        for c in sample
    )
    assert has_real is True


def test_walk_forward_cryptographic_oos_fingerprint(candles):
    specs = [IndicatorSpec("fisher", {"length": 9, "signal_length": 1}, "primary")]
    long_rule = {
        "operator": "AND",
        "conditions": [{"left": "fisher", "operator": "crosses_above", "right": -1.5}],
    }
    short_rule = {
        "operator": "AND",
        "conditions": [{"left": "fisher", "operator": "crosses_below", "right": 1.5}],
    }

    result = walk_forward(
        candles=candles,
        specs=specs,
        long_rule=long_rule,
        short_rule=short_rule,
        settings=BacktestSettings(),
        folds=3,
        purge_bars=5,
        max_combinations=5,
        min_trades=1,
    )

    assert result["folds_completed"] >= 1
    assert "oos_lock" in result
    assert result["oos_lock"]["oos_consumed"] is True
    assert len(result["oos_lock"]["oos_fingerprint"]) == 16
