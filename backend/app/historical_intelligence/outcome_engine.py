"""
Historical Outcome Engine & Multi-Horizon Tracking — §§11, 15, 16, 33
Evaluates 15m, 30m, and 60m forward paths with conservative execution semantics.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from app.historical_intelligence.schemas import (
    CandleData,
    ForwardOutcomeHorizon,
    HistoricalOutcomeRecord,
)
from app.historical_intelligence.versioning import OUTCOME_VERSION


def compute_horizon_outcome(
    forward_candles: list[CandleData],
    entry_price: float,
    horizon_minutes: int,
    target_pct: float = 0.50,
    stop_pct: float = 0.25,
    prior_bias: str = "BULLISH",
) -> ForwardOutcomeHorizon:
    """
    Evaluates forward path over a slice of forward candles.
    Enforces conservative same-candle resolution: if both target and stop
    are hit within the same candle, stop_hit takes precedence.
    """
    if not forward_candles or entry_price <= 0:
        return ForwardOutcomeHorizon(
            horizon_minutes=horizon_minutes,
            return_pct=0.0,
            direction="NEUTRAL",
            mfe_pct=0.0,
            mae_pct=0.0,
            high_price=entry_price,
            low_price=entry_price,
            target_hit=False,
            stop_hit=False,
            duration_bars=None,
            continuation=False,
            failure=False,
            reversal=False,
        )

    highs = [c.high for c in forward_candles]
    lows = [c.low for c in forward_candles]
    closes = [c.close for c in forward_candles]

    highest_p = max(highs)
    lowest_p = min(lows)
    terminal_p = closes[-1]

    # Excursions relative to entry price
    is_bullish_bias = (prior_bias == "BULLISH")
    if is_bullish_bias:
        mfe_pct = max(0.0, ((highest_p - entry_price) / entry_price) * 100.0)
        mae_pct = min(0.0, ((lowest_p - entry_price) / entry_price) * 100.0)
        target_p = entry_price * (1.0 + (target_pct / 100.0))
        stop_p = entry_price * (1.0 - (stop_pct / 100.0))
    else:  # BEARISH bias
        mfe_pct = max(0.0, ((entry_price - lowest_p) / entry_price) * 100.0)
        mae_pct = min(0.0, ((entry_price - highest_p) / entry_price) * 100.0)
        target_p = entry_price * (1.0 - (target_pct / 100.0))
        stop_p = entry_price * (1.0 + (stop_pct / 100.0))

    ret_pct = ((terminal_p - entry_price) / entry_price) * 100.0

    target_hit = False
    stop_hit = False
    duration_bars: Optional[int] = None

    for bar_idx, c in enumerate(forward_candles, start=1):
        bar_hit_target = False
        bar_hit_stop = False

        if is_bullish_bias:
            if c.high >= target_p:
                bar_hit_target = True
            if c.low <= stop_p:
                bar_hit_stop = True
        else:
            if c.low <= target_p:
                bar_hit_target = True
            if c.high >= stop_p:
                bar_hit_stop = True

        # Conservative same-candle conflict resolution
        if bar_hit_target and bar_hit_stop:
            stop_hit = True
            duration_bars = bar_idx
            break
        elif bar_hit_stop:
            stop_hit = True
            duration_bars = bar_idx
            break
        elif bar_hit_target:
            target_hit = True
            duration_bars = bar_idx
            break

    # Classify direction
    direction: str = "NEUTRAL"
    if ret_pct > 0.08:
        direction = "BULLISH"
    elif ret_pct < -0.08:
        direction = "BEARISH"

    # Continuation vs Failure vs Reversal
    continuation = (direction == prior_bias) and not stop_hit
    failure = stop_hit or (direction != prior_bias and abs(ret_pct) > stop_pct)
    reversal = (direction != prior_bias) and (abs(ret_pct) > target_pct * 0.75)

    return ForwardOutcomeHorizon(
        horizon_minutes=horizon_minutes,
        return_pct=round(ret_pct, 4),
        direction=direction,
        mfe_pct=round(mfe_pct, 4),
        mae_pct=round(mae_pct, 4),
        high_price=round(highest_p, 2),
        low_price=round(lowest_p, 2),
        target_hit=target_hit,
        stop_hit=stop_hit,
        duration_bars=duration_bars,
        continuation=continuation,
        failure=failure,
        reversal=reversal,
    )


def construct_forward_outcomes(
    snapshot_id: str,
    instrument: str,
    timestamp: datetime,
    entry_price: float,
    future_candles: list[CandleData],
    target_pct: float = 0.50,
    stop_pct: float = 0.25,
    prior_bias: str = "BULLISH",
) -> HistoricalOutcomeRecord:
    """
    Constructs multi-horizon forward outcome record for 15m, 30m, and 60m.
    Expects future_candles to start at T+1 (strictly point-in-time).
    """
    c_15m = future_candles[:15]
    c_30m = future_candles[:30]
    c_60m = future_candles[:60]

    out_15 = compute_horizon_outcome(c_15m, entry_price, 15, target_pct, stop_pct, prior_bias)
    out_30 = compute_horizon_outcome(c_30m, entry_price, 30, target_pct, stop_pct, prior_bias)
    out_60 = compute_horizon_outcome(c_60m, entry_price, 60, target_pct, stop_pct, prior_bias)

    return HistoricalOutcomeRecord(
        snapshot_id=snapshot_id,
        instrument=instrument,
        timestamp=timestamp,
        entry_price=entry_price,
        outcome_15m=out_15,
        outcome_30m=out_30,
        outcome_60m=out_60,
        labeled_at=datetime.now(timezone.utc),
        outcome_version=OUTCOME_VERSION,
    )
