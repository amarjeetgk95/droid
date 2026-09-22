"""S7 Event Engine — Structural Level & Absorption Detection (S7SPEC_v1.0).

Identifies key structural boundaries (Prev Day High/Low, VWAP +/- 2std bands)
and detects absorption events where institutional volume absorbs momentum.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, List, Optional
import polars as pl
import numpy as np

from app.quant.strategies.s7_config import S7Config, create_s7_default_config


@dataclass(frozen=True)
class StructuralLevel:
    """A detected structural boundary."""
    price: float
    level_type: str  # "PREV_DAY_HIGH", "PREV_DAY_LOW", "VWAP_UPPER", "VWAP_LOWER"
    role: Literal["SUPPORT", "RESISTANCE"]


@dataclass(frozen=True)
class LevelApproach:
    """A bar approaching a structural level."""
    bar_index: int
    timestamp: datetime
    level: StructuralLevel
    approach_direction: int  # +1 = approaching from below (hitting resistance), -1 = approaching from above (hitting support)
    approach_bars: int
    distance_atr: float


@dataclass(frozen=True)
class AbsorptionEvent:
    """A validated absorption event at a structural boundary."""
    bar_index: int
    timestamp: datetime
    level: StructuralLevel
    reversal_direction: int  # +1 = LONG reversal (bounce from support), -1 = SHORT reversal (rejection from resistance)
    volume_ratio: float
    price_displacement: float
    wick_rejection: float
    rsi: float
    atr: float
    entry_ref_price: float
    vwap: float
    trigger_reason: str


class S7EventEngine:
    """Event extraction engine for S7 Absorption Reversals."""

    def __init__(self, config: S7Config | None = None):
        self.config = config or create_s7_default_config()

    def detect_events(self, df: pl.DataFrame) -> list[AbsorptionEvent]:
        """Scans feature DataFrame for structural absorption reversal events."""
        if len(df) == 0:
            return []

        # Extract required columns
        timestamps = df["timestamp"].to_list()
        closes = df["close"].to_list()
        highs = df["high"].to_list()
        lows = df["low"].to_list()
        opens = df["open"].to_list()
        atrs = df["atr"].to_list()
        rsis = df["rsi"].to_list()
        vwaps = df["vwap"].to_list()
        vwap_uppers = df["vwap_upper_2std"].to_list()
        vwap_lowers = df["vwap_lower_2std"].to_list()
        vol_ratios = df["volume_ratio"].to_list()
        displacements = df["price_displacement"].to_list()
        wick_rejections = df["wick_rejection_ratio"].to_list()
        upper_wicks = df["upper_wick_ratio"].to_list()
        lower_wicks = df["lower_wick_ratio"].to_list()
        streaks = df["directional_streak"].to_list() if "directional_streak" in df.columns else [0] * len(df)
        prev_day_highs = df["prev_day_high"].to_list() if "prev_day_high" in df.columns else [None] * len(df)
        prev_day_lows = df["prev_day_low"].to_list() if "prev_day_low" in df.columns else [None] * len(df)

        events: list[AbsorptionEvent] = []
        n = len(df)
        prox_atr = self.config.levels.proximity_atr
        min_vol = self.config.absorption.min_volume_ratio
        max_disp = self.config.absorption.max_price_displacement
        min_wick = self.config.absorption.min_wick_rejection
        min_approach = self.config.absorption.min_approach_bars

        for i in range(1, n):
            c = closes[i]
            h = highs[i]
            l = lows[i]
            o = opens[i]
            atr = atrs[i]
            if atr is None or atr <= 0.0 or c is None:
                continue

            v_val = vwaps[i] or c
            up2 = vwap_uppers[i]
            lo2 = vwap_lowers[i]
            vr = vol_ratios[i] or 1.0
            disp = displacements[i] if displacements[i] is not None else (abs(c - o) / atr)
            wick_rej = wick_rejections[i] if wick_rejections[i] is not None else 0.0
            u_wick = upper_wicks[i] or 0.0
            l_wick = lower_wicks[i] or 0.0
            streak = streaks[i]
            rsi = rsis[i] or 50.0
            pd_h = prev_day_highs[i]
            pd_l = prev_day_lows[i]

            # Collect active levels at bar i
            resistance_levels: list[tuple[float, str]] = []
            support_levels: list[tuple[float, str]] = []

            if pd_h is not None:
                resistance_levels.append((pd_h, "PREV_DAY_HIGH"))
            if up2 is not None:
                resistance_levels.append((up2, "VWAP_UPPER"))

            if pd_l is not None:
                support_levels.append((pd_l, "PREV_DAY_LOW"))
            if lo2 is not None:
                support_levels.append((lo2, "VWAP_LOWER"))

            # --- Check Resistance Absorption (Bearish Reversal: Short Setup) ---
            for res_price, res_type in resistance_levels:
                dist_to_res = (res_price - c) / atr
                hit_res = (h >= res_price - (0.2 * atr)) or (abs(dist_to_res) <= prox_atr)
                had_approach = streak >= min_approach or (c > closes[i - 1])

                if (
                    hit_res
                    and had_approach
                    and vr >= min_vol
                    and disp <= max_disp
                    and u_wick >= min_wick
                    and c < (h + l) / 2.0  # Closed in bottom half of bar
                ):
                    reason = (
                        f"Absorption at resistance {res_type} ({res_price:.1f}): "
                        f"VolRatio={vr:.2f}>={min_vol}, Disp={disp:.2f}<={max_disp}, "
                        f"UpperWick={u_wick:.2f}>={min_wick}, Streak={streak}"
                    )
                    events.append(AbsorptionEvent(
                        bar_index=i,
                        timestamp=timestamps[i],
                        level=StructuralLevel(price=res_price, level_type=res_type, role="RESISTANCE"),
                        reversal_direction=-1,
                        volume_ratio=vr,
                        price_displacement=disp,
                        wick_rejection=u_wick,
                        rsi=rsi,
                        atr=atr,
                        entry_ref_price=c,
                        vwap=v_val,
                        trigger_reason=reason,
                    ))
                    break  # Avoid duplicate events at same bar

            # --- Check Support Absorption (Bullish Reversal: Long Setup) ---
            for sup_price, sup_type in support_levels:
                dist_to_sup = (c - sup_price) / atr
                hit_sup = (l <= sup_price + (0.2 * atr)) or (abs(dist_to_sup) <= prox_atr)
                had_approach = streak <= -min_approach or (c < closes[i - 1])

                if (
                    hit_sup
                    and had_approach
                    and vr >= min_vol
                    and disp <= max_disp
                    and l_wick >= min_wick
                    and c > (h + l) / 2.0  # Closed in upper half of bar
                ):
                    reason = (
                        f"Absorption at support {sup_type} ({sup_price:.1f}): "
                        f"VolRatio={vr:.2f}>={min_vol}, Disp={disp:.2f}<={max_disp}, "
                        f"LowerWick={l_wick:.2f}>={min_wick}, Streak={streak}"
                    )
                    events.append(AbsorptionEvent(
                        bar_index=i,
                        timestamp=timestamps[i],
                        level=StructuralLevel(price=sup_price, level_type=sup_type, role="SUPPORT"),
                        reversal_direction=1,
                        volume_ratio=vr,
                        price_displacement=disp,
                        wick_rejection=l_wick,
                        rsi=rsi,
                        atr=atr,
                        entry_ref_price=c,
                        vwap=v_val,
                        trigger_reason=reason,
                    ))
                    break

        return events
