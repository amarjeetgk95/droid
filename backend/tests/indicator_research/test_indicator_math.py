"""Hand-calculated checks of the helpers and of individual indicators.

These are the tests the build order demands before optimization is allowed to
exist: if a moving average or an RSI is subtly wrong, every result downstream is
wrong in the same direction and no amount of statistics will reveal it.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.indicator_research.indicators.base import IndicatorError
from app.indicator_research.indicators.helpers import (
    atr,
    ema,
    highest,
    linreg_slope,
    lowest,
    sma,
    stdev,
    true_range,
    vwap,
    wilder,
)
from app.indicator_research.indicators.registry import IndicatorRegistry
from tests.indicator_research.conftest import build_candles


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def test_sma_matches_hand_calculation():
    assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_sma_restarts_after_a_gap():
    # A missing input must not be averaged over: the window restarts.
    values = [1.0, 2.0, None, 4.0, 5.0, 6.0]
    result = sma(values, 2)
    assert result[0] is None
    assert result[1] == 1.5
    assert result[2] is None
    assert result[5] == 5.5


def test_ema_is_seeded_on_the_sma():
    # Seed = SMA(1,2,3) = 2 at index 2; k = 2/(3+1) = 0.5.
    assert ema([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_wilder_smoothing_recursion():
    # Seed = mean(1,2,3) = 2; then (2*2 + 4)/3 = 2.666..., then (2.666..*2 + 5)/3.
    result = wilder([1, 2, 3, 4, 5], 3)
    assert result[2] == pytest.approx(2.0)
    assert result[3] == pytest.approx(8 / 3)
    assert result[4] == pytest.approx((8 / 3 * 2 + 5) / 3)


def test_stdev_is_population_deviation():
    assert stdev([2, 4, 4, 4, 5, 5, 7, 9], 8) == [None] * 7 + [2.0]


def test_highest_and_lowest_windows():
    assert highest([1, 5, 3, 2], 2) == [None, 5, 5, 3]
    assert lowest([1, 5, 3, 2], 2) == [None, 1, 3, 2]


def test_linreg_slope_of_a_perfect_line():
    # Perfect line y = 2x + 1 -> slope 2.
    result = linreg_slope([1, 3, 5, 7], 4)
    assert result[3] == pytest.approx(2.0)


def test_true_range_includes_the_previous_close():
    candles = build_candles([(10, 11, 9, 10), (12, 13, 11.5, 12.5)])
    tr = true_range(candles)
    assert tr[0] == pytest.approx(2.0)
    # |high - prev close| = |13 - 10| = 3 beats high-low = 1.5.
    assert tr[1] == pytest.approx(3.0)


def test_atr_is_wilder_smoothed_true_range():
    candles = build_candles([(10, 11, 9, 10), (11, 12, 10, 11), (12, 13, 11, 12)])
    result = atr(candles, 2)
    assert result[0] is None
    # TRs are [2, 2, 2] -> seed at index 1 is 2.0, then stays 2.0.
    assert result[1] == pytest.approx(2.0)
    assert result[2] == pytest.approx(2.0)


def test_vwap_uses_typical_price_and_volume():
    candles = build_candles([(10, 12, 8, 10), (10, 12, 8, 10)])
    for candle in candles:
        candle["volume"] = 10
    # typical price = (12 + 8 + 10)/3 = 10 for both bars.
    result = vwap(candles, 0)
    assert result[0] == pytest.approx(10.0)
    assert result[1] == pytest.approx(10.0)


# --------------------------------------------------------------------------- #
# Indicator-level
# --------------------------------------------------------------------------- #
def test_registry_discovers_every_shipped_indicator():
    ids = set(IndicatorRegistry.ids())
    required = {
        "rsi",
        "macd",
        "fisher",
        "stoch_rsi",
        "wavetrend",
        "stc",
        "ebsw",
        "mama_fama",
        "dominant_cycle",
        "supertrend",
        "ema",
        "sma",
        "vwap",
        "atr",
        "bollinger",
        "adx",
        "cci",
        "williams_r",
    }
    missing = required - ids
    assert not missing, f"missing indicators: {sorted(missing)}"
    assert len(ids) >= 18


def test_every_indicator_declares_coherent_metadata():
    for indicator in IndicatorRegistry.all():
        meta = indicator.metadata
        assert meta.id and meta.id == meta.id.lower()
        assert meta.name
        assert meta.description
        assert meta.outputs, f"{meta.id} declares no outputs"
        for spec in meta.parameters:
            assert spec.default is not None
            if spec.min is not None and spec.max is not None:
                assert spec.min <= spec.max
                assert spec.min <= spec.default <= spec.max, (
                    f"{meta.id}.{spec.name} default {spec.default} outside "
                    f"[{spec.min}, {spec.max}]"
                )
        for out in meta.outputs:
            assert out.pane is not None and out.role is not None


def test_every_indicator_computes_on_a_real_series(candles):
    for indicator in IndicatorRegistry.all():
        result = indicator.compute(candles)
        assert result.length == len(candles)
        for name, series in result.outputs.items():
            assert len(series) == len(candles), f"{indicator.indicator_id}.{name} length"
        defined = [
            i
            for i in range(len(candles))
            if all(series[i] is not None for series in result.outputs.values())
        ]
        assert defined, f"{indicator.indicator_id} never produced a defined reading"


def test_outputs_are_never_zero_filled_during_warmup(candles):
    """A zero during warm-up would look like a real reading to a rule."""
    for indicator in IndicatorRegistry.all():
        result = indicator.compute(candles)
        if result.warmup_bars <= 0:
            continue
        for name, series in result.outputs.items():
            head = series[: result.warmup_bars]
            assert any(v is None for v in head), (
                f"{indicator.indicator_id}.{name} has no gaps before its warm-up"
            )


def test_sma_indicator_matches_the_helper(candles):
    indicator = IndicatorRegistry.get_or_raise("sma")
    result = indicator.compute(candles, {"length": 20})
    closes = [c["close"] for c in candles]
    assert result.outputs["sma"] == sma(closes, 20)


def test_rsi_on_a_monotonic_rise_is_one_hundred(candles):
    indicator = IndicatorRegistry.get_or_raise("rsi")
    rising = build_candles([(i, i + 1, i - 1, i) for i in range(1, 40)])
    result = indicator.compute(rising, {"length": 14})
    assert result.outputs["rsi"][14] == pytest.approx(100.0)


def test_rsi_on_a_monotonic_fall_is_zero():
    indicator = IndicatorRegistry.get_or_raise("rsi")
    falling = build_candles([(40 - i, 41 - i, 39 - i, 40 - i) for i in range(40)])
    result = indicator.compute(falling, {"length": 14})
    assert result.outputs["rsi"][14] == pytest.approx(0.0)


def test_macd_equals_the_difference_of_its_emas(candles):
    indicator = IndicatorRegistry.get_or_raise("macd")
    params = {"fast_length": 12, "slow_length": 26, "signal_length": 9, "source": "close"}
    result = indicator.compute(candles, params)
    closes = [c["close"] for c in candles]
    fast = ema(closes, 12)
    slow = ema(closes, 26)
    for index in (40, 100, 250):
        assert result.outputs["macd"][index] == pytest.approx(fast[index] - slow[index])


def test_bollinger_bands_are_symmetric_around_the_middle(candles):
    indicator = IndicatorRegistry.get_or_raise("bollinger")
    result = indicator.compute(candles, {"length": 20, "std_dev": 2.0, "source": "close"})
    closes = [c["close"] for c in candles]
    middle = sma(closes, 20)
    for index in (25, 120, 399):
        upper = result.outputs["upper"][index]
        lower = result.outputs["lower"][index]
        assert upper - middle[index] == pytest.approx(middle[index] - lower)
        assert 0.0 <= result.outputs["percent_b"][index] <= 1.0


def test_williams_r_bounds_and_orientation():
    indicator = IndicatorRegistry.get_or_raise("williams_r")
    # Close at the top of the range must read 0; at the bottom, -100.
    at_high = build_candles([(10, 20, 10, 20) for _ in range(5)])
    at_low = build_candles([(10, 20, 10, 10) for _ in range(5)])
    assert indicator.compute(at_high, {"length": 3}).outputs["williams_r"][4] == pytest.approx(0.0)
    assert indicator.compute(at_low, {"length": 3}).outputs["williams_r"][4] == pytest.approx(-100.0)


def test_donchian_channel_brackets_price(candles):
    indicator = IndicatorRegistry.get_or_raise("donchian")
    result = indicator.compute(candles, {"length": 20})
    for index in range(25, len(candles)):
        assert result.outputs["lower"][index] <= candles[index]["close"] <= result.outputs["upper"][index]
        assert result.outputs["middle"][index] == pytest.approx(
            (result.outputs["upper"][index] + result.outputs["lower"][index]) / 2
        )


def test_supertrend_direction_is_plus_or_minus_one(candles):
    indicator = IndicatorRegistry.get_or_raise("supertrend")
    result = indicator.compute(candles, {"length": 10, "multiplier": 3.0})
    directions = [d for d in result.outputs["direction"] if d is not None]
    assert directions
    assert set(directions) <= {1, -1}


def test_adx_is_bounded_and_positive(candles):
    indicator = IndicatorRegistry.get_or_raise("adx")
    result = indicator.compute(candles, {"length": 14})
    for index in range(30, len(candles)):
        adx = result.outputs["adx"][index]
        if adx is None:
            continue
        assert 0.0 <= adx <= 100.0
        assert result.outputs["plus_di"][index] >= 0.0
        assert result.outputs["minus_di"][index] >= 0.0


def test_ebsw_wave_is_normalised_into_minus_one_to_one(candles):
    indicator = IndicatorRegistry.get_or_raise("ebsw")
    result = indicator.compute(candles, {"hp_period": 40, "ssf_period": 10, "source": "close"})
    values = [v for v in result.outputs["ebsw"] if v is not None]
    assert values
    assert min(values) >= -1.0001 and max(values) <= 1.0001


def test_mama_alpha_respects_the_configured_limits(candles):
    indicator = IndicatorRegistry.get_or_raise("mama_fama")
    result = indicator.compute(
        candles, {"fast_limit": 0.5, "slow_limit": 0.05, "source": "hl2"}
    )
    alphas = [a for a in result.outputs["alpha"] if a is not None]
    assert alphas
    assert min(alphas) >= 0.05 - 1e-9
    assert max(alphas) <= 0.5 + 1e-9


def test_dominant_cycle_stays_inside_the_requested_band(candles):
    indicator = IndicatorRegistry.get_or_raise("dominant_cycle")
    result = indicator.compute(
        candles, {"window": 64, "min_period": 6, "max_period": 32, "source": "close"}
    )
    lengths = [v for v in result.outputs["cycle_length"] if v is not None]
    strengths = [v for v in result.outputs["cycle_strength"] if v is not None]
    assert lengths
    assert min(lengths) >= 6 and max(lengths) <= 32
    assert all(-1.0001 <= s <= 1.0001 for s in strengths)


def test_stc_is_bounded_zero_to_one_hundred(candles):
    indicator = IndicatorRegistry.get_or_raise("stc")
    result = indicator.compute(
        candles,
        {"stc_length": 10, "fast_length": 23, "slow_length": 50, "factor": 0.5, "source": "close"},
    )
    values = [v for v in result.outputs["stc"] if v is not None]
    assert values
    assert min(values) >= -1e-9 and max(values) <= 100.0 + 1e-9


# --------------------------------------------------------------------------- #
# Parameter contract
# --------------------------------------------------------------------------- #
def test_unknown_parameters_are_rejected():
    indicator = IndicatorRegistry.get_or_raise("rsi")
    with pytest.raises(IndicatorError) as exc:
        indicator.compute(build_candles([(1, 1, 1, 1)] * 30), {"lenght": 14})
    assert "Unknown parameter" in str(exc.value)


def test_parameters_are_clamped_into_their_declared_range():
    indicator = IndicatorRegistry.get_or_raise("rsi")
    resolved = indicator.resolve_params({"length": 9999})
    assert resolved["length"] == 100  # declared maximum


def test_parameters_are_coerced_to_their_declared_type():
    indicator = IndicatorRegistry.get_or_raise("bollinger")
    resolved = indicator.resolve_params({"length": "15", "std_dev": "2.5"})
    assert resolved["length"] == 15 and isinstance(resolved["length"], int)
    assert resolved["std_dev"] == 2.5 and isinstance(resolved["std_dev"], float)


def test_choice_parameters_reject_values_outside_their_options():
    indicator = IndicatorRegistry.get_or_raise("sma")
    with pytest.raises(IndicatorError):
        indicator.resolve_params({"source": "vwap"})


def test_undeclared_outputs_are_a_hard_error():
    from app.indicator_research.indicators.base import (
        BaseIndicator,
        IndicatorMetadata,
        OutputSpec,
    )
    from app.indicator_research.enums import IndicatorCategory, OutputType

    class Rogue(BaseIndicator):
        METADATA = IndicatorMetadata(
            id="rogue",
            name="Rogue",
            category=IndicatorCategory.CUSTOM,
            description="returns an output it never declared",
            output_type=OutputType.OSCILLATOR,
            outputs=(OutputSpec("declared"),),
        )

        def calculate(self, candles, params):
            return {"declared": [1.0] * len(candles), "surprise": [2.0] * len(candles)}

    with pytest.raises(IndicatorError) as exc:
        Rogue().compute(build_candles([(1, 1, 1, 1)] * 5))
    assert "undeclared" in str(exc.value)


def test_output_length_must_match_the_candle_series():
    from app.indicator_research.indicators.base import (
        BaseIndicator,
        IndicatorMetadata,
        OutputSpec,
    )
    from app.indicator_research.enums import IndicatorCategory, OutputType

    class Short(BaseIndicator):
        METADATA = IndicatorMetadata(
            id="shorty",
            name="Shorty",
            category=IndicatorCategory.CUSTOM,
            description="returns a truncated series",
            output_type=OutputType.OSCILLATOR,
            outputs=(OutputSpec("value"),),
        )

        def calculate(self, candles, params):
            return {"value": [1.0] * max(1, len(candles) - 2)}

    with pytest.raises(IndicatorError) as exc:
        Short().compute(build_candles([(1, 1, 1, 1)] * 20))
    assert "expected 20" in str(exc.value)


def test_concrete_indicators_must_declare_metadata():
    from app.indicator_research.indicators.base import BaseIndicator

    with pytest.raises(TypeError):

        class NoMetadata(BaseIndicator):
            def calculate(self, candles, params):
                return {}


def test_adding_an_indicator_file_is_enough(tmp_path):
    """Dropping a module into the package must register it everywhere."""
    package_dir = tmp_path / "samplepkg"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "myindicator.py").write_text(
        '''
from typing import Any, ClassVar, Mapping, Sequence
from app.indicator_research.enums import IndicatorCategory, OutputType
from app.indicator_research.indicators.base import (
    BaseIndicator, IndicatorMetadata, OutputSpec,
)


class MyIndicator(BaseIndicator):
    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="my_indicator",
        name="My Indicator",
        category=IndicatorCategory.CUSTOM,
        description="A one-file indicator.",
        output_type=OutputType.OSCILLATOR,
        outputs=(OutputSpec("my_indicator"),),
    )

    def calculate(self, candles: Sequence[Mapping[str, Any]], params: Mapping[str, Any]):
        return {"my_indicator": [float(len(candles))] * len(candles)}
''',
        encoding="utf-8",
    )

    installed = IndicatorRegistry.get("my_indicator")
    assert installed is None

    import sys
    import app.indicator_research.indicators as package

    original_path = list(package.__path__)
    package.__path__.append(str(package_dir))
    sys.path.insert(0, str(tmp_path))
    try:
        IndicatorRegistry.discover(force=True)
        assert "my_indicator" in IndicatorRegistry.ids()
        result = IndicatorRegistry.get_or_raise("my_indicator").compute(
            build_candles([(1, 1, 1, 1)] * 3)
        )
        assert result.outputs["my_indicator"] == [3.0, 3.0, 3.0]
    finally:
        sys.path.remove(str(tmp_path))
        package.__path__[:] = original_path
        IndicatorRegistry.clear()
        IndicatorRegistry.discover()
