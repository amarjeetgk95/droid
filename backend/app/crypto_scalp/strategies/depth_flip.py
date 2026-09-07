"""
Order Book Depth Flip Strategy
Detects institutional limit-order book imbalances (L2 depth dominance)
where heavy bidding or offering creates an asymmetric liquidity imbalance.
"""
from __future__ import annotations

from app.crypto_scalp.base import CryptoScalpContext, CryptoScalpCandidate
from app.models.crypto import SignalDirection


class DepthFlipStrategy:
    strategy_code = "DEPTH_FLIP"
    name = "L2 Depth Imbalance Scalp"
    entry_style = "MARKET"  # Liquidity-flip market entry at spot, not a breakout trigger

    def detect(self, ctx: CryptoScalpContext) -> CryptoScalpCandidate | None:
        if not ctx.orderbook:
            return None

        ob = ctx.orderbook
        imbalance_pct = ob.depth_imbalance_pct  # -100.0 to +100.0%
        spread_pct = ob.spread_percent

        # Strict institutional filters:
        # 1. Spread must be ultra-tight (<= 0.05%)
        if spread_pct > 0.05:
            return None

        # 2. Require volume confirmation (volume_surge_ratio >= 1.3)
        if ctx.volume_surge_ratio < 1.3:
            return None

        # 3. Must have 1m candle context
        if not ctx.candles_1m:
            return None

        curr = ctx.candles_1m[-1]
        c_range = max(0.0001, curr.high - curr.low)
        body = abs(curr.close - curr.open)
        body_ratio = body / c_range

        price = ctx.current_price
        atr = max(ctx.atr_14_1m, price * 0.001)

        direction: SignalDirection | None = None
        confluences: list[str] = []
        confidence = 72.0

        # Bullish: Heavy bid wall (>= +35% imbalance) with green candle push
        if imbalance_pct >= 35.0 and curr.close > curr.open and body_ratio >= 0.35:
            direction = SignalDirection.LONG
            confluences.append(f"Heavy L2 Bid Cushion: {imbalance_pct:+.1f}% depth imbalance")
            confluences.append(f"Volume surge {ctx.volume_surge_ratio:.1f}x with bullish candle body")
            if imbalance_pct >= 50.0:
                confluences.append("Extreme limit-bid concentration (>= 50% skew)")
                confidence += 8.0
            else:
                confidence += 4.0
            if ob.spread_percent <= 0.02:
                confluences.append("Ultra-tight spread (<= 0.02%) enables zero-slippage fill")
                confidence += 5.0
            if ctx.vwap_session and price >= ctx.vwap_session:
                confluences.append("Price positioned above session VWAP")
                confidence += 5.0

        # Bearish: Heavy ask wall (<= -35% imbalance) with red candle push
        elif imbalance_pct <= -35.0 and curr.close < curr.open and body_ratio >= 0.35:
            direction = SignalDirection.SHORT
            confluences.append(f"Heavy L2 Ask Overhead: {imbalance_pct:+.1f}% depth imbalance")
            confluences.append(f"Volume surge {ctx.volume_surge_ratio:.1f}x with bearish candle body")
            if imbalance_pct <= -50.0:
                confluences.append("Extreme limit-ask concentration (>= 50% skew)")
                confidence += 8.0
            else:
                confidence += 4.0
            if ob.spread_percent <= 0.02:
                confluences.append("Ultra-tight spread (<= 0.02%) enables zero-slippage fill")
                confidence += 5.0
            if ctx.vwap_session and price <= ctx.vwap_session:
                confluences.append("Price positioned below session VWAP")
                confidence += 5.0

        if not direction:
            return None

        entry = price
        risk = max(atr * 1.0, entry * 0.0035)
        risk = min(risk, entry * 0.007)  # max 0.7% risk

        if direction == SignalDirection.LONG:
            sl = round(entry - risk, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t1 = round(entry + risk * 1.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t2 = round(entry + risk * 2.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            rationale = (
                f"{ctx.asset} order book shows institutional bid dominance ({imbalance_pct:+.1f}% skew) "
                f"with {ctx.volume_surge_ratio:.1f}x volume confirmation toward ${t1:,.2f}."
            )
        else:
            sl = round(entry + risk, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t1 = round(entry - risk * 1.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t2 = round(entry - risk * 2.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            rationale = (
                f"{ctx.asset} order book shows institutional ask dominance ({imbalance_pct:+.1f}% skew) "
                f"with {ctx.volume_surge_ratio:.1f}x volume confirmation toward ${t1:,.2f}."
            )

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
            depth_imbalance=imbalance_pct,
        )
