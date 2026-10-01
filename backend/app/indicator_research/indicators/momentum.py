"""Momentum indicators.

RSI, MACD, Fisher Transform, Stochastic RSI, WaveTrend, CCI, Williams %R and
the Schaff Trend Cycle.
"""

from __future__ import annotations

import math
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
    diff,
    ema,
    ema_alpha,
    finite,
    highest,
    highest as rolling_high,
    lowest,
    sma,
    source_series,
    wilder,
)


def _rsi_series(src: Sequence[float | None], length: int) -> list[float | None]:
    """Wilder RSI. ``None`` until ``length`` price changes exist."""
    changes = diff(src, 1)
    gains: list[float | None] = [None] * len(src)
    losses: list[float | None] = [None] * len(src)
    for i, d in enumerate(changes):
        if d is None:
            continue
        gains[i] = d if d > 0 else 0.0
        losses[i] = -d if d < 0 else 0.0
    avg_gain = wilder(gains, length)
    avg_loss = wilder(losses, length)
    out: list[float | None] = [None] * len(src)
    for i in range(len(src)):
        g, l = avg_gain[i], avg_loss[i]
        if g is None or l is None:
            continue
        if l == 0.0:
            out[i] = 100.0 if g > 0 else 50.0
        else:
            rs = g / l
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def _stoch(values: Sequence[float | None], length: int) -> list[float | None]:
    """Percentile rank of the current value within its trailing window, 0-100."""
    hi = highest(values, length)
    lo = lowest(values, length)
    out: list[float | None] = [None] * len(values)
    for i, v in enumerate(values):
        h, l = hi[i], lo[i]
        if v is None or h is None or l is None:
            continue
        span = h - l
        val = 50.0 if span == 0 else 100.0 * (v - l) / span
        out[i] = max(0.0, min(100.0, val))
    return out


class RsiIndicator(BaseIndicator):
    """Wilder Relative Strength Index."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="rsi",
        name="RSI",
        category=IndicatorCategory.MOMENTUM,
        output_type=OutputType.OSCILLATOR,
        description=(
            "Wilder's Relative Strength Index, 0-100. Bounded, mean-reverting "
            "and smooth. A '70 overbought' reading is a description of recent "
            "gains, not a sell signal — in a strong trend RSI stays extreme for "
            "a long time, which is exactly the condition an RSI-threshold rule "
            "gets wrong."
        ),
        parameters=(
            ParameterSpec("length", ParameterType.INTEGER, 14, 2, 100, 1, label="Length"),
            ParameterSpec("source", ParameterType.CHOICE, "close", options=SOURCE_CHOICES,
                          label="Price source"),
        ),
        outputs=(OutputSpec("rsi", OutputRole.LINE, PaneHint.SEPARATE, label="RSI"),),
        formula_summary=(
            "RSI = 100 - 100/(1+RS); RS = Wilder(avg gain)/Wilder(avg loss)"
        ),
        version="1.0.0",
        tags=("momentum", "oscillator", "mean_reversion"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [
                {"left": "rsi", "operator": "crosses_above", "right": 30},
                {"left": "rsi", "operator": "turns_up"},
            ],
        },
        "short": {
            "operator": "AND",
            "conditions": [
                {"left": "rsi", "operator": "crosses_below", "right": 70},
                {"left": "rsi", "operator": "turns_down"},
            ],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        src = source_series(candles, str(params["source"]))
        return {"rsi": _rsi_series(src, int(params["length"]))}


class MacdIndicator(BaseIndicator):
    """Moving Average Convergence Divergence."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="macd",
        name="MACD",
        category=IndicatorCategory.MOMENTUM,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "Difference of two EMAs with a signal EMA of that difference. The "
            "histogram is the fastest of the three and the most prone to "
            "flipping on noise; the signal-line cross lags the histogram turn."
        ),
        parameters=(
            ParameterSpec("fast_length", ParameterType.INTEGER, 12, 2, 200, 1, label="Fast EMA"),
            ParameterSpec("slow_length", ParameterType.INTEGER, 26, 3, 400, 1, label="Slow EMA"),
            ParameterSpec("signal_length", ParameterType.INTEGER, 9, 1, 100, 1, label="Signal EMA"),
            ParameterSpec("source", ParameterType.CHOICE, "close", options=SOURCE_CHOICES,
                          label="Price source"),
        ),
        outputs=(
            OutputSpec("macd", OutputRole.LINE, PaneHint.SEPARATE, label="MACD"),
            OutputSpec("signal", OutputRole.LINE, PaneHint.SEPARATE, label="Signal"),
            OutputSpec("histogram", OutputRole.HISTOGRAM, PaneHint.SEPARATE, label="Histogram"),
        ),
        formula_summary="MACD = EMA(fast) - EMA(slow); signal = EMA(MACD, k); hist = MACD - signal",
        version="1.0.0",
        tags=("momentum", "trend", "oscillator"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [
                {"left": "macd", "operator": "crosses_above", "right": "signal"},
                {"left": "macd", "operator": "<", "right": 0},
            ],
        },
        "short": {
            "operator": "AND",
            "conditions": [
                {"left": "macd", "operator": "crosses_below", "right": "signal"},
                {"left": "macd", "operator": ">", "right": 0},
            ],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        src = source_series(candles, str(params["source"]))
        fast = ema(src, int(params["fast_length"]))
        slow = ema(src, int(params["slow_length"]))
        macd: list[Any] = [None] * len(src)
        for i in range(len(src)):
            if fast[i] is not None and slow[i] is not None:
                macd[i] = fast[i] - slow[i]
        signal = ema(macd, int(params["signal_length"]))
        hist: list[Any] = [None] * len(src)
        for i in range(len(src)):
            if macd[i] is not None and signal[i] is not None:
                hist[i] = macd[i] - signal[i]
        return {"macd": macd, "signal": signal, "histogram": hist}


class FisherTransformIndicator(BaseIndicator):
    """Ehlers Fisher Transform."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="fisher",
        name="Fisher Transform",
        category=IndicatorCategory.MOMENTUM,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "Non-linear transform of price's position inside its recent range. "
            "The transform sharpens turning points into visible spikes, which "
            "makes it popular and also makes it noisy: extremes mark where "
            "price has been, not where it is going. The recursion is "
            "path-dependent and evaluated bar by bar."
        ),
        parameters=(
            ParameterSpec("length", ParameterType.INTEGER, 9, 2, 100, 1,
                          label="Length", description="Range lookback."),
            ParameterSpec("signal_length", ParameterType.INTEGER, 1, 1, 50, 1,
                          label="Signal offset",
                          description="Bars the signal line lags the fisher line (1 = Ehlers' trigger)."),
        ),
        outputs=(
            OutputSpec("fisher", OutputRole.LINE, PaneHint.SEPARATE, label="Fisher"),
            OutputSpec("signal", OutputRole.LINE, PaneHint.SEPARATE, label="Trigger"),
        ),
        formula_summary=(
            "norm = (price - min)/(max - min); value = 0.66*(norm - 0.5) + 0.67*value[-1]; "
            "fisher = 0.5*ln((1+value)/(1-value)) + 0.5*fisher[-1]"
        ),
        version="1.0.0",
        reference="Ehlers, 'Fisher Transform' (TASC 2002)",
        tags=("momentum", "cycle", "oscillator"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [
                {"left": "fisher", "operator": "crosses_above", "right": "signal"},
                {"left": "fisher", "operator": "<", "right": -1.0},
            ],
        },
        "short": {
            "operator": "AND",
            "conditions": [
                {"left": "fisher", "operator": "crosses_below", "right": "signal"},
                {"left": "fisher", "operator": ">", "right": 1.0},
            ],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        length = int(params["length"])
        offset = max(1, int(params["signal_length"]))
        n = len(candles)
        price: list[float | None] = [None] * n
        for i, c in enumerate(candles):
            hi, lo = finite(c.get("high")), finite(c.get("low"))
            price[i] = None if hi is None or lo is None else (hi + lo) / 2.0

        hi_win = highest(price, length)
        lo_win = lowest(price, length)

        fisher: list[Any] = [None] * n
        value_prev = 0.0
        fisher_prev = 0.0
        value_series: list[float | None] = [None] * n
        for i in range(n):
            p, h, l = price[i], hi_win[i], lo_win[i]
            if p is None or h is None or l is None:
                continue
            span = h - l
            norm = 0.5 if span == 0 else (p - l) / span
            value = 0.66 * (norm - 0.5) + 0.67 * value_prev
            value = max(-0.999, min(0.999, value))
            value_series[i] = value
            fish = 0.5 * math.log((1.0 + value) / (1.0 - value)) + 0.5 * fisher_prev
            fisher[i] = fish
            value_prev, fisher_prev = value, fish

        signal: list[Any] = [None] * n
        for i in range(offset, n):
            signal[i] = fisher[i - offset]
        return {"fisher": fisher, "signal": signal}


class StochRsiIndicator(BaseIndicator):
    """Stochastic RSI."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="stoch_rsi",
        name="Stochastic RSI",
        category=IndicatorCategory.MOMENTUM,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "Applies the stochastic percentile to RSI instead of price. "
            "Because RSI is already bounded, the result is extremely sensitive "
            "to the RSI window: it saturates at 0/100 constantly. Use it as a "
            "timing refinement on an existing bias, never as a standalone "
            "bias."
        ),
        parameters=(
            ParameterSpec("rsi_length", ParameterType.INTEGER, 14, 2, 100, 1, label="RSI length"),
            ParameterSpec("stoch_length", ParameterType.INTEGER, 14, 2, 100, 1, label="Stoch length"),
            ParameterSpec("k_smooth", ParameterType.INTEGER, 3, 1, 50, 1, label="%K smoothing"),
            ParameterSpec("d_smooth", ParameterType.INTEGER, 3, 1, 50, 1, label="%D smoothing"),
            ParameterSpec("source", ParameterType.CHOICE, "close", options=SOURCE_CHOICES,
                          label="Price source"),
        ),
        outputs=(
            OutputSpec("stoch_rsi", OutputRole.LINE, PaneHint.SEPARATE, label="Stoch RSI",
                       description="Raw Stochastic RSI before %K/%D smoothing."),
            OutputSpec("k", OutputRole.LINE, PaneHint.SEPARATE, label="%K"),
            OutputSpec("d", OutputRole.LINE, PaneHint.SEPARATE, label="%D"),
        ),
        formula_summary="stoch_rsi = stoch(RSI, stoch_length); %K = SMA(stoch_rsi, k_smooth); %D = SMA(%K, d_smooth)",
        version="1.1.0",
        tags=("momentum", "oscillator", "hybrid"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [
                {"left": "k", "operator": "crosses_above", "right": "d"},
                {"left": "k", "operator": "<", "right": 20},
            ],
        },
        "short": {
            "operator": "AND",
            "conditions": [
                {"left": "k", "operator": "crosses_below", "right": "d"},
                {"left": "k", "operator": ">", "right": 80},
            ],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        src = source_series(candles, str(params["source"]))
        rsi = _rsi_series(src, int(params["rsi_length"]))
        raw_k = _stoch(rsi, int(params["stoch_length"]))
        raw_k_smoothed = sma(raw_k, int(params["k_smooth"]))
        k = [None if v is None else max(0.0, min(100.0, v)) for v in raw_k_smoothed]
        raw_d = sma(k, int(params["d_smooth"]))
        d = [None if v is None else max(0.0, min(100.0, v)) for v in raw_d]
        return {"stoch_rsi": raw_k, "k": k, "d": d}


class WaveTrendIndicator(BaseIndicator):
    """WaveTrend oscillator (LazyBear formulation)."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="wavetrend",
        name="WaveTrend",
        category=IndicatorCategory.MOMENTUM,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "Normalised deviation of the typical price from its EMA, itself "
            "smoothed by a second EMA. Unbounded in principle but usually "
            "bounded by its own saturation; the classic ±60 levels are "
            "convention, not statistics."
        ),
        parameters=(
            ParameterSpec("channel_length", ParameterType.INTEGER, 10, 2, 100, 1,
                          label="Channel length"),
            ParameterSpec("average_length", ParameterType.INTEGER, 21, 2, 200, 1,
                          label="Average length"),
            ParameterSpec("signal_length", ParameterType.INTEGER, 4, 1, 50, 1,
                          label="Signal smoothing"),
        ),
        outputs=(
            OutputSpec("wt1", OutputRole.LINE, PaneHint.SEPARATE, label="WT1"),
            OutputSpec("wt2", OutputRole.LINE, PaneHint.SEPARATE, label="WT2"),
        ),
        formula_summary=(
            "ap = hlc3; esa = EMA(ap, n1); d = EMA(|ap-esa|, n1); "
            "ci = (ap-esa)/(0.015*d); wt1 = EMA(ci, n2); wt2 = SMA(wt1, signal)"
        ),
        version="1.0.0",
        tags=("momentum", "cycle", "oscillator"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [
                {"left": "wt1", "operator": "crosses_above", "right": "wt2"},
                {"left": "wt1", "operator": "<", "right": -60},
            ],
        },
        "short": {
            "operator": "AND",
            "conditions": [
                {"left": "wt1", "operator": "crosses_below", "right": "wt2"},
                {"left": "wt1", "operator": ">", "right": 60},
            ],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        n1 = int(params["channel_length"])
        n2 = int(params["average_length"])
        n = len(candles)
        ap: list[float | None] = [None] * n
        for i, c in enumerate(candles):
            hi, lo, cl = finite(c.get("high")), finite(c.get("low")), finite(c.get("close"))
            ap[i] = None if None in (hi, lo, cl) else (hi + lo + cl) / 3.0

        esa = ema(ap, n1)
        dev: list[float | None] = [None] * n
        for i in range(n):
            if ap[i] is not None and esa[i] is not None:
                dev[i] = abs(ap[i] - esa[i])
        d = ema(dev, n1)

        ci: list[float | None] = [None] * n
        for i in range(n):
            if ap[i] is None or esa[i] is None or d[i] is None:
                continue
            denom = 0.015 * d[i]
            ci[i] = 0.0 if denom == 0 else (ap[i] - esa[i]) / denom

        wt1 = ema(ci, n2)
        wt2 = sma(wt1, int(params["signal_length"]))
        return {"wt1": wt1, "wt2": wt2}


class CciIndicator(BaseIndicator):
    """Commodity Channel Index."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="cci",
        name="CCI",
        category=IndicatorCategory.MOMENTUM,
        output_type=OutputType.OSCILLATOR,
        description=(
            "Deviation of typical price from its moving average, scaled by mean "
            "absolute deviation. The 0.015 constant is chosen so ~70-80% of "
            "readings fall inside ±100; it is a scaling convention, not a "
            "probability statement."
        ),
        parameters=(
            ParameterSpec("length", ParameterType.INTEGER, 20, 2, 200, 1, label="Length"),
            ParameterSpec("source", ParameterType.CHOICE, "hlc3", options=SOURCE_CHOICES,
                          label="Price source"),
        ),
        outputs=(OutputSpec("cci", OutputRole.LINE, PaneHint.SEPARATE, label="CCI"),),
        formula_summary="CCI = (tp - SMA(tp,n)) / (0.015 * mean absolute deviation)",
        version="1.0.0",
        tags=("momentum", "mean_reversion", "oscillator"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [
                {"left": "cci", "operator": "crosses_above", "right": -100},
            ],
        },
        "short": {
            "operator": "AND",
            "conditions": [
                {"left": "cci", "operator": "crosses_below", "right": 100},
            ],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        length = int(params["length"])
        src = source_series(candles, str(params["source"]))
        mean = sma(src, length)
        out: list[Any] = [None] * len(src)
        for i in range(len(src)):
            m = mean[i]
            if m is None or src[i] is None:
                continue
            window = src[max(0, i - length + 1) : i + 1]
            if len(window) < length or any(v is None for v in window):
                continue
            mad = sum(abs(float(v) - m) for v in window) / length
            denom = 0.015 * mad
            out[i] = 0.0 if denom == 0 else (src[i] - m) / denom
        return {"cci": out}


class WilliamsRIndicator(BaseIndicator):
    """Williams %R."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="williams_r",
        name="Williams %R",
        category=IndicatorCategory.MOMENTUM,
        output_type=OutputType.OSCILLATOR,
        description=(
            "Where the close sits inside the last n bars' range, expressed as "
            "-100..0. Mathematically it is the stochastic %K reflected, so it "
            "carries no information the stochastic does not — a useful reminder "
            "when a comparison shows two 'different' indicators agreeing."
        ),
        parameters=(
            ParameterSpec("length", ParameterType.INTEGER, 14, 2, 200, 1, label="Length"),
        ),
        outputs=(OutputSpec("williams_r", OutputRole.LINE, PaneHint.SEPARATE, label="%R"),),
        formula_summary="%R = -100 * (highest_high - close) / (highest_high - lowest_low)",
        version="1.0.0",
        tags=("momentum", "oscillator"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [{"left": "williams_r", "operator": "crosses_above", "right": -80}],
        },
        "short": {
            "operator": "AND",
            "conditions": [{"left": "williams_r", "operator": "crosses_below", "right": -20}],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        length = int(params["length"])
        n = len(candles)
        hh = rolling_high([finite(c.get("high")) for c in candles], length)
        ll = lowest([finite(c.get("low")) for c in candles], length)
        out: list[Any] = [None] * n
        for i in range(n):
            h, l = hh[i], ll[i]
            cl = finite(candles[i].get("close"))
            if None in (h, l, cl):
                continue
            span = h - l
            out[i] = -50.0 if span == 0 else -100.0 * (h - cl) / span
        return {"williams_r": out}


class StcIndicator(BaseIndicator):
    """Schaff Trend Cycle."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="stc",
        name="STC",
        category=IndicatorCategory.MOMENTUM,
        output_type=OutputType.OSCILLATOR,
        description=(
            "Doubly-stochastic-smoothed MACD, bounded 0-100. It exists to "
            "shorten MACD's lag; the price of that is two extra stochastic "
            "stages, each of which is a nonlinear operation that can latch at "
            "0/100 in quiet markets."
        ),
        parameters=(
            ParameterSpec("stc_length", ParameterType.INTEGER, 10, 2, 100, 1,
                          label="Cycle length"),
            ParameterSpec("fast_length", ParameterType.INTEGER, 23, 2, 200, 1,
                          label="Fast EMA"),
            ParameterSpec("slow_length", ParameterType.INTEGER, 50, 3, 400, 1,
                          label="Slow EMA"),
            ParameterSpec("factor", ParameterType.NUMBER, 0.5, 0.05, 1.0, 0.05,
                          label="Smoothing factor"),
            ParameterSpec("source", ParameterType.CHOICE, "close", options=SOURCE_CHOICES,
                          label="Price source"),
        ),
        outputs=(OutputSpec("stc", OutputRole.LINE, PaneHint.SEPARATE, label="STC"),),
        formula_summary=(
            "macd = EMA(fast)-EMA(slow); k = stoch(macd, cycle); "
            "k' = EMA_alpha(k, factor); d = stoch(k', cycle); stc = EMA_alpha(d, factor)"
        ),
        version="1.0.0",
        reference="Doug Schaff, 'Schaff Trend Cycle' (TASC 2008)",
        tags=("momentum", "trend", "oscillator", "hybrid"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [
                {"left": "stc", "operator": "crosses_above", "right": 25},
                {"left": "stc", "operator": "turns_up"},
            ],
        },
        "short": {
            "operator": "AND",
            "conditions": [
                {"left": "stc", "operator": "crosses_below", "right": 75},
                {"left": "stc", "operator": "turns_down"},
            ],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        cycle = int(params["stc_length"])
        factor = float(params["factor"])
        factor = max(0.01, min(1.0, factor))
        src = source_series(candles, str(params["source"]))
        fast = ema(src, int(params["fast_length"]))
        slow = ema(src, int(params["slow_length"]))
        n = len(src)
        macd: list[float | None] = [None] * n
        for i in range(n):
            if fast[i] is not None and slow[i] is not None:
                macd[i] = fast[i] - slow[i]

        k1 = _stoch(macd, cycle)
        k1_smooth = ema_alpha(k1, factor)
        d1 = _stoch(k1_smooth, cycle)
        stc = ema_alpha(d1, factor)
        return {"stc": stc}
