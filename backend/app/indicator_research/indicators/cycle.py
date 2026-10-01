"""Cycle indicators.

Ehlers' Even Better Sinewave (EBSW), Ehlers' MESA Adaptive Moving Average
(MAMA/FAMA) and a rolling-autocorrelation dominant-cycle estimate.

Cycle tools answer a different question from oscillators: not "how stretched is
price" but "does this market have a tradable rhythm at all, and how long is it".
A cycle length that drifts bar to bar is the honest answer "there is no stable
cycle here", and the rule builder should be able to require stability before
trading it — ``cycle_strength`` exists for exactly that.
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
    finite,
    source_series,
)


def _ehlers_alpha(period: float) -> float | None:
    """Ehlers' two-pole filter coefficient for a given cycle period."""
    if period <= 0:
        return None
    w = 0.707 * 2.0 * math.pi / period
    c = math.cos(w)
    if c == 0:
        return None
    return (c + math.sin(w) - 1.0) / c


class EbswIndicator(BaseIndicator):
    """Ehlers Even Better Sinewave."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="ebsw",
        name="Ehlers EBSW",
        category=IndicatorCategory.CYCLE,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "A two-stage filter chain: a high-pass filter removes the trend, a "
            "super-smoother removes high-frequency noise, and the survivor is "
            "the cyclical component. Ehlers' published output is the bandpass "
            "wave; this implementation additionally rescales it to -1..+1 over "
            "the super-smoother window so it can be thresholded with stable, "
            "instrument-independent levels. The rescaling divides by a rolling "
            "extremum, so a flat market (zero range) yields no reading rather "
            "than a division artifact."
        ),
        parameters=(
            ParameterSpec("hp_period", ParameterType.INTEGER, 40, 4, 200, 1,
                          label="High-pass period"),
            ParameterSpec("ssf_period", ParameterType.INTEGER, 10, 3, 100, 1,
                          label="Super-smoother period"),
            ParameterSpec("source", ParameterType.CHOICE, "close", options=SOURCE_CHOICES,
                          label="Price source"),
        ),
        outputs=(
            OutputSpec("ebsw", OutputRole.LINE, PaneHint.SEPARATE, label="EBSW",
                       description="Normalised wave, -1..+1."),
            OutputSpec("wave", OutputRole.LINE, PaneHint.SEPARATE, label="Wave",
                       description="Raw bandpass output before normalisation."),
            OutputSpec("trigger", OutputRole.LINE, PaneHint.SEPARATE, label="Trigger",
                       description="1-bar lagged EBSW trigger for crossover signals."),
        ),
        formula_summary=(
            "alpha = (cos(w)+sin(w)-1)/cos(w), w = 0.707*2pi/period; "
            "hp = (1-a/2)^2*(p - 2p[-1] + p[-2]) + 2(1-a)hp[-1] - (1-a)^2 hp[-2]; "
            "wave = same filter applied to hp; ebsw = 2*(wave-min)/(max-min) - 1; "
            "trigger = ebsw[-1]"
        ),
        version="1.1.0",
        reference="Ehlers, 'Cycle Analytics for Traders', ch. 4",
        tags=("cycle", "filter", "oscillator"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [
                {"left": "ebsw", "operator": "crosses_above", "right": -0.5},
            ],
        },
        "short": {
            "operator": "AND",
            "conditions": [
                {"left": "ebsw", "operator": "crosses_below", "right": 0.5},
            ],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        hp_period = float(params["hp_period"])
        ssf_period = float(params["ssf_period"])
        src = source_series(candles, str(params["source"]))
        n = len(src)

        wave = _two_pole_chain(src, hp_period, ssf_period)
        ebsw: list[Any] = [None] * n
        window = max(2, int(round(ssf_period)))
        for i in range(n):
            if wave[i] is None:
                continue
            start = max(0, i - window + 1)
            segment = [wave[j] for j in range(start, i + 1)]
            if len(segment) < window or any(v is None for v in segment):
                continue
            values = [float(v) for v in segment]
            lo, hi = min(values), max(values)
            span = hi - lo
            if span == 0:
                continue
            ebsw[i] = 2.0 * (float(wave[i]) - lo) / span - 1.0

        trigger: list[Any] = [None] * n
        for i in range(1, n):
            trigger[i] = ebsw[i - 1]
        return {"ebsw": ebsw, "wave": wave, "trigger": trigger}


def _two_pole_chain(
    src: Sequence[float | None], hp_period: float, ssf_period: float
) -> list[float | None]:
    """High-pass filter followed by Ehlers' super-smoother.

    Sequential and causal: each bar reads only its own price and the previous
    two filter states.
    """
    n = len(src)
    out: list[float | None] = [None] * n
    a1 = _ehlers_alpha(hp_period)
    a2 = _ehlers_alpha(ssf_period)
    if a1 is None or a2 is None:
        return out

    # IIR filters need two initial states. Zero state is the standard choice:
    # the filter is stable and its transient decays within roughly one
    # hp_period, well inside the warm-up window the caller discards. Starting
    # from zero is deterministic and independent of future bars.
    hp: list[float | None] = [None] * n
    prev_hp1 = 0.0
    prev_hp2 = 0.0
    for i in range(n):
        p0, p1, p2 = src[i], (src[i - 1] if i >= 1 else None), (src[i - 2] if i >= 2 else None)
        if p0 is None or p1 is None or p2 is None:
            continue
        hp[i] = (
            (1.0 - a1 / 2.0) ** 2 * (p0 - 2.0 * p1 + p2)
            + 2.0 * (1.0 - a1) * prev_hp1
            - (1.0 - a1) ** 2 * prev_hp2
        )
        prev_hp2, prev_hp1 = prev_hp1, hp[i]

    prev_w1 = 0.0
    prev_w2 = 0.0
    for i in range(n):
        w0, w1, w2 = hp[i], (hp[i - 1] if i >= 1 else None), (hp[i - 2] if i >= 2 else None)
        if w0 is None or w1 is None or w2 is None:
            continue
        out[i] = (
            (1.0 - a2 / 2.0) ** 2 * (w0 - 2.0 * w1 + w2)
            + 2.0 * (1.0 - a2) * prev_w1
            - (1.0 - a2) ** 2 * prev_w2
        )
        prev_w2, prev_w1 = prev_w1, out[i]
    return out


class MamaFamaIndicator(BaseIndicator):
    """Ehlers MESA Adaptive Moving Average with its following average."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="mama_fama",
        name="Ehlers MAMA/FAMA",
        category=IndicatorCategory.CYCLE,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "An adaptive moving average whose smoothing factor is driven by a "
            "Hilbert-transform phase discriminator, plus a slower follower. It "
            "accelerates when the dominant cycle shortens and slows when it "
            "lengthens. The discriminator is path-dependent and evaluated bar "
            "by bar; the smoothing factor is clamped to [slow_limit, "
            "fast_limit] so a degenerate phase reading cannot make the average "
            "jump to the current price."
        ),
        parameters=(
            ParameterSpec("fast_limit", ParameterType.NUMBER, 0.5, 0.05, 1.0, 0.01,
                          label="Fast limit"),
            ParameterSpec("slow_limit", ParameterType.NUMBER, 0.05, 0.01, 0.5, 0.01,
                          label="Slow limit"),
            ParameterSpec("source", ParameterType.CHOICE, "hl2", options=SOURCE_CHOICES,
                          label="Price source"),
        ),
        outputs=(
            OutputSpec("mama", OutputRole.LINE, PaneHint.PRICE, label="MAMA"),
            OutputSpec("fama", OutputRole.LINE, PaneHint.PRICE, label="FAMA"),
            OutputSpec("alpha", OutputRole.LINE, PaneHint.SEPARATE, label="Adaptive alpha",
                       description="Smoothing factor actually used, clamped to the limits."),
        ),
        formula_summary=(
            "smooth = (4p + 3p[-1] + 2p[-2] + p[-3])/10; Hilbert discriminator -> phase; "
            "delta = max(1, phase[-1]-phase); alpha = clamp(fast/delta, slow, fast); "
            "MAMA = alpha*p + (1-alpha)*MAMA[-1]; FAMA = 0.5*alpha*MAMA + (1-0.5*alpha)*FAMA[-1]"
        ),
        version="1.0.0",
        reference="Ehlers, 'MESA Adaptive Moving Averages' (TASC 2001)",
        tags=("cycle", "trend", "adaptive"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [{"left": "mama", "operator": "crosses_above", "right": "fama"}],
        },
        "short": {
            "operator": "AND",
            "conditions": [{"left": "mama", "operator": "crosses_below", "right": "fama"}],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        fast_limit = float(params["fast_limit"])
        slow_limit = float(params["slow_limit"])
        if slow_limit > fast_limit:
            fast_limit, slow_limit = slow_limit, fast_limit
        src = source_series(candles, str(params["source"]))
        n = len(src)

        mama: list[Any] = [None] * n
        fama: list[Any] = [None] * n
        alpha_out: list[Any] = [None] * n

        smooth: list[float | None] = [None] * n
        for i in range(3, n):
            w = [src[i - k] for k in range(4)]
            if any(v is None for v in w):
                continue
            smooth[i] = (4.0 * w[0] + 3.0 * w[1] + 2.0 * w[2] + w[3]) / 10.0

        detrender = [0.0] * n
        q1 = [0.0] * n
        i1 = [0.0] * n
        j_i = [0.0] * n
        j_q = [0.0] * n
        i2 = [0.0] * n
        q2 = [0.0] * n
        re = [0.0] * n
        im = [0.0] * n
        period = 6.0
        period_prev = 6.0
        phase = 0.0
        phase_prev = 0.0
        mama_prev: float | None = None
        fama_prev: float | None = None

        for i in range(6, n):
            base = smooth[i]
            if base is None:
                continue
            refs = [smooth[i - k] for k in (2, 4, 6)]
            if any(v is None for v in refs):
                continue

            # The 7-bar Hilbert FIR kernels are scaled by the adaptive factor
            # so their response tracks the estimated dominant cycle.
            adj = 0.075 * period_prev + 0.54
            detrender[i] = (
                0.0962 * base + 0.5769 * refs[0] - 0.5769 * refs[1] - 0.0962 * refs[2]
            ) * adj
            d_refs = [detrender[i - k] for k in (2, 4, 6)]
            q1[i] = (
                0.0962 * detrender[i]
                + 0.5769 * d_refs[0]
                - 0.5769 * d_refs[1]
                - 0.0962 * d_refs[2]
            ) * adj
            i1[i] = detrender[i - 3]
            i_refs = [i1[i - k] for k in (2, 4, 6)]
            j_i[i] = (
                0.0962 * i1[i] + 0.5769 * i_refs[0] - 0.5769 * i_refs[1] - 0.0962 * i_refs[2]
            ) * adj
            q_refs = [q1[i - k] for k in (2, 4, 6)]
            j_q[i] = (
                0.0962 * q1[i] + 0.5769 * q_refs[0] - 0.5769 * q_refs[1] - 0.0962 * q_refs[2]
            ) * adj

            i2[i] = 0.2 * (i1[i] - j_q[i]) + 0.8 * i2[i - 1]
            q2[i] = 0.2 * (q1[i] + j_i[i]) + 0.8 * q2[i - 1]
            re[i] = 0.2 * (i2[i] * i2[i - 1] + q2[i] * q2[i - 1]) + 0.8 * re[i - 1]
            im[i] = 0.2 * (i2[i] * q2[i - 1] - q2[i] * i2[i - 1]) + 0.8 * im[i - 1]

            if im[i] != 0.0 and re[i] != 0.0:
                angle = math.degrees(math.atan(im[i] / re[i]))
                if angle != 0.0:
                    candidate = 360.0 / angle
                    if candidate > 0.0 and math.isfinite(candidate):
                        period = candidate
            # Ratchet the estimate: a genuine cycle cannot double or halve in
            # one bar, and letting it do so makes alpha oscillate.
            period = min(1.5 * period_prev, max(0.67 * period_prev, period))
            period = min(50.0, max(6.0, period))
            period = 0.2 * period + 0.8 * period_prev
            period_prev = period

            if i1[i] != 0.0:
                phase = math.degrees(math.atan(q1[i] / i1[i]))
            delta_phase = phase_prev - phase
            if not math.isfinite(delta_phase) or delta_phase < 1.0:
                delta_phase = 1.0
            alpha = fast_limit / delta_phase
            alpha = min(fast_limit, max(slow_limit, alpha))
            phase_prev = phase

            price = finite(src[i])
            if price is None:
                continue
            if mama_prev is None or fama_prev is None:
                mama_prev = fama_prev = price
            else:
                mama_prev = alpha * price + (1.0 - alpha) * mama_prev
                fama_prev = 0.5 * alpha * mama_prev + (1.0 - 0.5 * alpha) * fama_prev
            mama[i] = mama_prev
            fama[i] = fama_prev
            alpha_out[i] = alpha

        return {"mama": mama, "fama": fama, "alpha": alpha_out}


class DominantCycleIndicator(BaseIndicator):
    """Dominant cycle length from rolling autocorrelation."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="dominant_cycle",
        name="Dominant Cycle",
        category=IndicatorCategory.CYCLE,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "Estimates the market's dominant cycle length by finding the lag "
            "whose autocorrelation of detrended price is highest inside a "
            "rolling window. Deliberately NOT Ehlers' Hilbert discriminator: "
            "autocorrelation is directly verifiable, produces a strength "
            "reading, and does not require phase continuity. A cycle_length "
            "that wanders bar to bar means there is no stable rhythm — read "
            "cycle_strength before trusting the length."
        ),
        parameters=(
            ParameterSpec("window", ParameterType.INTEGER, 64, 20, 400, 1,
                          label="Autocorrelation window"),
            ParameterSpec("min_period", ParameterType.INTEGER, 6, 2, 100, 1,
                          label="Min cycle"),
            ParameterSpec("max_period", ParameterType.INTEGER, 32, 3, 200, 1,
                          label="Max cycle"),
            ParameterSpec("source", ParameterType.CHOICE, "close", options=SOURCE_CHOICES,
                          label="Price source"),
        ),
        outputs=(
            OutputSpec("cycle_length", OutputRole.LINE, PaneHint.SEPARATE,
                       label="Cycle length", description="Bars of the best lag."),
            OutputSpec("cycle_strength", OutputRole.LINE, PaneHint.SEPARATE,
                       label="Cycle strength",
                       description="Peak autocorrelation (0-1) at that lag."),
        ),
        formula_summary=(
            "x = source - mean(source, window); for lag in [min_period, max_period]: "
            "ac(lag) = sum(x[t]*x[t-lag]) / sum(x[t]^2); cycle_length = argmax ac, "
            "cycle_strength = max ac"
        ),
        version="1.0.0",
        tags=("cycle", "regime", "diagnostic"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [
                {"left": "cycle_strength", "operator": ">", "right": 0.3},
                {"left": "close", "operator": "turns_up"},
            ],
        },
        "short": {
            "operator": "AND",
            "conditions": [
                {"left": "cycle_strength", "operator": ">", "right": 0.3},
                {"left": "close", "operator": "turns_down"},
            ],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        window = int(params["window"])
        min_period = int(params["min_period"])
        # A lag must stay well inside the window or the autocorrelation is
        # computed from a handful of overlapping points.
        max_period = min(int(params["max_period"]), max(min_period, window // 2))
        src = source_series(candles, str(params["source"]))
        n = len(src)

        cycle_length: list[Any] = [None] * n
        cycle_strength: list[Any] = [None] * n
        if max_period < min_period:
            return {"cycle_length": cycle_length, "cycle_strength": cycle_strength}

        module = _numpy_or_none()
        for i in range(window - 1, n):
            segment = src[i - window + 1 : i + 1]
            if len(segment) < window or any(v is None for v in segment):
                continue
            values = [float(v) for v in segment]
            mean = sum(values) / window
            centered = [v - mean for v in values]
            denom = sum(v * v for v in centered)
            if denom <= 0.0:
                continue
            lag, strength = _best_lag(centered, denom, min_period, max_period, module)
            if lag is None:
                continue
            cycle_length[i] = float(lag)
            cycle_strength[i] = strength
        return {"cycle_length": cycle_length, "cycle_strength": cycle_strength}


def _numpy_or_none() -> Any:
    """numpy if it is importable, else None.

    Only used to accelerate the autocorrelation scan; the pure-Python path
    computes the same quantity. Indicators must never hard-require numpy, and
    a caller should get a result (slower) rather than an ImportError.
    """
    try:  # pragma: no cover - environment dependent
        import numpy as np

        return np
    except Exception:  # pragma: no cover - environment dependent
        return None


def _best_lag(
    centered: list[float],
    denom: float,
    min_period: int,
    max_period: int,
    module: Any,
) -> tuple[int | None, float]:
    """Lag with the highest normalised autocorrelation."""
    best_lag: int | None = None
    best = -2.0
    if module is not None:  # pragma: no cover - environment dependent
        try:
            arr = module.asarray(centered, dtype=float)
            for lag in range(min_period, max_period + 1):
                ac = float(arr[lag:] @ arr[:-lag]) / denom
                if ac > best:
                    best, best_lag = ac, lag
            return best_lag, best
        except Exception:  # pragma: no cover - environment dependent
            pass
    for lag in range(min_period, max_period + 1):
        acc = 0.0
        for j in range(lag, len(centered)):
            acc += centered[j] * centered[j - lag]
        ac = acc / denom
        if ac > best:
            best, best_lag = ac, lag
    return best_lag, best
