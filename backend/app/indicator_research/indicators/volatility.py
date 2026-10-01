"""Volatility indicators.

ATR and Bollinger Bands. ATR is the backbone of the risk model: stop-loss and
take-profit distances are expressed in ATR multiples so a strategy's risk is
measured in the units the market is actually moving in, not in fixed points
that silently tighten in quiet regimes and loosen in fast ones.
"""

from __future__ import annotations

from typing import Any, ClassVar, Mapping, Sequence

from app.indicator_research.enums import (
    IndicatorCategory,
    OutputRole,
    OutputType,
    PaneHint,
    ParameterType,
)
from app.indicator_research.indicators.base import (
    BaseIndicator,
    Candle,
    IndicatorMetadata,
    OutputSpec,
    ParameterSpec,
)
from app.indicator_research.indicators.helpers import (
    SOURCE_CHOICES,
    atr,
    finite,
    sma,
    source_series,
    stdev,
)


class AtrIndicator(BaseIndicator):
    """Wilder Average True Range."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="atr",
        name="ATR",
        category=IndicatorCategory.VOLATILITY,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "Wilder's average true range, including gaps via the previous "
            "close. It measures how far the market travels, never which way. "
            "Any comparison of ATR levels across instruments must be done in "
            "percent terms, which is why atr_percent is provided alongside."
        ),
        parameters=(
            ParameterSpec("length", ParameterType.INTEGER, 14, 2, 200, 1, label="Length"),
        ),
        outputs=(
            OutputSpec("atr", OutputRole.LINE, PaneHint.SEPARATE, label="ATR"),
            OutputSpec("atr_percent", OutputRole.LINE, PaneHint.SEPARATE,
                       label="ATR %", description="ATR as a percentage of close."),
        ),
        formula_summary="TR = max(H-L, |H-C[-1]|, |L-C[-1]|); ATR = Wilder(TR, n)",
        version="1.0.0",
        tags=("volatility", "risk"),
    )

    # ATR has no directional content, so there is no honest default entry
    # rule to ship. The UI shows "no default rules — build one" rather than
    # inventing a trigger.
    DEFAULT_RULES: ClassVar[dict[str, Any] | None] = None

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        length = int(params["length"])
        atr_series = atr(candles, length)
        pct: list[Any] = [None] * len(candles)
        for i, candle in enumerate(candles):
            a = atr_series[i]
            cl = finite(candle.get("close"))
            if a is None or not cl:
                continue
            pct[i] = 100.0 * a / cl
        return {"atr": atr_series, "atr_percent": pct}


class BollingerBandsIndicator(BaseIndicator):
    """Bollinger Bands."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="bollinger",
        name="Bollinger Bands",
        category=IndicatorCategory.VOLATILITY,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "Moving average with bands one standard deviation multiple away. "
            "Band touch is not a reversal signal: in a trending market price "
            "'walks the band', and a touch-based mean-reversion rule loses "
            "money precisely when the trend is strongest. bandwidth and "
            "percent_b are exposed so a rule can require a squeeze or a "
            "confirmed excursion instead of a bare touch."
        ),
        parameters=(
            ParameterSpec("length", ParameterType.INTEGER, 20, 2, 500, 1, label="Length"),
            ParameterSpec("std_dev", ParameterType.NUMBER, 2.0, 0.5, 5.0, 0.1,
                          label="Std dev multiple"),
            ParameterSpec("source", ParameterType.CHOICE, "close", options=SOURCE_CHOICES,
                          label="Price source"),
        ),
        outputs=(
            OutputSpec("upper", OutputRole.BAND_UPPER, PaneHint.PRICE),
            OutputSpec("middle", OutputRole.BAND_MIDDLE, PaneHint.PRICE),
            OutputSpec("lower", OutputRole.BAND_LOWER, PaneHint.PRICE),
            OutputSpec("bandwidth", OutputRole.LINE, PaneHint.SEPARATE,
                       label="Bandwidth %"),
            OutputSpec("percent_b", OutputRole.LINE, PaneHint.SEPARATE,
                       label="%B", description="0 at lower band, 1 at upper band."),
        ),
        formula_summary=(
            "middle = SMA(source, n); upper/lower = middle ± k*stdev(source, n); "
            "bandwidth = 100*(upper-lower)/middle; %B = (source-lower)/(upper-lower)"
        ),
        version="1.0.0",
        tags=("volatility", "mean_reversion", "squeeze"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [
                {"left": "percent_b", "operator": "crosses_above", "right": 0.0},
            ],
        },
        "short": {
            "operator": "AND",
            "conditions": [
                {"left": "percent_b", "operator": "crosses_below", "right": 1.0},
            ],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        length = int(params["length"])
        k = float(params["std_dev"])
        src = source_series(candles, str(params["source"]))
        middle = sma(src, length)
        sd = stdev(src, length)
        n = len(src)
        upper: list[Any] = [None] * n
        lower: list[Any] = [None] * n
        bandwidth: list[Any] = [None] * n
        percent_b: list[Any] = [None] * n
        for i in range(n):
            m, s, v = middle[i], sd[i], src[i]
            if m is None or s is None:
                continue
            up = m + k * s
            lo = m - k * s
            upper[i] = up
            lower[i] = lo
            if m:
                bandwidth[i] = 100.0 * (up - lo) / m
            span = up - lo
            if v is not None and span != 0:
                percent_b[i] = (v - lo) / span
        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "bandwidth": bandwidth,
            "percent_b": percent_b,
        }
