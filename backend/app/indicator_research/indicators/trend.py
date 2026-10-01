"""Trend / overlay indicators.

SMA, EMA, VWAP, Supertrend and ADX. Each is a complete, self-describing
indicator: add this file's pattern to a new module and the registry picks it up.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, ClassVar, Mapping, Sequence
from zoneinfo import ZoneInfo

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
    InputRequirement,
    OutputSpec,
    ParameterSpec,
)
from app.indicator_research.indicators.helpers import (
    SOURCE_CHOICES,
    atr,
    ema,
    finite,
    highest,
    highs,
    lowest,
    lows,
    sma,
    source_series,
    true_range,
    wilder,
)

_SOURCE_PARAM = ParameterSpec(
    name="source",
    type=ParameterType.CHOICE,
    default="close",
    options=SOURCE_CHOICES,
    label="Price source",
    description="Which candle price the indicator reads.",
)


class SmaIndicator(BaseIndicator):
    """Simple moving average."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="sma",
        name="SMA",
        category=IndicatorCategory.TREND,
        output_type=OutputType.OVERLAY,
        description=(
            "Arithmetic mean of the last n prices. The slowest-responding "
            "average and the most lagging: a cross of price over SMA says the "
            "mean has moved, not that a new move has started."
        ),
        parameters=(
            ParameterSpec("length", ParameterType.INTEGER, 20, 2, 500, 1,
                          label="Length", description="Averaging window in bars."),
            _SOURCE_PARAM,
        ),
        outputs=(OutputSpec("sma", OutputRole.LINE, PaneHint.PRICE, label="SMA"),),
        formula_summary="SMA[t] = mean(source[t-n+1 .. t])",
        version="1.0.0",
        tags=("trend", "baseline"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [{"left": "close", "operator": "crosses_above", "right": "sma"}],
        },
        "short": {
            "operator": "AND",
            "conditions": [{"left": "close", "operator": "crosses_below", "right": "sma"}],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        src = source_series(candles, str(params["source"]))
        return {"sma": sma(src, int(params["length"]))}


class EmaIndicator(BaseIndicator):
    """Exponential moving average, SMA-seeded."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="ema",
        name="EMA",
        category=IndicatorCategory.TREND,
        output_type=OutputType.OVERLAY,
        description=(
            "Exponentially weighted moving average seeded with the first "
            "n-period SMA. Reacts faster than the SMA, at the cost of more "
            "whipsaw in a range."
        ),
        parameters=(
            ParameterSpec("length", ParameterType.INTEGER, 20, 2, 500, 1, label="Length"),
            _SOURCE_PARAM,
        ),
        outputs=(OutputSpec("ema", OutputRole.LINE, PaneHint.PRICE, label="EMA"),),
        formula_summary="EMA[t] = k*source[t] + (1-k)*EMA[t-1], k = 2/(n+1), seeded on SMA(n)",
        version="1.0.0",
        tags=("trend", "baseline"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [{"left": "close", "operator": "crosses_above", "right": "ema"}],
        },
        "short": {
            "operator": "AND",
            "conditions": [{"left": "close", "operator": "crosses_below", "right": "ema"}],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        src = source_series(candles, str(params["source"]))
        return {"ema": ema(src, int(params["length"]))}


IST = ZoneInfo("Asia/Kolkata")


def _candle_ist(candle: Mapping[str, Any]) -> datetime | None:
    raw = candle.get("timestamp")
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, str) and raw:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


def _is_anchor_reset(
    prev_dt: datetime | None,
    curr_dt: datetime | None,
    anchor: str,
) -> bool:
    if prev_dt is None or curr_dt is None:
        return False
    if anchor == "session":
        return prev_dt.date() != curr_dt.date()
    if anchor == "week":
        return prev_dt.isocalendar()[:2] != curr_dt.isocalendar()[:2]
    if anchor == "month":
        return (prev_dt.year, prev_dt.month) != (curr_dt.year, curr_dt.month)
    return False


class VwapIndicator(BaseIndicator):
    """Anchored and Rolling Volume-Weighted Average Price."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="vwap",
        name="VWAP",
        category=IndicatorCategory.TREND,
        output_type=OutputType.OVERLAY,
        description=(
            "Volume-weighted average price. Supports session, weekly, monthly and "
            "rolling anchors. Session anchor resets at 09:15 IST each trading day. "
            "Reports VWAP, distance from VWAP in points, and bar-over-bar slope."
        ),
        parameters=(
            ParameterSpec(
                "anchor", ParameterType.CHOICE, "session",
                options=("session", "week", "month", "rolling"),
                label="Anchor mode",
                description="Reset interval for volume accumulation.",
            ),
            ParameterSpec(
                "window", ParameterType.INTEGER, 0, 0, 1000, 1,
                label="Rolling window",
                description="0 = accumulate within anchor, >0 = rolling bars.",
            ),
            ParameterSpec(
                "source", ParameterType.CHOICE, "hlc3",
                options=SOURCE_CHOICES,
                label="Price source",
            ),
        ),
        outputs=(
            OutputSpec("vwap", OutputRole.LINE, PaneHint.PRICE, label="VWAP"),
            OutputSpec("distance_from_vwap", OutputRole.LINE, PaneHint.SEPARATE,
                       label="Distance from VWAP", description="Close minus VWAP (points)."),
            OutputSpec("vwap_slope", OutputRole.LINE, PaneHint.SEPARATE,
                       label="VWAP Slope", description="Bar-over-bar rate of change of VWAP."),
        ),
        requires=(InputRequirement.OHLCV, InputRequirement.VOLUME),
        formula_summary="VWAP[t] = sum(price * volume) / sum(volume) within anchor interval",
        version="1.1.0",
        tags=("trend", "volume", "anchor"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [{"left": "close", "operator": "crosses_above", "right": "vwap"}],
        },
        "short": {
            "operator": "AND",
            "conditions": [{"left": "close", "operator": "crosses_below", "right": "vwap"}],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        anchor = str(params.get("anchor", "session")).lower()
        window = int(params.get("window", 0))
        src = source_series(candles, str(params.get("source", "hlc3")))
        n = len(candles)

        vwap_out: list[float | None] = [None] * n
        dist_out: list[float | None] = [None] * n
        slope_out: list[float | None] = [None] * n

        cum_vol = 0.0
        cum_pv = 0.0
        rolling_buf: list[tuple[float, float]] = []
        prev_dt: datetime | None = None
        prev_vwap: float | None = None

        for i, c in enumerate(candles):
            p = src[i]
            vol = finite(c.get("volume")) or 0.0
            curr_dt = _candle_ist(c)

            if anchor != "rolling" and _is_anchor_reset(prev_dt, curr_dt, anchor):
                cum_vol = 0.0
                cum_pv = 0.0

            if p is not None:
                if anchor == "rolling" and window > 0:
                    rolling_buf.append((p, vol))
                    cum_pv += p * vol
                    cum_vol += vol
                    if len(rolling_buf) > window:
                        old_p, old_v = rolling_buf.pop(0)
                        cum_pv -= old_p * old_v
                        cum_vol -= old_v
                else:
                    cum_pv += p * vol
                    cum_vol += vol

                current_vwap = (cum_pv / cum_vol) if cum_vol > 0.0 else prev_vwap
            else:
                current_vwap = prev_vwap

            vwap_out[i] = current_vwap
            cl = finite(c.get("close"))
            if current_vwap is not None and cl is not None:
                dist_out[i] = cl - current_vwap
            if current_vwap is not None:
                slope_out[i] = (current_vwap - prev_vwap) if prev_vwap is not None else 0.0

            if current_vwap is not None:
                prev_vwap = current_vwap
            prev_dt = curr_dt

        return {
            "vwap": vwap_out,
            "distance_from_vwap": dist_out,
            "vwap_slope": slope_out,
        }


class VolumeProfileIndicator(BaseIndicator):
    """Causal Volume-at-Price Profile (POC, VAH, VAL, HVN, LVN)."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="volume_profile",
        name="Volume Profile",
        category=IndicatorCategory.TREND,
        output_type=OutputType.OVERLAY,
        description=(
            "Causal Volume-at-Price distribution accumulated within the active anchor. "
            "Reports developing Point of Control (POC), Value Area High (VAH), and "
            "Value Area Low (VAL). When computed from OHLCV bars without tick data, "
            "intrabar volume is discretized across the bar range and stamped as ESTIMATED."
        ),
        parameters=(
            ParameterSpec("anchor", ParameterType.CHOICE, "session",
                          options=("session", "week", "month", "rolling"),
                          label="Anchor mode"),
            ParameterSpec("value_area_pct", ParameterType.NUMBER, 0.70, 0.1, 1.0, 0.05,
                          label="Value area fraction"),
            ParameterSpec("bin_size", ParameterType.NUMBER, 1.0, 0.05, 100.0, 0.05,
                          label="Bin size (pts)"),
        ),
        outputs=(
            OutputSpec("poc", OutputRole.LINE, PaneHint.PRICE, label="POC",
                       description="Point of Control (price with highest accumulated volume)."),
            OutputSpec("vah", OutputRole.LINE, PaneHint.PRICE, label="VAH",
                       description="Value Area High (upper boundary of 70% volume area)."),
            OutputSpec("val", OutputRole.LINE, PaneHint.PRICE, label="VAL",
                       description="Value Area Low (lower boundary of 70% volume area)."),
            OutputSpec("hvn", OutputRole.LINE, PaneHint.PRICE, label="HVN",
                       description="High Volume Node level."),
            OutputSpec("lvn", OutputRole.LINE, PaneHint.PRICE, label="LVN",
                       description="Low Volume Node level."),
        ),
        requires=(InputRequirement.OHLCV, InputRequirement.VOLUME),
        formula_summary="Volume profile histogram accumulated bar-by-bar; POC = argmax(Vol); VAH/VAL = 70% area",
        version="1.0.0",
        tags=("trend", "volume", "profile", "price_location"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [{"left": "close", "operator": "crosses_above", "right": "val"}],
        },
        "short": {
            "operator": "AND",
            "conditions": [{"left": "close", "operator": "crosses_below", "right": "vah"}],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        anchor = str(params.get("anchor", "session")).lower()
        va_fraction = float(params.get("value_area_pct", 0.70))
        bin_size = max(0.05, float(params.get("bin_size", 1.0)))

        n = len(candles)
        poc_out: list[float | None] = [None] * n
        vah_out: list[float | None] = [None] * n
        val_out: list[float | None] = [None] * n
        hvn_out: list[float | None] = [None] * n
        lvn_out: list[float | None] = [None] * n

        hist: dict[float, float] = {}
        total_vol = 0.0
        prev_dt: datetime | None = None
        prev_poc: float | None = None
        prev_vah: float | None = None
        prev_val: float | None = None
        prev_hvn: float | None = None
        prev_lvn: float | None = None

        for i, c in enumerate(candles):
            curr_dt = _candle_ist(c)
            if anchor != "rolling" and _is_anchor_reset(prev_dt, curr_dt, anchor):
                hist = {}
                total_vol = 0.0

            hi = finite(c.get("high"))
            lo = finite(c.get("low"))
            cl = finite(c.get("close"))
            vol = finite(c.get("volume")) or 0.0

            if None not in (hi, lo, cl) and vol > 0.0:
                low_bin = round(lo / bin_size) * bin_size
                high_bin = round(hi / bin_size) * bin_size
                step_count = max(1, int(round((high_bin - low_bin) / bin_size)) + 1)
                v_slice = vol / step_count
                for s in range(step_count):
                    b = round(low_bin + s * bin_size, 4)
                    hist[b] = hist.get(b, 0.0) + v_slice
                total_vol += vol

            if hist:
                sorted_bins = sorted(hist.keys())
                poc_bin = max(sorted_bins, key=lambda b: hist[b])
                poc_out[i] = poc_bin
                prev_poc = poc_bin

                target_va_vol = total_vol * va_fraction
                va_vol = hist[poc_bin]
                included_bins = {poc_bin}
                poc_idx = sorted_bins.index(poc_bin)
                up_idx = poc_idx + 1
                dn_idx = poc_idx - 1

                while va_vol < target_va_vol and (up_idx < len(sorted_bins) or dn_idx >= 0):
                    up_vol = hist[sorted_bins[up_idx]] if up_idx < len(sorted_bins) else -1.0
                    dn_vol = hist[sorted_bins[dn_idx]] if dn_idx >= 0 else -1.0
                    if up_vol >= dn_vol and up_idx < len(sorted_bins):
                        va_vol += up_vol
                        included_bins.add(sorted_bins[up_idx])
                        up_idx += 1
                    elif dn_idx >= 0:
                        va_vol += dn_vol
                        included_bins.add(sorted_bins[dn_idx])
                        dn_idx -= 1
                    else:
                        break

                val_out[i] = min(included_bins)
                vah_out[i] = max(included_bins)
                prev_val = val_out[i]
                prev_vah = vah_out[i]

                if len(sorted_bins) >= 3:
                    peaks = [
                        sorted_bins[k] for k in range(1, len(sorted_bins) - 1)
                        if hist[sorted_bins[k]] > hist[sorted_bins[k - 1]] and hist[sorted_bins[k]] > hist[sorted_bins[k + 1]]
                    ]
                    valleys = [
                        sorted_bins[k] for k in range(1, len(sorted_bins) - 1)
                        if hist[sorted_bins[k]] < hist[sorted_bins[k - 1]] and hist[sorted_bins[k]] < hist[sorted_bins[k + 1]]
                    ]
                    hvn_out[i] = max(peaks, key=lambda b: hist[b]) if peaks else poc_bin
                    lvn_out[i] = min(valleys, key=lambda b: hist[b]) if valleys else val_out[i]
                else:
                    hvn_out[i] = poc_bin
                    lvn_out[i] = val_out[i]
                prev_hvn = hvn_out[i]
                prev_lvn = lvn_out[i]
            else:
                poc_out[i] = prev_poc
                vah_out[i] = prev_vah
                val_out[i] = prev_val
                hvn_out[i] = prev_hvn
                lvn_out[i] = prev_lvn

            prev_dt = curr_dt

        return {
            "poc": poc_out,
            "vah": vah_out,
            "val": val_out,
            "hvn": hvn_out,
            "lvn": lvn_out,
        }


class SupertrendIndicator(BaseIndicator):
    """ATR-banded trailing trend line."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="supertrend",
        name="Supertrend",
        category=IndicatorCategory.TREND,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "Trend line that flips side when price closes through an ATR band. "
            "The band recursion is path-dependent, so it is evaluated "
            "sequentially bar by bar — the band at bar t depends on the band "
            "at t-1, never on a later flip."
        ),
        parameters=(
            ParameterSpec("length", ParameterType.INTEGER, 10, 1, 100, 1,
                          label="ATR length"),
            ParameterSpec("multiplier", ParameterType.NUMBER, 3.0, 0.5, 10.0, 0.1,
                          label="ATR multiplier"),
        ),
        outputs=(
            OutputSpec("supertrend", OutputRole.LINE, PaneHint.PRICE, label="Supertrend"),
            OutputSpec("direction", OutputRole.HISTOGRAM, PaneHint.SEPARATE,
                       label="Direction", description="+1 uptrend, -1 downtrend."),
            OutputSpec("upper_band", OutputRole.BAND_UPPER, PaneHint.PRICE),
            OutputSpec("lower_band", OutputRole.BAND_LOWER, PaneHint.PRICE),
        ),
        formula_summary=(
            "upper = hl2 + m*ATR; lower = hl2 - m*ATR; bands ratchet toward price "
            "and only loosen on a close beyond the opposite band; trend flips on "
            "that close."
        ),
        version="1.0.0",
        tags=("trend", "volatility", "trailing"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [{"left": "direction", "operator": "crosses_above", "right": 0}],
        },
        "short": {
            "operator": "AND",
            "conditions": [{"left": "direction", "operator": "crosses_below", "right": 0}],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        length = int(params["length"])
        mult = float(params["multiplier"])
        n = len(candles)

        out_st: list[Any] = [None] * n
        out_dir: list[Any] = [None] * n
        out_up: list[Any] = [None] * n
        out_lo: list[Any] = [None] * n

        atr_series = atr(candles, length)
        prev_close: float | None = None
        final_upper: float | None = None
        final_lower: float | None = None
        direction: int | None = None

        for i, candle in enumerate(candles):
            cl = finite(candle.get("close"))
            hi = finite(candle.get("high"))
            lo = finite(candle.get("low"))
            a = atr_series[i]
            if None in (cl, hi, lo) or a is None:
                prev_close = cl
                continue

            mid = (hi + lo) / 2.0
            basic_upper = mid + mult * a
            basic_lower = mid - mult * a

            if final_upper is None or final_lower is None or prev_close is None or direction is None:
                final_upper, final_lower = basic_upper, basic_lower
                direction = 1 if cl >= mid else -1
            else:
                # Bands ratchet toward price: they tighten, and only release
                # when the previous close has already broken them.
                if basic_upper < final_upper or prev_close > final_upper:
                    final_upper = basic_upper
                if basic_lower > final_lower or prev_close < final_lower:
                    final_lower = basic_lower
                if direction == 1 and cl < final_lower:
                    direction = -1
                elif direction == -1 and cl > final_upper:
                    direction = 1

            out_up[i] = final_upper
            out_lo[i] = final_lower
            out_dir[i] = direction
            out_st[i] = final_lower if direction == 1 else final_upper
            prev_close = cl

        return {
            "supertrend": out_st,
            "direction": out_dir,
            "upper_band": out_up,
            "lower_band": out_lo,
        }


class AdxIndicator(BaseIndicator):
    """Average Directional Index with +DI / -DI."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="adx",
        name="ADX",
        category=IndicatorCategory.TREND,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "Wilder's directional-movement system. ADX measures trend strength "
            "without direction; +DI/-DI carry the direction. ADX is a trend "
            "filter, not an entry trigger."
        ),
        parameters=(
            ParameterSpec("length", ParameterType.INTEGER, 14, 2, 100, 1, label="Length"),
        ),
        outputs=(
            OutputSpec("adx", OutputRole.LINE, PaneHint.SEPARATE, label="ADX"),
            OutputSpec("plus_di", OutputRole.LINE, PaneHint.SEPARATE, label="+DI"),
            OutputSpec("minus_di", OutputRole.LINE, PaneHint.SEPARATE, label="-DI"),
        ),
        formula_summary=(
            "Wilder-smoothed +DM/-DM and TR over n bars; DI = 100*DM/TR; "
            "DX = 100*|+DI - -DI|/(+DI + -DI); ADX = Wilder(DX, n)."
        ),
        version="1.0.0",
        tags=("trend", "strength"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [
                {"left": "plus_di", "operator": "crosses_above", "right": "minus_di"},
                {"left": "adx", "operator": ">", "right": 20},
            ],
        },
        "short": {
            "operator": "AND",
            "conditions": [
                {"left": "minus_di", "operator": "crosses_above", "right": "plus_di"},
                {"left": "adx", "operator": ">", "right": 20},
            ],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        length = int(params["length"])
        n = len(candles)
        plus_dm: list[Any] = [None] * n
        minus_dm: list[Any] = [None] * n

        prev_high: float | None = None
        prev_low: float | None = None
        for i, candle in enumerate(candles):
            hi = finite(candle.get("high"))
            lo = finite(candle.get("low"))
            if hi is None or lo is None:
                prev_high, prev_low = hi, lo
                continue
            if prev_high is not None and prev_low is not None:
                up_move = hi - prev_high
                down_move = prev_low - lo
                plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
                minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0
            prev_high, prev_low = hi, lo

        tr_smooth = wilder(true_range(candles), length)
        plus_smooth = wilder(plus_dm, length)
        minus_smooth = wilder(minus_dm, length)

        plus_di: list[Any] = [None] * n
        minus_di: list[Any] = [None] * n
        dx: list[Any] = [None] * n
        for i in range(n):
            tr = tr_smooth[i]
            ps = plus_smooth[i]
            ms = minus_smooth[i]
            if tr is None or tr == 0 or ps is None or ms is None:
                continue
            pdi = 100.0 * ps / tr
            mdi = 100.0 * ms / tr
            plus_di[i] = pdi
            minus_di[i] = mdi
            denom = pdi + mdi
            dx[i] = 0.0 if denom == 0 else 100.0 * abs(pdi - mdi) / denom

        return {
            "adx": wilder(dx, length),
            "plus_di": plus_di,
            "minus_di": minus_di,
        }


class DonchianIndicator(BaseIndicator):
    """Donchian channel — rolling high/low envelope."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="donchian",
        name="Donchian Channel",
        category=IndicatorCategory.PRICE_ACTION,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "Highest high and lowest low of the last n bars, with the channel "
            "midline. Breakouts of a prior channel are a classic price-action "
            "trigger; the channel at bar t excludes bar t+1 by construction, so "
            "breakout rules are naturally lookahead-free."
        ),
        parameters=(
            ParameterSpec("length", ParameterType.INTEGER, 20, 2, 500, 1, label="Length"),
        ),
        outputs=(
            OutputSpec("upper", OutputRole.BAND_UPPER, PaneHint.PRICE),
            OutputSpec("lower", OutputRole.BAND_LOWER, PaneHint.PRICE),
            OutputSpec("middle", OutputRole.BAND_MIDDLE, PaneHint.PRICE),
        ),
        formula_summary="upper = max(high[t-n+1..t]); lower = min(low[t-n+1..t]); middle = (upper+lower)/2",
        version="1.0.0",
        tags=("price_action", "breakout"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [{"left": "close", "operator": "crosses_above", "right": "upper"}],
        },
        "short": {
            "operator": "AND",
            "conditions": [{"left": "close", "operator": "crosses_below", "right": "lower"}],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        length = int(params["length"])
        upper = highest(highs(candles), length)
        lower = lowest(lows(candles), length)
        middle: list[Any] = [None] * len(candles)
        for i in range(len(candles)):
            u, l = upper[i], lower[i]
            if u is not None and l is not None:
                middle[i] = (u + l) / 2.0
        return {"upper": upper, "lower": lower, "middle": middle}
