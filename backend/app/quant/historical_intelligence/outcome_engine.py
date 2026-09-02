"""
Forward Outcome Engine — §17, §18, §19, §20, §52
Evaluates the real forward outcome of a historical analog window with ZERO lookahead bias.
Computes MFE, MAE, target/stop hits, and empirical risk/reward distributions.
"""
from __future__ import annotations

from typing import NamedTuple
from app.quant.historical_intelligence.models import CandleData


class ForwardOutcomeResult(NamedTuple):
    forward_candles_count: int
    forward_returns: list[float]
    mfe_pct: float                      # Maximum Favorable Excursion % (+ve)
    mae_pct: float                      # Maximum Adverse Excursion % (-ve)
    target_hit: bool
    stop_hit: bool
    time_to_target_bars: int | None
    session_end_return_pct: float


def compute_forward_outcomes(
    forward_candles: list[CandleData],
    entry_price: float,
    target_pct: float = 0.50,
    stop_pct: float = 0.25,
) -> ForwardOutcomeResult:
    """
    Computes forward trajectory metrics from [T+1 ... T+H] relative to entry_price.
    Applies strict same-candle conservative ambiguity resolution (§52).
    """
    if not forward_candles or entry_price <= 0:
        return ForwardOutcomeResult(
            forward_candles_count=0,
            forward_returns=[],
            mfe_pct=0.0,
            mae_pct=0.0,
            target_hit=False,
            stop_hit=False,
            time_to_target_bars=None,
            session_end_return_pct=0.0,
        )

    target_price = entry_price * (1.0 + (target_pct / 100.0))
    stop_price = entry_price * (1.0 - (stop_pct / 100.0))

    highest_p = entry_price
    lowest_p = entry_price
    target_hit = False
    stop_hit = False
    time_to_target: int | None = None
    forward_returns: list[float] = []

    for i, c in enumerate(forward_candles):
        # Track price evolution
        ret = ((c.close - entry_price) / entry_price) * 100.0
        forward_returns.append(round(ret, 4))

        highest_p = max(highest_p, c.high)
        lowest_p = min(lowest_p, c.low)

        # Same-candle ambiguity resolution (§52):
        # If both target and stop are spanned by the candle's high-low range,
        # apply conservative pessimism (assume Stop was hit first).
        candle_hits_target = c.high >= target_price
        candle_hits_stop = c.low <= stop_price

        if candle_hits_target and candle_hits_stop:
            if not target_hit and not stop_hit:
                stop_hit = True  # Conservative rule (§52)
        elif candle_hits_target and not stop_hit and not target_hit:
            target_hit = True
            if time_to_target is None:
                time_to_target = i + 1
        elif candle_hits_stop and not target_hit and not stop_hit:
            stop_hit = True

    mfe_pct = ((highest_p - entry_price) / entry_price) * 100.0
    mae_pct = ((lowest_p - entry_price) / entry_price) * 100.0
    final_ret = ((forward_candles[-1].close - entry_price) / entry_price) * 100.0

    return ForwardOutcomeResult(
        forward_candles_count=len(forward_candles),
        forward_returns=forward_returns,
        mfe_pct=round(mfe_pct, 4),
        mae_pct=round(mae_pct, 4),
        target_hit=target_hit,
        stop_hit=stop_hit,
        time_to_target_bars=time_to_target,
        session_end_return_pct=round(final_ret, 4),
    )
