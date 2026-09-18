"""Pinned metadata contract for the built-in research indicators (§46).

The five identity/classification fields (indicator_id/name/version/category/
lifecycle) are declared once per class as ``METADATA = IndicatorMetadata(...)``
and surfaced by :class:`IndicatorBase` properties. These tests pin the exact
values plus the full ``get_definition()`` payload captured before the metadata
dedupe, so any drift in registry/API surface fails loudly.
"""

from __future__ import annotations

import json

import pytest

from app.research.enums import IndicatorCategory, IndicatorLifecycle
from app.research.indicators import (  # noqa: F401  (import registers all built-ins)
    MACDIndicator,
    MomentumIndicator,
    OMPIIndicator,
    RSIIndicator,
    VWAPIndicator,
)
from app.research.indicators.base import BuiltinIndicator
from app.research.indicator_base import IndicatorMetadata
from app.research.registry import IndicatorRegistry

INDICATOR_CLASSES = {
    "rsi": RSIIndicator,
    "vwap": VWAPIndicator,
    "macd": MACDIndicator,
    "momentum": MomentumIndicator,
    "ompi": OMPIIndicator,
}

_PINNED_METADATA = {
    "rsi": {
        "indicator_id": "rsi",
        "name": "Relative Strength Index (RSI)",
        "version": "1.0.0",
        "category": IndicatorCategory.STANDARD,
        "lifecycle": IndicatorLifecycle.PRODUCTION,
    },
    "vwap": {
        "indicator_id": "vwap",
        "name": "Volume Weighted Average Price (VWAP)",
        "version": "1.0.0",
        "category": IndicatorCategory.STANDARD,
        "lifecycle": IndicatorLifecycle.PRODUCTION,
    },
    "macd": {
        "indicator_id": "macd",
        "name": "Moving Average Convergence Divergence (MACD)",
        "version": "1.0.0",
        "category": IndicatorCategory.STANDARD,
        "lifecycle": IndicatorLifecycle.PRODUCTION,
    },
    "momentum": {
        "indicator_id": "momentum",
        "name": "Multi-Period Momentum Composite",
        "version": "1.0.0",
        "category": IndicatorCategory.STANDARD,
        "lifecycle": IndicatorLifecycle.PRODUCTION,
    },
    "ompi": {
        "indicator_id": "ompi",
        "name": "Option Market Pressure Index (OMPI)",
        "version": "0.1.0",
        "category": IndicatorCategory.PROPRIETARY,
        "lifecycle": IndicatorLifecycle.EXPERIMENTAL,
    },
}

_PINNED_SCHEMAS = {
    "rsi": {
        "period": {"default": 14, "type": "int"},
        "overbought": {"default": 70, "type": "int"},
        "oversold": {"default": 30, "type": "int"},
        "bull_threshold": {"default": 10.0, "type": "float"},
        "bear_threshold": {"default": -10.0, "type": "float"},
    },
    "vwap": {
        "scale_factor": {"default": 50.0, "type": "float"},
        "neutral_band_pct": {"default": 0.08, "type": "float"},
    },
    "macd": {
        "fast_period": {"default": 12, "type": "int"},
        "slow_period": {"default": 26, "type": "int"},
        "signal_period": {"default": 9, "type": "int"},
    },
    "momentum": {
        "p_fast": {"default": 5, "type": "int"},
        "p_mid": {"default": 14, "type": "int"},
        "p_slow": {"default": 20, "type": "int"},
        "scale": {"default": 100.0, "type": "float"},
    },
    "ompi": {
        "w_dir": {"default": 0.3, "type": "float"},
        "w_opt": {"default": 0.25, "type": "float"},
        "w_part": {"default": 0.2, "type": "float"},
        "w_vol": {"default": 0.15, "type": "float"},
        "w_decay": {"default": 0.1, "type": "float"},
        "bull_threshold": {"default": 20.0, "type": "float"},
        "bear_threshold": {"default": -20.0, "type": "float"},
    },
}

_PINNED_DEFINITIONS = {
    "rsi": {
        "indicator_id": "rsi",
        "name": "Relative Strength Index (RSI)",
        "category": "STANDARD",
        "description": "14-period Relative Strength Index with Wilder's smoothing, centered at 0 on [-100, +100].",
        "author": "system",
        "lifecycle": "PRODUCTION",
        "current_version": "1.0.0",
        "supported_timeframes": ["1m", "5m", "15m", "1h", "1D"],
        "supported_instruments": ["NIFTY 50", "BANKNIFTY", "SENSEX"],
        "formula_summary": "Score = (RSI(14) - 50) * 2; Bullish > 10, Bearish < -10",
        "parameters_schema": _PINNED_SCHEMAS["rsi"],
        "created_at": None,
        "updated_at": None,
    },
    "vwap": {
        "indicator_id": "vwap",
        "name": "Volume Weighted Average Price (VWAP)",
        "category": "STANDARD",
        "description": "Intraday volume-weighted average price benchmark with distance-based normalization.",
        "author": "system",
        "lifecycle": "PRODUCTION",
        "current_version": "1.0.0",
        "supported_timeframes": ["1m", "5m", "15m", "1h", "1D"],
        "supported_instruments": ["NIFTY 50", "BANKNIFTY", "SENSEX"],
        "formula_summary": "Distance% = (Price - VWAP) / VWAP * 100; Scaled into [-100, 100]",
        "parameters_schema": _PINNED_SCHEMAS["vwap"],
        "created_at": None,
        "updated_at": None,
    },
    "macd": {
        "indicator_id": "macd",
        "name": "Moving Average Convergence Divergence (MACD)",
        "category": "STANDARD",
        "description": "Classic 12/26/9 trend-following momentum indicator with volatility-scaled histogram.",
        "author": "system",
        "lifecycle": "PRODUCTION",
        "current_version": "1.0.0",
        "supported_timeframes": ["1m", "5m", "15m", "1h", "1D"],
        "supported_instruments": ["NIFTY 50", "BANKNIFTY", "SENSEX"],
        "formula_summary": "MACD = EMA(12) - EMA(26); Signal = EMA(MACD, 9); Hist = MACD - Signal",
        "parameters_schema": _PINNED_SCHEMAS["macd"],
        "created_at": None,
        "updated_at": None,
    },
    "momentum": {
        "indicator_id": "momentum",
        "name": "Multi-Period Momentum Composite",
        "category": "STANDARD",
        "description": "Composite momentum score based on weighted short, medium, and long Rate of Change (ROC).",
        "author": "system",
        "lifecycle": "PRODUCTION",
        "current_version": "1.0.0",
        "supported_timeframes": ["1m", "5m", "15m", "1h", "1D"],
        "supported_instruments": ["NIFTY 50", "BANKNIFTY", "SENSEX"],
        "formula_summary": "Score = 0.5 * ROC(5) + 0.3 * ROC(14) + 0.2 * ROC(20); Normalized to [-100, 100]",
        "parameters_schema": _PINNED_SCHEMAS["momentum"],
        "created_at": None,
        "updated_at": None,
    },
    "ompi": {
        "indicator_id": "ompi",
        "name": "Option Market Pressure Index (OMPI)",
        "category": "PROPRIETARY",
        "description": "Proprietary 5-vector composite measuring underlying directional momentum, options positioning (PCR/walls/max pain), volume participation, volatility regime, and theta decay friction.",
        "author": "system",
        "lifecycle": "EXPERIMENTAL",
        "current_version": "0.1.0",
        "supported_timeframes": ["1m", "5m", "15m", "1h", "1D"],
        "supported_instruments": ["NIFTY 50", "BANKNIFTY", "SENSEX"],
        "formula_summary": "OMPI = 0.30*P_dir + 0.25*P_opt + 0.20*P_part + 0.15*P_vol + 0.10*P_decay; Bullish >= 20.0, Bearish <= -20.0",
        "parameters_schema": _PINNED_SCHEMAS["ompi"],
        "created_at": None,
        "updated_at": None,
    },
}


@pytest.mark.parametrize("indicator_id", sorted(_PINNED_METADATA))
def test_metadata_matches_pinned_values(indicator_id):
    ind = INDICATOR_CLASSES[indicator_id]()
    expected = _PINNED_METADATA[indicator_id]
    assert ind.indicator_id == expected["indicator_id"]
    assert ind.name == expected["name"]
    assert ind.version == expected["version"]
    assert ind.category == expected["category"]
    assert ind.lifecycle == expected["lifecycle"]


@pytest.mark.parametrize("indicator_id", sorted(_PINNED_METADATA))
def test_metadata_is_single_source(indicator_id):
    ind = INDICATOR_CLASSES[indicator_id]()
    assert isinstance(ind.METADATA, IndicatorMetadata)
    assert (ind.indicator_id, ind.name, ind.version, ind.category, ind.lifecycle) == (
        ind.METADATA.indicator_id,
        ind.METADATA.name,
        ind.METADATA.version,
        ind.METADATA.category,
        ind.METADATA.lifecycle,
    )


@pytest.mark.parametrize("indicator_id", sorted(_PINNED_DEFINITIONS))
def test_get_definition_matches_pinned_baseline(indicator_id):
    ind = INDICATOR_CLASSES[indicator_id]()
    assert ind.get_definition().model_dump(mode="json") == _PINNED_DEFINITIONS[indicator_id]


@pytest.mark.parametrize("indicator_id", sorted(_PINNED_SCHEMAS))
def test_parameters_schema_round_trip(indicator_id):
    ind = INDICATOR_CLASSES[indicator_id]()
    schema = ind.get_parameters_schema()
    assert schema == _PINNED_SCHEMAS[indicator_id]

    rebuilt = {
        key: {"type": type(value).__name__, "default": value}
        for key, value in ind.default_parameters.items()
    }
    assert schema == rebuilt
    assert ind.get_definition().parameters_schema == schema
    # JSON round-trip stays lossless for the API/DB payloads.
    assert json.loads(json.dumps(schema)) == schema
    assert ind.get_parameters_schema() == schema


def test_registry_definitions_match_pinned_baseline():
    registry_defs = {d.indicator_id: d.model_dump(mode="json") for d in IndicatorRegistry.list_all()}
    for indicator_id, pinned in _PINNED_DEFINITIONS.items():
        assert registry_defs[indicator_id] == pinned


def test_concrete_subclass_without_metadata_rejected():
    with pytest.raises(TypeError, match="METADATA"):

        class _ConcreteMissingMetadata(BuiltinIndicator):
            async def calculate(self, context):  # pragma: no cover - never run
                raise NotImplementedError


def test_abstract_subclass_without_metadata_allowed():
    import inspect

    class _AbstractNoMetadata(BuiltinIndicator):
        pass

    assert inspect.isabstract(_AbstractNoMetadata)
    assert inspect.isabstract(BuiltinIndicator)


def test_custom_concrete_subclass_with_metadata_uses_default_lifecycle():
    class _Custom(BuiltinIndicator):
        METADATA = IndicatorMetadata(
            indicator_id="custom_test",
            name="Custom Test",
            version="9.9.9",
            category=IndicatorCategory.EXPERIMENTAL,
        )

        async def calculate(self, context):  # pragma: no cover - never run
            raise NotImplementedError

    ind = _Custom()
    assert ind.indicator_id == "custom_test"
    assert ind.version == "9.9.9"
    assert ind.lifecycle == IndicatorLifecycle.EXPERIMENTAL
    assert ind.get_definition().current_version == "9.9.9"
