import pytest

from app.indicator_research.indicators.registry import IndicatorRegistry
from app.indicator_research.presets import CANONICAL_PRESETS, get_preset, list_presets


def test_canonical_presets_completeness():
    presets = list_presets()
    assert len(presets) == 6
    preset_ids = {p["id"] for p in presets}
    expected = {
        "ehlers_cycle_reversal",
        "trend_momentum",
        "order_flow_absorption",
        "dpfi_breakout",
        "stoch_rsi_mean_reversion",
        "stc_mama_timing",
    }
    assert preset_ids == expected


def test_presets_indicators_exist_in_registry():
    presets = list_presets()
    for preset in presets:
        assert get_preset(preset["id"]) is not None
        for ind in preset["indicators"]:
            indicator = IndicatorRegistry.get(ind["indicator_id"])
            assert indicator is not None, f"Indicator {ind['indicator_id']} in preset {preset['id']} not in registry"
            # Verify declared parameters exist on indicator metadata
            known_params = {p.name for p in indicator.parameters}
            for p_name in ind["params"]:
                assert p_name in known_params, f"Param {p_name} not found on indicator {indicator.indicator_id}"
