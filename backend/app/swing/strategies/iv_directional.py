"""
IV Directional Normalization Strategy (v6.0 Options Overhaul).
Rule: Long-only option buying when:
  1. IV is Low/Normal (iv_percentile <= 60.0) -> Volatility is mispriced / cheap.
  2. Clear underlying technical directional trend exists (MA alignment).
  3. Expected realized move exceeds implied option move (iv_edge >= 1.0).
Strictly Long-Only: No naked selling or premium decay plays (§11).
Strategy: IV_DIRECTIONAL.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from app.swing.models import MarketRegime
from app.swing.technical import SwingFeatures
from app.swing.strategies.base import BaseSwingStrategy, SetupContext, SwingSignal


class IVDirectionalStrategy(BaseSwingStrategy):
    strategy_id = "IV_DIRECTIONAL"
    strategy_name = "IV Directional Edge"

    candidate_types = ["ITM_1", "ATM"]
    max_theta_drag_ratio = 20.0

    theta_drag_default = 12.0
    dte_fallback = 10
    iv_edge_min = 1.0
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
        if len(candles) < 30:
            return None

        # §11: Only enter long options when IV is favorable (<= 60th percentile)
        if iv_percentile > 60.0:
            return None

        # Determine directional bias: Price vs 20 EMA and 50 SMA
        if features.price_above_ema20 and features.price_above_sma50:
            direction: Literal["LONG_CALL", "LONG_PUT"] = "LONG_CALL"
            trigger = features.close
            stop_dist = max(features.atr_14 * 1.2, trigger - (features.ema_20 or trigger * 0.98))
            spot_stop = round(trigger - stop_dist, 2)
            expected_move = max(features.atr_14 * 3.0, stop_dist * 2.5)
        elif not features.price_above_ema20 and not features.price_above_sma50:
            direction = "LONG_PUT"
            trigger = features.close
            stop_dist = max(features.atr_14 * 1.2, (features.ema_20 or trigger * 1.02) - trigger)
            spot_stop = round(trigger + stop_dist, 2)
            expected_move = max(features.atr_14 * 3.0, stop_dist * 2.5)
        else:
            # Choppy / no clear directional edge
            return None

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
            f"Underlying in clear {signal.direction.replace('_', ' ')} trend (MA alignment)",
            f"Expected move (+{signal.expected_move:.1f} pts) exceeds option implied move by {ctx.iv_edge:.2f}x",
            f"Trigger at \u20b9{signal.trigger:.2f}, Invalidation Stop at \u20b9{signal.spot_stop:.2f}",
        ]

    def _options_reasons(self, ctx: SetupContext) -> list[str]:
        return [
            f"Low/Normal IV environment: IV Rank {ctx.iv_percentile:.1f}% ({ctx.regime.iv_regime})",
            f"Contract: {ctx.contract_symbol} ({ctx.selection.selected_strike_type})",
            f"Delta: {ctx.greeks.delta:.2f}, Premium Entry: \u20b9{ctx.entry_premium:.2f}, Stop: \u20b9{ctx.stop_premium:.2f}",
        ]

    def _risk_reasons(self, ctx: SetupContext) -> list[str]:
        return [
            f"Risk/Lot: \u20b9{ctx.risk_res.premium_risk_per_lot:.0f}, Max Allocation: {ctx.risk_res.num_lots} lots",
            f"Total Outlay: \u20b9{ctx.risk_res.total_premium_outlay:.0f} ({ctx.risk_res.capital_at_risk_pct:.1f}% equity risk)",
        ]
