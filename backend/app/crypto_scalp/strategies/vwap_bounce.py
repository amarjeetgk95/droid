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
    entry_style = "MARKET"  # Mean-reversion market entry at spot, not a breakout trigger

    def detect(self, ctx: CryptoScalpContext) -> CryptoScalpCandidate | None:
        if not ctx.candles_1m or len(ctx.candles_1m) < 5 or ctx.vwap_session <= 0:
            return None

        current_candle = ctx.candles_1m[-1]
        prev_candle = ctx.candles_1m[-2]
        vwap = ctx.vwap_session
        price = ctx.current_price
        atr = max(ctx.atr_14_1m, price * 0.001)

        # Require minimum volume confirmation to avoid flat market whipsaws
        if ctx.volume_surge_ratio < 1.5:
            return None

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
        confidence = 78.0

        # 1. BULLISH BOUNCE: Price tested VWAP from above or pierced and closed back above
        # Low tested near/below VWAP, reclaimed VWAP on close, green candle with prominent lower wick
        if (
            current_candle.low <= vwap * 1.0005
            and current_candle.close > vwap
            and current_candle.close > current_candle.open
            and lower_wick_ratio >= 0.40
        ):
            direction = SignalDirection.LONG
            risk = max(atr * 1.0, (entry - min(current_candle.low, vwap * 0.998)))
            risk = min(risk, entry * 0.007)
            sl = round(entry - risk, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t1 = round(entry + risk * 1.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t2 = round(entry + risk * 2.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)

            confluences.append(f"VWAP support confirmed with {lower_wick_ratio * 100:.0f}% lower rejection wick")
            confluences.append(f"Volume surge {ctx.volume_surge_ratio:.1f}x avg")
            if ctx.orderbook and ctx.orderbook.depth_imbalance_pct > 15.0:
                confluences.append(f"Order book bid-skewed ({ctx.orderbook.depth_imbalance_pct:+.1f}%)")
                confidence += 7.0
            if ctx.ema_9_1m > ctx.ema_21_1m and ctx.ema_21_1m > ctx.ema_50_1m:
                confluences.append("Full EMA bullish stack EMA9 > EMA21 > EMA50")
                confidence += 8.0
            elif ctx.ema_9_1m > ctx.ema_21_1m:
                confluences.append("Short-term EMA9 > EMA21 aligned bullish")
                confidence += 4.0

            rationale = (
                f"{ctx.asset} tested session VWAP (${vwap:,.2f}) and formed a bullish rejection wick. "
                f"Price reclaimed VWAP with {confidence:.0f}% confidence and {ctx.volume_surge_ratio:.1f}x volume."
            )

        # 2. BEARISH REJECTION: Price tested VWAP from below and got rejected
        # High tested near/above VWAP, rejected below VWAP on close, red candle with prominent upper wick
        elif (
            current_candle.high >= vwap * 0.9995
            and current_candle.close < vwap
            and current_candle.close < current_candle.open
            and upper_wick_ratio >= 0.40
        ):
            direction = SignalDirection.SHORT
            risk = max(atr * 1.0, (max(current_candle.high, vwap * 1.002) - entry))
            risk = min(risk, entry * 0.007)
            sl = round(entry + risk, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t1 = round(entry - risk * 1.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t2 = round(entry - risk * 2.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)

            confluences.append(f"VWAP resistance confirmed with {upper_wick_ratio * 100:.0f}% upper rejection wick")
            confluences.append(f"Volume surge {ctx.volume_surge_ratio:.1f}x avg")
            if ctx.orderbook and ctx.orderbook.depth_imbalance_pct < -15.0:
                confluences.append(f"Order book ask-skewed ({ctx.orderbook.depth_imbalance_pct:+.1f}%)")
                confidence += 7.0
            if ctx.ema_9_1m < ctx.ema_21_1m and ctx.ema_21_1m < ctx.ema_50_1m:
                confluences.append("Full EMA bearish stack EMA9 < EMA21 < EMA50")
                confidence += 8.0
            elif ctx.ema_9_1m < ctx.ema_21_1m:
                confluences.append("Short-term EMA9 < EMA21 aligned bearish")
                confidence += 4.0

            rationale = (
                f"{ctx.asset} attempted to breach session VWAP (${vwap:,.2f}) and failed with an upper rejection wick. "
                f"Sellers defended VWAP ceiling with {confidence:.0f}% confidence and {ctx.volume_surge_ratio:.1f}x volume."
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
            depth_imbalance=ctx.orderbook.depth_imbalance_pct if ctx.orderbook else None,
        )
