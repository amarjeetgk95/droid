"""
Volume Breakout Scalp Strategy
Detects explosive momentum when 1m candles breach recent 15-minute highs or lows
with confirmed volume surge (>= 1.5x 20-bar volume average).
"""
from __future__ import annotations

from app.crypto_scalp.base import CryptoScalpContext, CryptoScalpCandidate
from app.models.crypto import SignalDirection


class BreakoutVolumeStrategy:
    strategy_code = "BREAKOUT_VOLUME"
    name = "Volume Breakout Scalp"

    def detect(self, ctx: CryptoScalpContext) -> CryptoScalpCandidate | None:
        if not ctx.candles_1m or len(ctx.candles_1m) < 15:
            return None

        # Determine 15m high and low from either ctx or previous 15 candles
        candles_window = ctx.candles_1m[-16:-1] if len(ctx.candles_1m) >= 16 else ctx.candles_1m[:-1]
        if not candles_window:
            return None

        recent_high = ctx.high_15m or max(c.high for c in candles_window)
        recent_low = ctx.low_15m or min(c.low for c in candles_window)

        curr = ctx.candles_1m[-1]
        price = ctx.current_price
        atr = max(ctx.atr_14_1m, price * 0.001)

        candle_range = max(0.0001, curr.high - curr.low)
        body = abs(curr.close - curr.open)
        body_ratio = body / candle_range

        direction: SignalDirection | None = None
        confluences: list[str] = []
        confidence = 72.0

        # Bullish Breakout: 1m bar closes above recent 15m high with volume expansion
        bullish_break = (
            curr.close > recent_high
            and curr.close > curr.open
            and body_ratio >= 0.55
            and ctx.volume_surge_ratio >= 1.5
        )

        # Bearish Breakdown: 1m bar closes below recent 15m low with volume expansion
        bearish_break = (
            curr.close < recent_low
            and curr.close < curr.open
            and body_ratio >= 0.55
            and ctx.volume_surge_ratio >= 1.5
        )

        entry = price
        sl = 0.0
        t1 = 0.0
        t2 = 0.0
        rationale = ""

        if bullish_break:
            direction = SignalDirection.LONG
            risk = max(atr * 1.0, entry - curr.low)
            risk = min(risk, entry * 0.008)  # max 0.8% risk
            sl = round(entry - risk, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t1 = round(entry + risk * 1.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t2 = round(entry + risk * 2.8, 2 if "USDT" in ctx.symbol and price > 100 else 4)

            confluences.append(f"Clean breach of 15m resistance (${recent_high:,.2f})")
            confluences.append(f"Volume surge {ctx.volume_surge_ratio:.1f}x above average")
            if ctx.volume_surge_ratio >= 2.0:
                confidence += 10.0
            else:
                confidence += 5.0
            if ctx.orderbook and ctx.orderbook.depth_imbalance_pct > 15.0:
                confluences.append("Depth liquidity absorption favoring buyers")
                confidence += 5.0

            rationale = (
                f"{ctx.asset} pierced 15m resistance (${recent_high:,.2f}) with {ctx.volume_surge_ratio:.1f}x volume. "
                f"Breakout expansion underway targeting ${t1:,.2f}."
            )

        elif bearish_break:
            direction = SignalDirection.SHORT
            risk = max(atr * 1.0, curr.high - entry)
            risk = min(risk, entry * 0.008)
            sl = round(entry + risk, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t1 = round(entry - risk * 1.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t2 = round(entry - risk * 2.8, 2 if "USDT" in ctx.symbol and price > 100 else 4)

            confluences.append(f"Clean breach of 15m support (${recent_low:,.2f})")
            confluences.append(f"Volume surge {ctx.volume_surge_ratio:.1f}x above average")
            if ctx.volume_surge_ratio >= 2.0:
                confidence += 10.0
            else:
                confidence += 5.0
            if ctx.orderbook and ctx.orderbook.depth_imbalance_pct < -15.0:
                confluences.append("Depth liquidity absorption favoring sellers")
                confidence += 5.0

            rationale = (
                f"{ctx.asset} cracked below 15m support (${recent_low:,.2f}) with {ctx.volume_surge_ratio:.1f}x volume. "
                f"Breakdown continuation targeting ${t1:,.2f}."
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
