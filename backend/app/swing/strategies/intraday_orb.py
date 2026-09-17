"""
Intraday Opening Range Breakout (ORB) Options Strategy (v6.1 Intraday Swing Mode).
Detects 30-minute opening range expansion on index underlyings,
selects high-gamma ATM/ITM-1 contracts with tight risk brackets,
and enforces mandatory 15:15 IST market-close square-off.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from app.swing.models import MarketRegime
from app.swing.technical import SwingFeatures
from app.swing.strategies.base import IntradaySwingStrategy, SwingSignal


class IntradayORBStrategy(IntradaySwingStrategy):
    strategy_id = "INTRADAY_ORB_CE"
    strategy_id_short = "INTRADAY_ORB_PE"
    strategy_name = "Opening Range Breakout (ORB)"

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
        if len(candles) < 4 or features.opening_range_high <= 0:
            return None

        or_high = features.opening_range_high
        or_low = features.opening_range_low
        or_range = max(10.0, or_high - or_low)

        is_bullish = spot > or_high and features.rvol >= 0.95
        is_bearish = spot < or_low and features.rvol >= 0.95

        if not (is_bullish or is_bearish):
            return None

        direction: Literal["LONG_CALL", "LONG_PUT"] = "LONG_CALL" if is_bullish else "LONG_PUT"
        atr = max(10.0, features.atr_14)
        midpoint = round((or_high + or_low) / 2.0, 2)

        if is_bullish:
            trigger = round(or_high, 2)
            # Stop at OR midpoint or 1.2 * ATR
            stop_dist = max(atr * 1.2, trigger - midpoint)
            spot_stop = round(trigger - stop_dist, 2)
        else:
            trigger = round(or_low, 2)
            stop_dist = max(atr * 1.2, midpoint - trigger)
            spot_stop = round(trigger + stop_dist, 2)
        expected_move = max(or_range * 1.5, stop_dist * 2.0)

        tech_reasons = [
            f"30-Minute Opening Range Breakout ({'Above OR High' if is_bullish else 'Below OR Low'} \u20b9{trigger:,.2f})",
            f"Opening Range: \u20b9{or_low:,.2f} - \u20b9{or_high:,.2f} (Span \u20b9{or_range:,.2f})",
            f"RVOL: {features.rvol:.2f} confirms momentum expansion",
        ]

        return SwingSignal(
            direction=direction,
            trigger=trigger,
            spot_stop=spot_stop,
            stop_dist=stop_dist,
            expected_move=expected_move,
            technical_reasons=tech_reasons,
            vwap=features.vwap or spot,
            daily_atr=round(atr, 2),
        )
