"""DROID MACD + Fisher-9 Exhaustion Research — Forward Outcome Engine.

Specification Reference: §25, §26, §58, DEC-006, DEC-010.
"""

from __future__ import annotations

from dataclasses import dataclass
import pandas as pd
import numpy as np
from app.signals.strategies.fisher_macd.event_detector import ResearchEvent


@dataclass
class EventOutcome:
    """Evaluated forward outcome for an event."""
    event: ResearchEvent
    horizon_bars: int
    raw_return_atr: float
    mfe_atr: float
    mae_atr: float
    target_hit: bool  # First passage +1.0 ATR
    stop_hit: bool    # First passage -1.0 ATR
    success: bool     # Target hit before stop hit
    friction_adjusted_return_atr: float = 0.0


def compute_forward_outcomes(
    df: pd.DataFrame,
    events: list[ResearchEvent],
    horizon_bars: int = 6,  # 6 bars * 5m = 30m horizon
    target_atr_multiple: float = 1.0,
    stop_atr_multiple: float = 1.0,
    friction_cost_atr: float = 0.05,
    apply_friction: bool = False,
) -> list[EventOutcome]:
    """Compute forward returns, MFE/MAE, and first-passage barrier hits.

    Direction-aligned:
      - BEARISH_REVERSAL: profit when price falls.
      - BULLISH_REVERSAL: profit when price rises.
    """
    n = len(df)
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    timestamps = df["timestamp"].values

    outcomes: list[EventOutcome] = []

    for ev in events:
        i = ev.bar_index
        if i + horizon_bars >= n:
            continue

        entry_price = ev.price
        entry_atr = ev.atr
        if entry_atr <= 0:
            continue

        target_delta = target_atr_multiple * entry_atr
        stop_delta = stop_atr_multiple * entry_atr

        fwd_highs = highs[i + 1 : i + 1 + horizon_bars]
        fwd_lows = lows[i + 1 : i + 1 + horizon_bars]
        exit_close = closes[i + horizon_bars]

        if ev.direction == "BEARISH_REVERSAL":
            # Profit when price goes down
            raw_return = (entry_price - exit_close) / entry_atr
            mfe = (entry_price - np.min(fwd_lows)) / entry_atr
            mae = (np.max(fwd_highs) - entry_price) / entry_atr

            # Barrier monitoring
            target_price = entry_price - target_delta
            stop_price = entry_price + stop_delta

            target_hit = False
            stop_hit = False
            for h_idx in range(len(fwd_highs)):
                bar_h = fwd_highs[h_idx]
                bar_l = fwd_lows[h_idx]

                hit_t = bar_l <= target_price
                hit_s = bar_h >= stop_price

                if hit_t and hit_s:
                    # Same-bar double touch: pessimistic resolution (DEC-006)
                    stop_hit = True
                    break
                elif hit_t:
                    target_hit = True
                    break
                elif hit_s:
                    stop_hit = True
                    break

        else:  # BULLISH_REVERSAL
            # Profit when price goes up
            raw_return = (exit_close - entry_price) / entry_atr
            mfe = (np.max(fwd_highs) - entry_price) / entry_atr
            mae = (entry_price - np.min(fwd_lows)) / entry_atr

            # Barrier monitoring
            target_price = entry_price + target_delta
            stop_price = entry_price - stop_delta

            target_hit = False
            stop_hit = False
            for h_idx in range(len(fwd_highs)):
                bar_h = fwd_highs[h_idx]
                bar_l = fwd_lows[h_idx]

                hit_t = bar_h >= target_price
                hit_s = bar_l <= stop_price

                if hit_t and hit_s:
                    # Same-bar double touch: pessimistic resolution (DEC-006)
                    stop_hit = True
                    break
                elif hit_t:
                    target_hit = True
                    break
                elif hit_s:
                    stop_hit = True
                    break

        success = target_hit and not stop_hit
        friction_ret = raw_return - friction_cost_atr if apply_friction else raw_return

        outcomes.append(
            EventOutcome(
                event=ev,
                horizon_bars=horizon_bars,
                raw_return_atr=float(raw_return),
                mfe_atr=float(mfe),
                mae_atr=float(mae),
                target_hit=target_hit,
                stop_hit=stop_hit,
                success=success,
                friction_adjusted_return_atr=float(friction_ret),
            )
        )

    return outcomes
