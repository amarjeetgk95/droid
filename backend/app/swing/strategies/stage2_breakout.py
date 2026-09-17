"""
Stage 2 / 4 Trend Options Strategy (v6.0 Options Overhaul).
Detects Stan Weinstein / Mark Minervini Stage 2 structural breakouts (CE)
and Stage 4 structural breakdowns (PE) on the underlying index.
Strategies: STAGE2_CE, STAGE2_PE.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from app.swing.models import MarketRegime
from app.swing.technical import SwingFeatures
from app.swing.strategies.base import BaseSwingStrategy, SwingSignal


class Stage2OptionsStrategy(BaseSwingStrategy):
    strategy_id = "STAGE2_CE"
    strategy_id_short = "STAGE2_PE"
    strategy_name = "Stage 2 Trend Breakout"

    expected_holding_days = 10
    candidate_types = ["ITM_1", "ATM"]
    max_theta_drag_ratio = 25.0
    dte_fallback = 12
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
        if len(candles) < 40 or features.sma_50 is None:
            return None

        is_bullish = features.price_above_sma50
        direction: Literal["LONG_CALL", "LONG_PUT"] = "LONG_CALL" if is_bullish else "LONG_PUT"

        if is_bullish:
            if features.dist_from_52w_high_pct < -15.0:
                return None
            trigger = features.pivot_breakout_level if features.pivot_breakout_level > 0 else features.recent_swing_high
            structural_stop = features.recent_swing_low
            stop_dist = max(features.atr_14 * 1.2, trigger - structural_stop)
            spot_stop = round(trigger - stop_dist, 2)
            expected_move = max(features.atr_14 * 3.0, stop_dist * 2.2)
        else:
            trigger = features.recent_swing_low
            structural_stop = features.recent_swing_high
            stop_dist = max(features.atr_14 * 1.2, structural_stop - trigger)
            spot_stop = round(trigger + stop_dist, 2)
            expected_move = max(features.atr_14 * 3.0, stop_dist * 2.2)

        tech_reasons = [
            f"Stage 2/4 trend confirmation: Spot (\u20b9{spot:.2f}) vs 50 SMA (\u20b9{features.sma_50:.2f})",
            f"Breaking multi-week structural level at \u20b9{trigger:.2f}",
            f"Volume RVOL: {features.rvol:.2f}",
        ]

        return SwingSignal(
            direction=direction,
            trigger=trigger,
            spot_stop=spot_stop,
            stop_dist=stop_dist,
            expected_move=expected_move,
            technical_reasons=tech_reasons,
        )


Stage2BreakoutStrategy = Stage2OptionsStrategy
