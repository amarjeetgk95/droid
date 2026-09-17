"""
Intraday Trend Pullback Options Strategy (v6.1 Intraday Swing Mode).
Detects 15M 20 EMA pullbacks aligned with intraday VWAP on index underlyings,
selects high-gamma ATM/ITM-1 options with < 5% hourly theta drag,
and sets hard 15:15 IST square-off stops.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from app.swing.models import MarketRegime
from app.swing.technical import SwingFeatures
from app.swing.strategies.base import IntradaySwingStrategy, SwingSignal


class IntradayPullbackStrategy(IntradaySwingStrategy):
    strategy_id = "INTRADAY_PULLBACK_CE"
    strategy_id_short = "INTRADAY_PULLBACK_PE"
    strategy_name = "15M VWAP Trend Pullback"

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
        if len(candles) < 10 or features.ema_20 is None:
            return None

        # VWAP and EMA alignment determine direction
        vwap = features.vwap or spot
        is_bullish = spot >= vwap and features.price_above_ema20
        is_bearish = spot < vwap and not features.price_above_ema20

        if not (is_bullish or is_bearish):
            return None

        direction: Literal["LONG_CALL", "LONG_PUT"] = "LONG_CALL" if is_bullish else "LONG_PUT"

        ema20 = features.ema_20
        dist_to_ema20 = abs(spot - ema20) / ema20
        if dist_to_ema20 > 0.015:  # Pullback within 1.5% of 20 EMA
            return None

        bar_range = max(0.01, features.high - features.low)
        atr = max(10.0, features.atr_14)

        if is_bullish:
            close_pos = (features.close - features.low) / bar_range
            if close_pos < 0.35:
                return None
            trigger = round(features.high, 2)
            structural_stop = round(min(c["low"] for c in candles[-3:]), 2)
            stop_dist = max(atr * 1.2, trigger - structural_stop)
            spot_stop = round(trigger - stop_dist, 2)
        else:
            close_pos = (features.high - features.close) / bar_range
            if close_pos < 0.35:
                return None
            trigger = round(features.low, 2)
            structural_stop = round(max(c["high"] for c in candles[-3:]), 2)
            stop_dist = max(atr * 1.2, structural_stop - trigger)
            spot_stop = round(trigger + stop_dist, 2)
        expected_move = max(atr * 2.0, stop_dist * 1.8)

        tech_reasons = [
            f"15M Trend Pullback to 20 EMA (Spot \u20b9{spot:,.2f} vs EMA \u20b9{ema20:,.2f})",
            f"VWAP Alignment: Spot is {'above' if is_bullish else 'below'} VWAP (\u20b9{vwap:,.2f})",
            f"15M ATR: \u20b9{atr:.2f}, Intraday RVOL: {features.rvol:.2f}",
        ]

        return SwingSignal(
            direction=direction,
            trigger=trigger,
            spot_stop=spot_stop,
            stop_dist=stop_dist,
            expected_move=expected_move,
            technical_reasons=tech_reasons,
            vwap=vwap,
            daily_atr=round(atr, 2),
        )
