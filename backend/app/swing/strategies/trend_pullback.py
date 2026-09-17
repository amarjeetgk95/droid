"""
Pullback Options Strategy (v6.0 Options Overhaul).
Detects 20 EMA trend pullbacks on the underlying index (bullish support / bearish resistance),
selects optimal CE/PE contracts via QuantitativeContractSelector, and gates risk.
Strategies: PULLBACK_CE, PULLBACK_PE.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from app.swing.models import MarketRegime
from app.swing.technical import SwingFeatures
from app.swing.strategies.base import BaseSwingStrategy, SwingSignal


class PullbackOptionsStrategy(BaseSwingStrategy):
    strategy_id = "PULLBACK_CE"
    strategy_id_short = "PULLBACK_PE"
    strategy_name = "20 EMA Trend Pullback"

    expected_holding_days = 6
    candidate_types = ["ITM_1", "ATM"]
    max_theta_drag_ratio = 25.0
    dte_fallback = 8
    trigger_watch_states = True
    regime_blocks_unhedged = True

    def _detect(
        self,
        underlying: str,
        features: SwingFeatures,
        candles: list[dict[str, Any]],
        regime: MarketRegime,
        spot: float,
        current_iv: float,
        iv_percentile: float,
    ) -> Optional[SwingSignal]:
        if len(candles) < 30 or features.ema_20 is None or features.sma_50 is None:
            return None

        is_bullish = features.price_above_sma50
        direction: Literal["LONG_CALL", "LONG_PUT"] = "LONG_CALL" if is_bullish else "LONG_PUT"

        ema20 = features.ema_20
        dist_to_ema20 = abs(spot - ema20) / ema20
        if dist_to_ema20 > 0.025:
            return None

        bar_range = max(0.01, features.high - features.low)
        if is_bullish:
            close_pos = (features.close - features.low) / bar_range
            if close_pos < 0.35:
                return None  # No rejection of 20 EMA
            trigger = round(features.high, 2)
            structural_stop = round(min(c["low"] for c in candles[-3:]), 2)
            stop_dist = max(features.atr_14 * 1.2, trigger - structural_stop)
            spot_stop = round(trigger - stop_dist, 2)
            expected_move = max(features.atr_14 * 2.5, stop_dist * 2.0)
        else:
            close_pos = (features.high - features.close) / bar_range
            if close_pos < 0.35:
                return None  # No downward rejection
            trigger = round(features.low, 2)
            structural_stop = round(max(c["high"] for c in candles[-3:]), 2)
            stop_dist = max(features.atr_14 * 1.2, structural_stop - trigger)
            spot_stop = round(trigger + stop_dist, 2)
            expected_move = max(features.atr_14 * 2.5, stop_dist * 2.0)

        tech_reasons = [
            f"Underlying retested 20 EMA at \u20b9{ema20:.2f} with strong rejection wick",
            f"Controlled pullback volume (RVOL: {features.rvol:.2f})",
            f"Trigger level: \u20b9{trigger:.2f}, Structural Invalidation: \u20b9{spot_stop:.2f}",
        ]

        return SwingSignal(
            direction=direction,
            trigger=trigger,
            spot_stop=spot_stop,
            stop_dist=stop_dist,
            expected_move=expected_move,
            technical_reasons=tech_reasons,
        )


TrendPullbackStrategy = PullbackOptionsStrategy
