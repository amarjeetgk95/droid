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

    def detect(self, ctx: CryptoScalpContext) -> CryptoScalpCandidate | None:
        if not ctx.orderbook:
            return None

        ob = ctx.orderbook
        imbalance = ob.depth_imbalance  # -1.0 to +1.0
        imbalance_pct = ob.depth_imbalance_pct
        spread_pct = ob.spread_percent

        # Only evaluate if spread is tight (< 0.08%) so execution is viable
        if spread_pct > 0.08:
            return None

        price = ctx.current_price
        atr = max(ctx.atr_14_1m, price * 0.001)

        direction: SignalDirection | None = None
        confluences: list[str] = []
        confidence = 70.0

        # Bullish: Strong bid wall / bid depth dominance (>= +20% imbalance)
        if imbalance >= 0.20:
            # Confirm price is holding or pushing up
            if not ctx.candles_1m or ctx.candles_1m[-1].close >= ctx.candles_1m[-1].low:
                direction = SignalDirection.LONG
                confluences.append(f"Heavy L2 Bid Cushion: {imbalance_pct:+.1f}% depth imbalance")
                if imbalance >= 0.40:
                    confluences.append("Extreme limit-bid concentration (>= 40% skew)")
                    confidence += 10.0
                else:
                    confidence += 5.0
                if ob.spread_percent <= 0.02:
                    confluences.append("Ultra-tight spread (<= 0.02%) enables zero-slippage fill")
                    confidence += 5.0
                if ctx.vwap_session and price >= ctx.vwap_session:
                    confluences.append("Price positioned above VWAP")
                    confidence += 5.0

        # Bearish: Strong ask wall / ask depth dominance (<= -20% imbalance)
        elif imbalance <= -0.20:
            if not ctx.candles_1m or ctx.candles_1m[-1].close <= ctx.candles_1m[-1].high:
                direction = SignalDirection.SHORT
                confluences.append(f"Heavy L2 Ask Overhead: {imbalance_pct:+.1f}% depth imbalance")
                if imbalance <= -0.40:
                    confluences.append("Extreme limit-ask concentration (>= 40% skew)")
                    confidence += 10.0
                else:
                    confidence += 5.0
                if ob.spread_percent <= 0.02:
                    confluences.append("Ultra-tight spread (<= 0.02%) enables zero-slippage fill")
                    confidence += 5.0
                if ctx.vwap_session and price <= ctx.vwap_session:
                    confluences.append("Price positioned below VWAP")
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
                f"{ctx.asset} order book is heavily bid-dominated ({imbalance_pct:+.1f}% skew). "
                f"Thin ask book provides low resistance toward ${t1:,.2f}."
            )
        else:
            sl = round(entry + risk, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t1 = round(entry - risk * 1.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t2 = round(entry - risk * 2.5, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            rationale = (
                f"{ctx.asset} order book is heavily ask-dominated ({imbalance_pct:+.1f}% skew). "
                f"Lack of bid support enables downside scalping toward ${t1:,.2f}."
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
            depth_imbalance=imbalance,
        )
