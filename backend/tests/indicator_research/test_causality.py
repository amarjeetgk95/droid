"""Causality and repaint detection.

A validation layer that never fails is decoration. These tests feed it
deliberately future-reading indicators and require it to catch them, then feed
it the shipped library and require it to stay quiet.
"""

from __future__ import annotations

from typing import Any, ClassVar, Mapping, Sequence

import pytest

from app.indicator_research.backtesting.engine import BacktestEngine
from app.indicator_research.backtesting.models import BacktestSettings, ExitSettings, ExecutionSettings
from app.indicator_research.backtesting.validation import (
    check_feature_causality,
    check_indicator_causality,
    check_rule_causality,
    validate_backtest,
)
from app.indicator_research.enums import IndicatorCategory, OutputType
from app.indicator_research.indicators.base import (
    BaseIndicator,
    IndicatorMetadata,
    OutputSpec,
)
from app.indicator_research.indicators.helpers import ohlcv_features
from app.indicator_research.indicators.registry import IndicatorRegistry
from app.indicator_research.research.features import IndicatorSpec, build_features, make_feature_provider
from tests.indicator_research.conftest import build_candles

LONG_ABOVE_100 = {
    "operator": "AND",
    "conditions": [{"left": "close", "operator": "crosses_above", "right": 100}],
}


class CenteredAverage(BaseIndicator):
    """Non-causal on purpose: averages the bar, the one before and the one after."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="test_centered",
        name="Centered Average (non-causal)",
        category=IndicatorCategory.CUSTOM,
        description="Reads one future bar. Used to test repaint detection.",
        output_type=OutputType.OSCILLATOR,
        outputs=(OutputSpec("centered"),),
    )

    def calculate(self, candles: Sequence[Mapping[str, Any]], params: Mapping[str, Any]):
        closes = [float(c["close"]) for c in candles]
        out: list[Any] = [None] * len(candles)
        for i in range(1, len(candles) - 1):
            out[i] = (closes[i - 1] + closes[i] + closes[i + 1]) / 3.0
        return {"centered": out}


class FullSampleZScore(BaseIndicator):
    """Non-causal on purpose: normalises by the whole sample's mean and sigma."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="test_zscore",
        name="Full-sample Z-Score (non-causal)",
        category=IndicatorCategory.CUSTOM,
        description="Uses every future bar to normalise. Used to test repaint detection.",
        output_type=OutputType.OSCILLATOR,
        outputs=(OutputSpec("z"),),
    )

    def calculate(self, candles: Sequence[Mapping[str, Any]], params: Mapping[str, Any]):
        closes = [float(c["close"]) for c in candles]
        mean = sum(closes) / len(closes)
        variance = sum((c - mean) ** 2 for c in closes) / len(closes)
        sd = variance**0.5
        return {"z": [None if sd == 0 else (c - mean) / sd for c in closes]}


def growing_rows(count: int = 200):
    return [(100 + i * 0.5, 100.5 + i * 0.5, 99.5 + i * 0.5, 100.2 + i * 0.5) for i in range(count)]


@pytest.fixture
def rogue_registry():
    """Register the deliberately broken indicators, then remove them again.

    Scoped and cleaned up so the shipped-library causality test cannot pick up
    a fixture that is *supposed* to fail.
    """
    IndicatorRegistry.register(CenteredAverage())
    IndicatorRegistry.register(FullSampleZScore())
    yield
    IndicatorRegistry.clear()
    IndicatorRegistry.discover()


# --------------------------------------------------------------------------- #
# Indicator-level detection
# --------------------------------------------------------------------------- #
def test_shipped_indicators_are_causal():
    candles = build_candles(growing_rows())
    for indicator in IndicatorRegistry.all():
        report = check_indicator_causality(indicator, candles)
        assert report["causal"], (
            f"{indicator.indicator_id} failed causality: {report.get('mismatches')}"
        )
        assert report["checks"] > 0


def test_a_centered_average_is_caught():
    candles = build_candles(growing_rows())
    report = check_indicator_causality(CenteredAverage(), candles)
    assert report["causal"] is False
    assert report["mismatches"]
    assert "repaint" in report["mismatches"][0]["message"]


def test_a_whole_sample_normalisation_is_caught():
    candles = build_candles(growing_rows())
    report = check_indicator_causality(FullSampleZScore(), candles)
    assert report["causal"] is False
    assert any(m["output"] == "z" for m in report["mismatches"])


def test_short_series_reports_untested_rather_than_causal():
    report = check_indicator_causality(CenteredAverage(), build_candles(growing_rows(8)))
    assert report["checked"] is False
    assert "too short" in report["reason"]


# --------------------------------------------------------------------------- #
# Rule-level detection
# --------------------------------------------------------------------------- #
def test_rules_are_causal_on_a_real_feature_set(candles):
    build = build_features(candles, [IndicatorSpec("fisher", {})])
    features = {**ohlcv_features(candles), **build.features}
    from app.indicator_research.signals.rules import evaluate_series

    long_signals = evaluate_series(LONG_ABOVE_100, features, len(candles))
    report = check_rule_causality(
        LONG_ABOVE_100, None, features, long_signals, [False] * len(candles)
    )
    assert report["causal"] is True
    assert report["scope"] == "rules_only"


def test_every_operator_survives_a_prefix_recompute(candles):
    """Each operator must produce the same answer when future bars are removed."""
    from app.indicator_research.signals.rules import evaluate_series

    for operator in ("crosses_above", "crosses_below", "turns_up", "turns_down", "slope_up", "slope_down"):
        rule = {"operator": "AND", "conditions": [{"left": "rsi", "operator": operator, "right": 50}]}
        features = build_features(candles, [IndicatorSpec("rsi", {})]).features
        signals = evaluate_series(rule, features, len(candles))
        report = check_rule_causality(rule, None, features, signals, [False] * len(candles))
        assert report["causal"], f"{operator} is not prefix-stable: {report['mismatches']}"


# --------------------------------------------------------------------------- #
# Full-recompute detection
# --------------------------------------------------------------------------- #
def test_feature_recompute_catches_a_non_causal_indicator(rogue_registry):
    candles = build_candles(growing_rows())
    specs = [IndicatorSpec("test_centered", {})]
    features = {**ohlcv_features(candles), **build_features(candles, specs).features}
    report = check_feature_causality(
        make_feature_provider(specs),
        candles,
        features,
        None,
        None,
        [False] * len(candles),
        [False] * len(candles),
    )
    assert report["causal"] is False
    assert any(m.get("feature") == "centered" for m in report["mismatches"])


def test_feature_recompute_passes_for_a_causal_library_indicator():
    candles = build_candles(growing_rows())
    specs = [IndicatorSpec("fisher", {"length": 9})]
    features = {**ohlcv_features(candles), **build_features(candles, specs).features}
    report = check_feature_causality(
        make_feature_provider(specs),
        candles,
        features,
        LONG_ABOVE_100,
        None,
        [False] * len(candles),
        [False] * len(candles),
    )
    assert report["causal"], report["mismatches"]


# --------------------------------------------------------------------------- #
# End-to-end: the badge must be withheld for a repainting feature set
# --------------------------------------------------------------------------- #
def test_validate_backtest_withholds_the_badge_for_a_repainting_feature(rogue_registry):
    candles = build_candles(growing_rows(120))
    specs = [IndicatorSpec("test_centered", {})]
    build = build_features(candles, specs)
    features = {**ohlcv_features(candles), **build.features}
    rule = {"operator": "AND", "conditions": [{"left": "close", "operator": ">", "right": "centered"}]}
    from app.indicator_research.signals.rules import evaluate_series

    signals = evaluate_series(rule, features, len(candles))
    report = validate_backtest(
        candles=candles,
        features=features,
        long_rule=rule,
        short_rule=None,
        long_signals=signals,
        short_signals=[False] * len(candles),
        trades=[],
        settings=BacktestSettings(
            execution=ExecutionSettings(entry_fill="next_open", initial_capital=100_000.0),
            exits=ExitSettings(),
        ),
        warmup_bars=build.warmup_bars,
        feature_provider=make_feature_provider(specs),
    )
    assert report["no_lookahead"] is False
    assert report["badge"].startswith("⚠")
    assert any("reads the future" in issue for issue in report["issues"])


def test_engine_badge_is_present_for_a_library_indicator(candles):
    build = build_features(candles, [IndicatorSpec("fisher", {})])
    result = BacktestEngine().run(
        candles=candles,
        features=build.features,
        long_rule={
            "operator": "AND",
            "conditions": [
                {"left": "fisher", "operator": "crosses_above", "right": "signal"},
            ],
        },
        settings=BacktestSettings(
            execution=ExecutionSettings(entry_fill="next_open", initial_capital=100_000.0),
            exits=ExitSettings(max_bars_held=10),
        ),
        timeframe="5m",
        indicator=IndicatorRegistry.get("fisher"),
        warmup_bars=build.warmup_bars,
    )
    assert result.ok, result.error
    assert result.validation["no_lookahead"] is True


def test_repaint_detection_uses_prefixes_not_the_whole_series():
    """The samples must include the final bar, where a future read is impossible."""
    candles = build_candles(growing_rows(150))
    report = check_indicator_causality(CenteredAverage(), candles)
    # The tail must be sampled: that is where a future read has nothing left to
    # read and the truncated series diverges.
    assert max(report["samples"]) >= 145
