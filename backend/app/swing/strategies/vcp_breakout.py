"""
Breakout Options Strategy (v6.0 Options Overhaul).
Detects Volatility Contraction Pattern (VCP) breakouts on the underlying index,
selects optimal CE/PE contracts via QuantitativeContractSelector, and gates risk.
Strategies: TREND_BREAKOUT_CE, TREND_BREAKOUT_PE.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from app.swing.models import MarketRegime
from app.swing.technical import SwingFeatures
from app.swing.strategies.base import BaseSwingStrategy, SetupContext, SwingSignal


class BreakoutOptionsStrategy(BaseSwingStrategy):
    strategy_id = "TREND_BREAKOUT_CE"
    strategy_id_short = "TREND_BREAKOUT_PE"
    strategy_name = "Trend Contraction Breakout"

    expected_holding_days = 8
    candidate_types = ["ITM_1", "ATM"]
    max_theta_drag_ratio = 25.0
    dte_fallback = 10
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
        if len(candles) < 25:
            return None

        # Determine directional bias based on moving average trend
        is_bullish = features.price_above_sma50
        direction: Literal["LONG_CALL", "LONG_PUT"] = "LONG_CALL" if is_bullish else "LONG_PUT"

        # Contraction check
        if features.range_contraction_ratio > 0.85:
            return None

        if is_bullish:
            if features.dist_from_52w_high_pct < -25.0:
                return None
            trigger = features.pivot_breakout_level if features.pivot_breakout_level > 0 else features.recent_swing_high
            lows_last_5 = [c["low"] for c in candles[-5:]]
            structural_stop = min(lows_last_5) if lows_last_5 else features.recent_swing_low
            stop_dist = max(features.atr_14 * 1.2, trigger - structural_stop)
            spot_stop = round(trigger - stop_dist, 2)
            expected_move = max(features.atr_14 * 2.5, stop_dist * 2.0)
        else:
            trigger = features.recent_swing_low
            highs_last_5 = [c["high"] for c in candles[-5:]]
            structural_stop = max(highs_last_5) if highs_last_5 else features.recent_swing_high
            stop_dist = max(features.atr_14 * 1.2, structural_stop - trigger)
            spot_stop = round(trigger + stop_dist, 2)
            expected_move = max(features.atr_14 * 2.5, stop_dist * 2.0)

        return SwingSignal(
            direction=direction,
            trigger=trigger,
            spot_stop=spot_stop,
            stop_dist=stop_dist,
            expected_move=expected_move,
        )

    def _technical_reasons(self, ctx: SetupContext) -> list[str]:
        signal = ctx.signal
        return [
            f"Range contraction ratio {ctx.features.range_contraction_ratio:.2f} confirms volatility squeeze",
            f"Underlying {signal.direction.replace('_', ' ')} trigger at \u20b9{signal.trigger:.2f} with structural stop at \u20b9{signal.spot_stop:.2f}",
            f"Projected move: +{signal.expected_move:.1f} pts ({ctx.iv_edge:.1f}x option implied move)",
        ]

    def _options_reasons(self, ctx: SetupContext) -> list[str]:
        return [
            f"Selected contract: {ctx.contract_symbol} ({ctx.selection.selected_strike_type})",
            f"Delta: {ctx.greeks.delta:.2f}, Daily Theta: \u20b9{ctx.greeks.theta_day:.2f}/unit",
            f"Premium Entry: \u20b9{ctx.entry_premium:.2f}, Stop: \u20b9{ctx.stop_premium:.2f}, T1: \u20b9{ctx.target_1:.2f} (1.5R)",
        ]

    def _risk_reasons(self, ctx: SetupContext) -> list[str]:
        return [
            f"Risk/Lot: \u20b9{ctx.risk_res.premium_risk_per_lot:.0f}, Max Allocation: {ctx.risk_res.num_lots} lots",
            f"Total Outlay: \u20b9{ctx.risk_res.total_premium_outlay:.0f} ({ctx.risk_res.capital_at_risk_pct:.1f}% equity risk)",
        ]

    def _invalidation_rules(self, ctx: SetupContext) -> list[str]:
        return [
            f"Underlying spot breaching \u20b9{ctx.signal.spot_stop:.2f} invalidates setup",
            f"Option premium falling below \u20b9{ctx.stop_premium:.2f} closes trade",
            f"Holding period exceeded ({ctx.expected_holding_days} days) triggers time stop",
        ]


# Backward compatibility alias
VCPBreakoutStrategy = BreakoutOptionsStrategy
