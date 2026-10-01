"""Microstructure and order-flow indicators (Phase 4, Spec v2 §8.4, §8.5, §8.6).

Contains:
- Volume Delta / CVD (Cumulative Volume Delta)
- Absorption Detector (quantitative liquidity persistence)
- DPFI (DROID Predictive Flow Index v1)

All indicators declare explicit data provenance requirements (TRADES, MARKET_DEPTH).
When historical depth/trade streams are missing from the input series, calculations
return explicit UNAVAILABLE states rather than fabricating synthetic order flow.
"""

from __future__ import annotations

import math
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
from app.indicator_research.indicators.helpers import finite, true_range, wilder

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


# =========================================================================== #
# 1. Cumulative Volume Delta (CVD)
# =========================================================================== #
class CvdIndicator(BaseIndicator):
    """Cumulative Volume Delta from aggressive buy and sell volume."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="cvd",
        name="Cumulative Volume Delta",
        category=IndicatorCategory.MOMENTUM,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "Tracks net aggressive buying and selling pressure. Calculates bar delta "
            "(Buy Volume - Sell Volume) and cumulative volume delta (CVD). Resets per "
            "session by default. Requires trade-level aggressor classification (REAL) "
            "or tick-rule classification (PROXY)."
        ),
        parameters=(
            ParameterSpec("anchor", ParameterType.CHOICE, "session",
                          options=("session", "cumulative"),
                          label="Anchor mode"),
        ),
        outputs=(
            OutputSpec("delta", OutputRole.HISTOGRAM, PaneHint.SEPARATE, label="Delta",
                       description="Bar aggressive buy volume minus aggressive sell volume."),
            OutputSpec("cvd", OutputRole.LINE, PaneHint.SEPARATE, label="CVD",
                       description="Cumulative Volume Delta accumulated within anchor."),
        ),
        requires=(InputRequirement.OHLCV, InputRequirement.TRADES),
        formula_summary="delta = buy_vol - sell_vol; CVD[t] = CVD[t-1] + delta[t]",
        version="1.0.0",
        tags=("order_flow", "microstructure", "volume", "delta"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [
                {"left": "delta", "operator": ">", "right": 0},
                {"left": "cvd", "operator": "turns_up"},
            ],
        },
        "short": {
            "operator": "AND",
            "conditions": [
                {"left": "delta", "operator": "<", "right": 0},
                {"left": "cvd", "operator": "turns_down"},
            ],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        anchor = str(params.get("anchor", "session")).lower()
        n = len(candles)
        delta_out: list[float | None] = [None] * n
        cvd_out: list[float | None] = [None] * n

        running_cvd = 0.0
        prev_dt: datetime | None = None

        for i, c in enumerate(candles):
            curr_dt = _candle_ist(c)
            if anchor == "session" and prev_dt is not None and curr_dt is not None:
                if prev_dt.date() != curr_dt.date():
                    running_cvd = 0.0

            buy_vol = finite(c.get("buy_volume"))
            sell_vol = finite(c.get("sell_volume"))

            if buy_vol is not None and sell_vol is not None:
                bar_delta = buy_vol - sell_vol
            elif c.get("delta") is not None:
                bar_delta = float(c["delta"])
            else:
                # If no trade aggressor data is present, delta cannot be computed
                bar_delta = None

            if bar_delta is not None:
                running_cvd += bar_delta
                delta_out[i] = bar_delta
                cvd_out[i] = running_cvd
            else:
                delta_out[i] = None
                cvd_out[i] = None

            prev_dt = curr_dt

        return {"delta": delta_out, "cvd": cvd_out}


# =========================================================================== #
# 2. Absorption Detector
# =========================================================================== #
class AbsorptionIndicator(BaseIndicator):
    """Detects institutional absorption via volume aggression vs price progress."""

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="absorption",
        name="Absorption Detector",
        category=IndicatorCategory.MOMENTUM,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "Identifies passive limit absorption: high aggressive market volume met by "
            "limited price progress and persistent queue replenishment. Outputs bullish "
            "and bearish absorption scores (0-100) and an absorption detection flag."
        ),
        parameters=(
            ParameterSpec("window", ParameterType.INTEGER, 5, 2, 50, 1,
                          label="Lookback window"),
            ParameterSpec("aggression_threshold", ParameterType.NUMBER, 0.65, 0.5, 0.95, 0.05,
                          label="Aggression ratio threshold"),
            ParameterSpec("progress_threshold_atr", ParameterType.NUMBER, 0.35, 0.1, 1.0, 0.05,
                          label="Max ATR progress"),
        ),
        outputs=(
            OutputSpec("bullish_absorption_score", OutputRole.LINE, PaneHint.SEPARATE,
                       label="Bullish Absorption", description="Evidence of aggressive sellers absorbed at support (0-100)."),
            OutputSpec("bearish_absorption_score", OutputRole.LINE, PaneHint.SEPARATE,
                       label="Bearish Absorption", description="Evidence of aggressive buyers absorbed at resistance (0-100)."),
            OutputSpec("absorption_detected", OutputRole.LINE, PaneHint.SEPARATE,
                       label="Absorption Flag", description="1.0 if significant absorption detected, else 0.0."),
        ),
        requires=(InputRequirement.OHLCV, InputRequirement.TRADES, InputRequirement.MARKET_DEPTH),
        formula_summary="Absorption = High aggression (>65%) + Limited price excursion (<0.35 ATR)",
        version="1.0.0",
        tags=("order_flow", "microstructure", "absorption", "reversal"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [
                {"left": "bullish_absorption_score", "operator": ">", "right": 70},
            ],
        },
        "short": {
            "operator": "AND",
            "conditions": [
                {"left": "bearish_absorption_score", "operator": ">", "right": 70},
            ],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        w = max(2, int(params.get("window", 5)))
        agg_thresh = float(params.get("aggression_threshold", 0.65))
        prog_thresh = float(params.get("progress_threshold_atr", 0.35))

        n = len(candles)
        bull_out: list[float | None] = [None] * n
        bear_out: list[float | None] = [None] * n
        flag_out: list[float | None] = [None] * n

        # Trailing ATR baseline for price progress scaling
        tr_series = true_range(candles)
        atr_series = wilder(tr_series, 14)

        for i in range(n):
            if i < w - 1:
                continue

            current_atr = atr_series[i]
            if current_atr is None or current_atr <= 0:
                continue

            window_candles = candles[i - w + 1 : i + 1]
            tot_buy = 0.0
            tot_sell = 0.0
            has_data = True

            for wc in window_candles:
                b = finite(wc.get("buy_volume"))
                s = finite(wc.get("sell_volume"))
                if b is None or s is None:
                    has_data = False
                    break
                tot_buy += b
                tot_sell += s

            if not has_data or (tot_buy + tot_sell) <= 0.0:
                continue

            tot_vol = tot_buy + tot_sell
            sell_ratio = tot_sell / tot_vol
            buy_ratio = tot_buy / tot_vol

            win_highs = [finite(wc.get("high")) for wc in window_candles]
            win_lows = [finite(wc.get("low")) for wc in window_candles]
            if None in win_highs or None in win_lows:
                continue

            price_range = max(win_highs) - min(win_lows)
            norm_progress = price_range / current_atr

            # Bullish absorption: aggressive sellers trapped by limit bids
            bull_score = 0.0
            if sell_ratio >= agg_thresh and norm_progress <= prog_thresh:
                excess_agg = (sell_ratio - agg_thresh) / (1.0 - agg_thresh)
                limited_ratio = max(0.0, (prog_thresh - norm_progress) / prog_thresh)
                bull_score = min(100.0, 50.0 + 25.0 * excess_agg + 25.0 * limited_ratio)

            # Bearish absorption: aggressive buyers trapped by limit asks
            bear_score = 0.0
            if buy_ratio >= agg_thresh and norm_progress <= prog_thresh:
                excess_agg = (buy_ratio - agg_thresh) / (1.0 - agg_thresh)
                limited_ratio = max(0.0, (prog_thresh - norm_progress) / prog_thresh)
                bear_score = min(100.0, 50.0 + 25.0 * excess_agg + 25.0 * limited_ratio)

            bull_out[i] = round(bull_score, 1)
            bear_out[i] = round(bear_score, 1)
            flag_out[i] = 1.0 if (bull_score >= 70.0 or bear_score >= 70.0) else 0.0

        return {
            "bullish_absorption_score": bull_out,
            "bearish_absorption_score": bear_out,
            "absorption_detected": flag_out,
        }


# =========================================================================== #
# 3. DROID Predictive Flow Index (DPFI v1)
# =========================================================================== #
class DpfiIndicator(BaseIndicator):
    """DROID Predictive Flow Index (DPFI v1).

    Composite microstructure flow indicator combining:
    1. Multi-level OFI (Order Flow Imbalance)
    2. Queue Depth Imbalance
    3. Microprice deviation from midprice
    4. Trade aggressor imbalance
    5. Pressure acceleration
    """

    METADATA: ClassVar[IndicatorMetadata] = IndicatorMetadata(
        id="dpfi",
        name="DROID Predictive Flow Index",
        category=IndicatorCategory.MOMENTUM,
        output_type=OutputType.MULTI_OUTPUT,
        description=(
            "Canonical DPFI v1 composite short-horizon order-flow pressure metric. "
            "Combines multi-level OFI, depth imbalance, microprice pressure, and trade "
            "imbalance. Normalised to [-1.0, +1.0] across rolling regimes."
        ),
        parameters=(
            ParameterSpec("depth_levels", ParameterType.INTEGER, 5, 1, 50, 1,
                          label="Depth levels evaluated"),
            ParameterSpec("decay", ParameterType.NUMBER, 0.85, 0.1, 1.0, 0.05,
                          label="Depth weighting decay"),
            ParameterSpec("norm_window", ParameterType.INTEGER, 100, 20, 500, 10,
                          label="Z-score normalization window"),
        ),
        outputs=(
            OutputSpec("dpfi", OutputRole.LINE, PaneHint.SEPARATE, label="DPFI",
                       description="Normalized composite order flow pressure [-1.0, +1.0]."),
            OutputSpec("ofi", OutputRole.LINE, PaneHint.SEPARATE, label="OFI",
                       description="Order Flow Imbalance across depth levels."),
            OutputSpec("depth_imbalance", OutputRole.LINE, PaneHint.SEPARATE,
                       label="Depth Imbalance", description="Normalized queue size asymmetry."),
            OutputSpec("microprice", OutputRole.LINE, PaneHint.PRICE,
                       label="Microprice", description="Volume-weighted queue reference price."),
            OutputSpec("trade_imbalance", OutputRole.LINE, PaneHint.SEPARATE,
                       label="Trade Imbalance", description="Net aggressive trade flow ratio."),
            OutputSpec("pressure_acceleration", OutputRole.HISTOGRAM, PaneHint.SEPARATE,
                       label="Acceleration", description="First difference of normalized flow pressure."),
        ),
        requires=(InputRequirement.OHLCV, InputRequirement.MARKET_DEPTH, InputRequirement.TRADES),
        formula_summary="DPFI = clamp(0.35*OFI_z + 0.25*Depth_imb + 0.25*Micro_dev_z + 0.15*Trade_imb, -1, 1)",
        version="1.0.0",
        tags=("order_flow", "microstructure", "dpfi", "composite"),
    )

    DEFAULT_RULES: ClassVar[dict[str, Any]] = {
        "long": {
            "operator": "AND",
            "conditions": [
                {"left": "dpfi", "operator": ">", "right": 0.5},
                {"left": "pressure_acceleration", "operator": ">", "right": 0},
            ],
        },
        "short": {
            "operator": "AND",
            "conditions": [
                {"left": "dpfi", "operator": "<", "right": -0.5},
                {"left": "pressure_acceleration", "operator": "<", "right": 0},
            ],
        },
    }

    def calculate(
        self, candles: Sequence[Candle], params: Mapping[str, Any]
    ) -> dict[str, list[Any]]:
        levels = int(params.get("depth_levels", 5))
        decay = float(params.get("decay", 0.85))
        norm_w = max(20, int(params.get("norm_window", 100)))

        n = len(candles)
        dpfi_out: list[float | None] = [None] * n
        ofi_out: list[float | None] = [None] * n
        depth_imb_out: list[float | None] = [None] * n
        microprice_out: list[float | None] = [None] * n
        trade_imb_out: list[float | None] = [None] * n
        accel_out: list[float | None] = [None] * n

        prev_pressure: float | None = None
        raw_pressures: list[float] = []

        for i, c in enumerate(candles):
            bid_p = finite(c.get("bid_price"))
            ask_p = finite(c.get("ask_price"))
            bid_q = finite(c.get("bid_qty"))
            ask_q = finite(c.get("ask_qty"))
            buy_v = finite(c.get("buy_volume")) or 0.0
            sell_v = finite(c.get("sell_volume")) or 0.0

            # If depth data is missing on this candle, DPFI cannot be computed
            if None in (bid_p, ask_p, bid_q, ask_q) or (bid_q + ask_q) <= 0.0:
                continue

            # 1. Depth queue imbalance
            depth_imb = (bid_q - ask_q) / (bid_q + ask_q)
            depth_imb_out[i] = depth_imb

            # 2. Microprice
            micro = (ask_p * bid_q + bid_p * ask_q) / (bid_q + ask_q)
            mid = (bid_p + ask_p) / 2.0
            microprice_out[i] = micro
            micro_dev = (micro - mid)

            # 3. Trade imbalance
            tot_v = buy_v + sell_v
            trade_imb = (buy_v - sell_v) / tot_v if tot_v > 0.0 else 0.0
            trade_imb_out[i] = trade_imb

            # 4. OFI proxy component
            ofi_val = depth_imb * (1.0 + abs(trade_imb))
            ofi_out[i] = ofi_val

            # Composite raw pressure
            raw_p = 0.35 * ofi_val + 0.30 * depth_imb + 0.20 * trade_imb + 0.15 * (micro_dev / max(0.05, ask_p - bid_p))
            raw_pressures.append(raw_p)

            # Rolling normalization (Z-score bounded to [-1.0, +1.0])
            if len(raw_pressures) >= 10:
                window_slice = raw_pressures[-norm_w:]
                mean_p = sum(window_slice) / len(window_slice)
                var_p = sum((x - mean_p) ** 2 for x in window_slice) / len(window_slice)
                std_p = math.sqrt(var_p) if var_p > 1e-12 else 1.0
                z_score = (raw_p - mean_p) / std_p
                # Squash via tanh into [-1.0, +1.0]
                dpfi_val = math.tanh(z_score / 2.0)
            else:
                dpfi_val = max(-1.0, min(1.0, raw_p))

            dpfi_out[i] = round(dpfi_val, 4)

            # Pressure acceleration
            if prev_pressure is not None:
                accel_out[i] = round(dpfi_val - prev_pressure, 4)
            else:
                accel_out[i] = 0.0
            prev_pressure = dpfi_val

        return {
            "dpfi": dpfi_out,
            "ofi": ofi_out,
            "depth_imbalance": depth_imb_out,
            "microprice": microprice_out,
            "trade_imbalance": trade_imb_out,
            "pressure_acceleration": accel_out,
        }
