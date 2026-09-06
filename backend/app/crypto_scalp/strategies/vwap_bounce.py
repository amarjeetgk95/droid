"""
VWAP Bounce Scalp Strategy
Detects mean-reversion rejections and bounces off the Volume-Weighted Average Price (VWAP).
Operates primarily on 1m and 5m candles.
"""
from __future__ import annotations

from app.crypto_scalp.base import CryptoScalpContext, CryptoScalpCandidate
from app.models.crypto import SignalDirection


class VWAPBounceStrategy:
    strategy_code = "VWAP_BOUNCE"
    name = "VWAP Rejection Bounce"

    def detect(self, ctx: CryptoScalpContext) -> CryptoScalpCandidate | None:
        if not ctx.candles_1m or len(ctx.candles_1m) < 5 or ctx.vwap_session <= 0:
            return None

        current_candle = ctx.candles_1m[-1]
        prev_candle = ctx.candles_1m[-2]
        vwap = ctx.vwap_session
        price = ctx.current_price
        atr = max(ctx.atr_14_1m, price * 0.001)

        # Distance to VWAP as percentage
        dist_pct = (price - vwap) / vwap * 100.0

        # Candle anatomy
        c_range = max(0.0001, current_candle.high - current_candle.low)
        lower_wick = min(current_candle.open, current_candle.close) - current_candle.low
        upper_wick = current_candle.high - max(current_candle.open, current_candle.close)
        lower_wick_ratio = lower_wick / c_range
        upper_wick_ratio = upper_wick / c_range

        confluences: list[str] = []
        direction: SignalDirection | None = None
        entry = price
        sl = 0.0
        t1 = 0.0
        t2 = 0.0
        confidence = 70.0

        # 1. BULLISH BOUNCE: Price tested VWAP from above or pierced and closed back above
        # Low was near or below VWAP, but close is above VWAP with lower wick rejection
        if (
            current_candle.low <= vwap * 1.0015
            and current_candle.close >= vwap
            and (lower_wick_ratio >= 0.35 or current_candle.close > current_candle.open)
        ):
            direction = SignalDirection.LONG
            risk = max(atr * 1.0, (entry - min(current_candle.low, vwap * 0.998)))
            # Max 0.8% risk for scalp
            risk = min(risk, entry * 0.008)
            sl = round(entry - risk, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t1 = round(entry + risk * 1.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t2 = round(entry + risk * 2.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)

            confluences.append("VWAP support confirmed with lower rejection wick")
            if ctx.volume_surge_ratio >= 1.2:
                confluences.append(f"Volume surge {ctx.volume_surge_ratio:.1f}x avg")
                confidence += 8.0
            if ctx.orderbook and ctx.orderbook.depth_imbalance > 0.1:
                confluences.append(f"Order book bid-skewed ({ctx.orderbook.depth_imbalance_pct:+.1f}%)")
                confidence += 7.0
            if ctx.ema_9_1m > ctx.ema_21_1m:
                confluences.append("Short-term EMA9 > EMA21 aligned bullish")
                confidence += 5.0

            rationale = (
                f"{ctx.asset} tested session VWAP (${vwap:,.2f}) and formed a bullish rejection wick. "
                f"Price reclaimed VWAP with {confidence:.0f}% confidence."
            )

        # 2. BEARISH REJECTION: Price tested VWAP from below and got rejected
        elif (
            current_candle.high >= vwap * 0.9985
            and current_candle.close <= vwap
            and (upper_wick_ratio >= 0.35 or current_candle.close < current_candle.open)
        ):
            direction = SignalDirection.SHORT
            risk = max(atr * 1.0, (max(current_candle.high, vwap * 1.002) - entry))
            risk = min(risk, entry * 0.008)
            sl = round(entry + risk, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t1 = round(entry - risk * 1.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t2 = round(entry - risk * 2.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)

            confluences.append("VWAP resistance confirmed with upper rejection wick")
            if ctx.volume_surge_ratio >= 1.2:
                confluences.append(f"Volume surge {ctx.volume_surge_ratio:.1f}x avg")
                confidence += 8.0
            if ctx.orderbook and ctx.orderbook.depth_imbalance < -0.1:
                confluences.append(f"Order book ask-skewed ({ctx.orderbook.depth_imbalance_pct:+.1f}%)")
                confidence += 7.0
            if ctx.ema_9_1m < ctx.ema_21_1m:
                confluences.append("Short-term EMA9 < EMA21 aligned bearish")
                confidence += 5.0

            rationale = (
                f"{ctx.asset} attempted to breach session VWAP (${vwap:,.2f}) and failed with an upper rejection wick. "
                f"Sellers defended VWAP ceiling with {confidence:.0f}% confidence."
            )

        if not direction or sl <= 0 or t1 <= 0:
            return None

        risk_pts = abs(entry - sl)
        risk_pct = (risk_pts / entry) * 100.0
        rr = abs(t1 - entry) / risk_pts if risk_pts > 0 else 1.5

        return CryptoScalpCandidate(
            symbol=ctx.symbol,
            asset=ctx.asset,
            direction=direction,
            strategy=self.strategy_code,
            strategy_name=self.name,
            entry_price=entry,
            stop_loss=sl,
            target_1=t1,
            target_2=t2,
            risk_points=round(risk_pts, 2),
            risk_percent=round(risk_pct, 2),
            risk_reward_ratio=round(rr, 2),
            confidence=min(95.0, confidence),
            timeframe="1m",
            confluence_factors=confluences,
            rationale=rationale,
            atr_value=atr,
            volume_ratio=ctx.volume_surge_ratio,
            depth_imbalance=ctx.orderbook.depth_imbalance if ctx.orderbook else None,
        )
