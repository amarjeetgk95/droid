"""
Funding Rate Squeeze Strategy
Detects asymmetric leverage positioning where negative funding rate triggers short squeezes,
or extreme positive funding rate triggers long liquidation cascades.
"""
from __future__ import annotations

from app.crypto_scalp.base import CryptoScalpContext, CryptoScalpCandidate
from app.models.crypto import SignalDirection


class FundingSqueezeStrategy:
    strategy_code = "FUNDING_SQUEEZE"
    name = "Perpetual Funding Squeeze"

    def detect(self, ctx: CryptoScalpContext) -> CryptoScalpCandidate | None:
        if not ctx.derivatives:
            return None

        derivs = ctx.derivatives
        funding_rate = derivs.funding_rate  # e.g. -0.0001 (-0.01%) or 0.0003 (+0.03%)
        funding_pct = derivs.funding_rate_percent
        ls_ratio = derivs.long_short_ratio
        price = ctx.current_price
        atr = max(ctx.atr_14_1m, price * 0.001)

        direction: SignalDirection | None = None
        confluences: list[str] = []
        confidence = 74.0

        # Case 1: SHORT SQUEEZE OPPORTUNITY (Long signal)
        # Funding is negative or heavily compressed + market pushing upwards
        if funding_rate <= -0.00005 or (funding_rate < 0 and ls_ratio < 0.95):
            # Price action confirmation: 1m candle green or price > session vwap
            if ctx.candles_1m and ctx.candles_1m[-1].close >= ctx.candles_1m[-1].open:
                direction = SignalDirection.LONG
                confluences.append(f"Negative funding rate ({funding_pct:+.4f}%) penalizing shorts")
                if ls_ratio < 0.85:
                    confluences.append(f"Heavily short-skewed L/S ratio ({ls_ratio:.2f})")
                    confidence += 8.0
                if derivs.open_interest_usd > 1_000_000:
                    confluences.append("Elevated Open Interest (OI) fuel for squeeze")
                    confidence += 6.0
                if ctx.orderbook and ctx.orderbook.depth_imbalance > 0.05:
                    confluences.append("Spot depth supporting squeeze breakout")
                    confidence += 5.0

        # Case 2: LONG LIQUIDATION FLUSH (Short signal)
        # Funding is excessively positive (overleveraged longs) + market turning downward
        elif funding_rate >= 0.00025 or (funding_rate > 0.00015 and ls_ratio > 1.80):
            # Price action confirmation: 1m candle red or price < session vwap
            if ctx.candles_1m and ctx.candles_1m[-1].close <= ctx.candles_1m[-1].open:
                direction = SignalDirection.SHORT
                confluences.append(f"Elevated positive funding ({funding_pct:+.4f}%) - longs overstretched")
                if ls_ratio > 1.80:
                    confluences.append(f"Crowded long positioning ({ls_ratio:.2f} L/S)")
                    confidence += 8.0
                if derivs.open_interest_usd > 1_000_000:
                    confluences.append("High OI vulnerable to cascading stop runs")
                    confidence += 6.0
                if ctx.orderbook and ctx.orderbook.depth_imbalance < -0.05:
                    confluences.append("Spot depth reflecting sell-side pressure")
                    confidence += 5.0

        if not direction:
            return None

        entry = price
        risk = max(atr * 1.2, entry * 0.004)
        risk = min(risk, entry * 0.009)  # Cap scalp risk at 0.9%

        if direction == SignalDirection.LONG:
            sl = round(entry - risk, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t1 = round(entry + risk * 1.6, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t2 = round(entry + risk * 2.8, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            rationale = (
                f"{ctx.asset} perp funding ({funding_pct:+.4f}%) indicates crowded short exposure. "
                f"Anticipating short liquidation wick squeeze toward ${t1:,.2f}."
            )
        else:
            sl = round(entry + risk, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t1 = round(entry - risk * 1.6, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            t2 = round(entry - risk * 2.8, 2 if "USDT" in ctx.symbol and price > 100 else 4)
            rationale = (
                f"{ctx.asset} funding rate ({funding_pct:+.4f}%) shows overleveraged long imbalance. "
                f"Anticipating liquidation cascade flush toward ${t1:,.2f}."
            )

        risk_pts = abs(entry - sl)
        risk_pct = (risk_pts / entry) * 100.0
        rr = abs(t1 - entry) / risk_pts if risk_pts > 0 else 1.6

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
            funding_rate=funding_rate,
            depth_imbalance=ctx.orderbook.depth_imbalance if ctx.orderbook else None,
        )
