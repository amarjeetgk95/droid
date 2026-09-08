"""
EMA Cross Micro-Scalp Strategy
Detects 9 EMA / 21 EMA crosses and pullbacks on 1m candles with volume momentum.
"""
from __future__ import annotations

from app.crypto_scalp.base import CryptoScalpContext, CryptoScalpCandidate, calc_ema
from app.models.crypto import SignalDirection


class EMACrossScalpStrategy:
    strategy_code = "EMA_CROSS_SCALP"
    name = "EMA Cross Micro-Scalp"
    entry_style = "MARKET"  # Momentum market entry at spot, not a breakout trigger

    def detect(self, ctx: CryptoScalpContext) -> CryptoScalpCandidate | None:
        if not ctx.candles_1m or len(ctx.candles_1m) < 25:
            return None

        # Extract close price series
        closes = [c.close for c in ctx.candles_1m]
        prev_closes = closes[:-1]

        # Current EMAs
        ema_9_now = ctx.ema_9_1m or calc_ema(closes, 9)
        ema_21_now = ctx.ema_21_1m or calc_ema(closes, 21)
        ema_50_now = ctx.ema_50_1m or calc_ema(closes, 50)

        # Previous bar EMAs to detect the exact crossover
        ema_9_prev = calc_ema(prev_closes, 9)
        ema_21_prev = calc_ema(prev_closes, 21)

        price = ctx.current_price
        atr = max(ctx.atr_14_1m, price * 0.001)

        direction: SignalDirection | None = None
        confluences: list[str] = []
        confidence = 78.0

        # Volume surge must confirm the EMA momentum or pullback
        if ctx.volume_surge_ratio < 1.5:
            return None

        # Bullish Crossover: EMA 9 crosses above EMA 21
        bullish_cross = ema_9_prev <= ema_21_prev and ema_9_now > ema_21_now
        # Bullish Pullback Bounce: EMA 9 > EMA 21, low touched EMA 21 and rebounded
        bullish_pullback = (
            ema_9_now > ema_21_now
            and ctx.candles_1m[-1].low <= ema_21_now * 1.001
            and ctx.candles_1m[-1].close > ema_21_now
            and ctx.candles_1m[-1].close > ctx.candles_1m[-1].open
        )

        # Bearish Crossover: EMA 9 crosses below EMA 21
        bearish_cross = ema_9_prev >= ema_21_prev and ema_9_now < ema_21_now
        # Bearish Pullback Rejection: EMA 9 < EMA 21, high touched EMA 21 and got rejected
        bearish_pullback = (
            ema_9_now < ema_21_now
            and ctx.candles_1m[-1].high >= ema_21_now * 0.999
            and ctx.candles_1m[-1].close < ema_21_now
            and ctx.candles_1m[-1].close < ctx.candles_1m[-1].open
        )

        entry = price
        sl = 0.0
        t1 = 0.0
        t2 = 0.0
        rationale = ""

        if bullish_cross or bullish_pullback:
            direction = SignalDirection.LONG
            risk = max(atr * 1.0, entry - min(ema_21_now, ctx.candles_1m[-1].low))
            risk = min(risk, entry * 0.007)  # max 0.7% scalp risk
            sl = round(entry - risk, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t1 = round(entry + risk * 1.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t2 = round(entry + risk * 2.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)

            trigger_type = "Bullish EMA 9/21 cross" if bullish_cross else "EMA 21 dynamic support pullback"
            confluences.append(trigger_type)
            confluences.append(f"Volume surge {ctx.volume_surge_ratio:.1f}x")

            if ctx.ema_50_1m > 0 and price > ctx.ema_50_1m:
                confluences.append("Trend alignment: Price > EMA 50")
                confidence += 8.0
            if ctx.orderbook and ctx.orderbook.depth_imbalance_pct > 15.0:
                confluences.append("Bid-side L2 depth dominant")
                confidence += 5.0

            rationale = (
                f"{ctx.asset} triggered {trigger_type} on 1m chart with {ctx.volume_surge_ratio:.1f}x volume. "
                f"Momentum favors upside continuation toward ${t1:,.2f}."
            )

        elif bearish_cross or bearish_pullback:
            direction = SignalDirection.SHORT
            risk = max(atr * 1.0, max(ema_21_now, ctx.candles_1m[-1].high) - entry)
            risk = min(risk, entry * 0.007)
            sl = round(entry + risk, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t1 = round(entry - risk * 1.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t2 = round(entry - risk * 2.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)

            trigger_type = "Bearish EMA 9/21 cross" if bearish_cross else "EMA 21 dynamic resistance rejection"
            confluences.append(trigger_type)
            confluences.append(f"Volume surge {ctx.volume_surge_ratio:.1f}x")

            if ctx.ema_50_1m > 0 and price < ctx.ema_50_1m:
                confluences.append("Trend alignment: Price < EMA 50")
                confidence += 8.0
            if ctx.orderbook and ctx.orderbook.depth_imbalance_pct < -15.0:
                confluences.append("Ask-side L2 depth dominant")
                confidence += 5.0

            rationale = (
                f"{ctx.asset} triggered {trigger_type} on 1m chart with {ctx.volume_surge_ratio:.1f}x volume. "
                f"Downward momentum favors scalping short toward ${t1:,.2f}."
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
