"""Triple-Barrier Label Engine with Adverse Path Resolution (Tier 0).

Implements de Prado's Triple-Barrier Method:
1. Upper barrier: Take-Profit (k_tp * ATR or target_pct)
2. Lower barrier: Stop-Loss (k_sl * ATR or stop_pct)
3. Horizontal barrier: Time expiration (T_max bars)

Key Institutional Safeguards:
- Adverse OHLC Resolution: When both barriers are crossed in the same bar, assume STOP FIRST.
- Cost-Aware Labeling: Outputs both y_raw and y_net (after modeled round-trip costs).
- Interval tracking [t_start, t_end] for purge & embargo validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, List, Dict, Any
import polars as pl
import numpy as np
import structlog

logger = structlog.get_logger(__name__)

ExitReason = Literal["TARGET_HIT", "STOP_HIT", "TIME_EXPIRED"]


@dataclass
class BarrierOutcome:
    t_start: datetime
    t_end: datetime
    bars_held: int
    exit_reason: ExitReason
    entry_price: float
    exit_price: float
    gross_return: float
    net_return: float
    mfe: float  # Maximum Favorable Excursion
    mae: float  # Maximum Adverse Excursion
    y_raw: int  # +1 (profit), -1 (loss), 0 (flat/timeout)
    y_net: int  # +1 (net profit after costs), -1 (net loss after costs), 0


class TripleBarrierLabelEngine:
    """Computes rigorous, leakage-safe triple-barrier labels."""

    def __init__(
        self,
        t_max_bars: int = 15,
        k_tp: float = 1.5,
        k_sl: float = 1.0,
        fixed_cost_pct: float = 0.0008,  # 8 bps round-trip reference cost placeholder
    ):
        self.t_max_bars = t_max_bars
        self.k_tp = k_tp
        self.k_sl = k_sl
        self.fixed_cost_pct = fixed_cost_pct

    def label_candidates(
        self,
        df: pl.DataFrame,
        candidate_indices: list[int],
        directions: list[int],  # +1 for LONG, -1 for SHORT
        atr_col: str = "atr",
        k_tps: list[float] | None = None,
        k_sls: list[float] | None = None,
        t_max_bars_list: list[int] | None = None,
    ) -> list[BarrierOutcome]:
        """Labels a set of candidate signals against future price path.
        
        candidate_indices: indices in df where candidate fired
        directions: +1 (LONG) or -1 (SHORT)
        k_tps: optional per-candidate take-profit ATR multipliers
        k_sls: optional per-candidate stop-loss ATR multipliers
        t_max_bars_list: optional per-candidate time barrier limits
        """
        outcomes: list[BarrierOutcome] = []
        n_bars = len(df)

        timestamps = df["timestamp"].to_list()
        opens = df["open"].to_list()
        highs = df["high"].to_list()
        lows = df["low"].to_list()
        closes = df["close"].to_list()
        atrs = df[atr_col].to_list() if atr_col in df.columns else [c * 0.003 for c in closes]

        for i, (idx, direction) in enumerate(zip(candidate_indices, directions)):
            if idx + 1 >= n_bars:
                continue  # Cannot trade on the very last bar

            # Realistic entry: Next bar open
            entry_idx = idx + 1
            t_start = timestamps[entry_idx]
            entry_price = opens[entry_idx]
            current_atr = atrs[idx] or (entry_price * 0.003)

            cand_k_tp = k_tps[i] if k_tps is not None and i < len(k_tps) else self.k_tp
            cand_k_sl = k_sls[i] if k_sls is not None and i < len(k_sls) else self.k_sl
            cand_t_max = t_max_bars_list[i] if t_max_bars_list is not None and i < len(t_max_bars_list) else self.t_max_bars

            # Barriers in price units
            tp_dist = cand_k_tp * current_atr
            sl_dist = cand_k_sl * current_atr

            if direction == 1:  # LONG
                tp_price = entry_price + tp_dist
                sl_price = entry_price - sl_dist
            else:  # SHORT
                tp_price = entry_price - tp_dist
                sl_price = entry_price + sl_dist

            # Excursion trackers
            mfe = 0.0
            mae = 0.0
            exit_idx = entry_idx
            exit_reason: ExitReason = "TIME_EXPIRED"
            exit_price = entry_price

            max_forward = min(entry_idx + cand_t_max, n_bars)

            for f_idx in range(entry_idx, max_forward):
                f_high = highs[f_idx]
                f_low = lows[f_idx]
                f_close = closes[f_idx]
                exit_idx = f_idx

                # Compute excursion relative to direction
                if direction == 1:
                    bar_mfe = (f_high - entry_price) / entry_price
                    bar_mae = (f_low - entry_price) / entry_price
                    mfe = max(mfe, bar_mfe)
                    mae = min(mae, bar_mae)

                    tp_hit = f_high >= tp_price
                    sl_hit = f_low <= sl_price
                else:  # SHORT
                    bar_mfe = (entry_price - f_low) / entry_price
                    bar_mae = (entry_price - f_high) / entry_price
                    mfe = max(mfe, bar_mfe)
                    mae = min(mae, bar_mae)

                    tp_hit = f_low <= tp_price
                    sl_hit = f_high >= sl_price

                # Adverse OHLC Path Resolution:
                # When both TP and SL are crossed within the same bar, assume STOP FIRST.
                if tp_hit and sl_hit:
                    exit_reason = "STOP_HIT"
                    exit_price = sl_price
                    break
                elif sl_hit:
                    exit_reason = "STOP_HIT"
                    exit_price = sl_price
                    break
                elif tp_hit:
                    exit_reason = "TARGET_HIT"
                    exit_price = tp_price
                    break

            if exit_reason == "TIME_EXPIRED":
                # Exit at close of the final evaluation bar
                exit_price = closes[exit_idx]

            t_end = timestamps[exit_idx]
            bars_held = exit_idx - entry_idx + 1

            if direction == 1:
                gross_return = (exit_price - entry_price) / entry_price
            else:
                gross_return = (entry_price - exit_price) / entry_price

            net_return = gross_return - self.fixed_cost_pct

            # Determine classification label
            if gross_return > 0.0005:
                y_raw = 1
            elif gross_return < -0.0005:
                y_raw = -1
            else:
                y_raw = 0

            if net_return > 0.0:
                y_net = 1
            elif net_return < 0.0:
                y_net = -1
            else:
                y_net = 0

            outcomes.append(BarrierOutcome(
                t_start=t_start,
                t_end=t_end,
                bars_held=bars_held,
                exit_reason=exit_reason,
                entry_price=entry_price,
                exit_price=exit_price,
                gross_return=gross_return,
                net_return=net_return,
                mfe=mfe,
                mae=mae,
                y_raw=y_raw,
                y_net=y_net,
            ))

        return outcomes
