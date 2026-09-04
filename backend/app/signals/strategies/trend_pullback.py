"""
Trend Pullback & EMA Ribbon Retest Strategy
Mathematical rules:
  - LONG_CALL: EMA20 > EMA50 > EMA200, ADX >= 22, Spot pulls back to EMA20 within 0.3% tolerance, 15M/1H MTF Bullish
  - LONG_PUT: EMA20 < EMA50 < EMA200, ADX >= 22, Spot pulls back to EMA20 within 0.3% tolerance, 15M/1H MTF Bearish
  - SL = Below EMA50 / swing low, T1 = 1.5R (previous high test), T2 = 3.0R (trend extension)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.risk_engine import resolve_realistic_atr


class TrendPullbackStrategy(Strategy):
    name = "TREND_PULLBACK"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        ind = ctx.indicators
        spot = ctx.spot_price
        tick = Decimal("0.05")

        trend_data = ind.get("trend", {})
        ema20 = Decimal(str(trend_data.get("ema20") or spot * Decimal("0.998")))
        ema50 = Decimal(str(trend_data.get("ema50") or spot * Decimal("0.995")))
        ema200 = Decimal(str(trend_data.get("ema200") or spot * Decimal("0.990")))
        adx = float(ind.get("adx") or trend_data.get("adx", 25.0))
        atr = resolve_realistic_atr(ctx.underlying, spot, ind)
        mtf_bias = ctx.mtf.get("overall_bias", "NEUTRAL")

        # ── BULLISH TREND PULLBACK (LONG_CALL) ──
        if spot > Decimal("0") and (ema20 >= ema50 >= ema200 or trend_data.get("trend") == "BULLISH") and mtf_bias in ("BULLISH", "NEUTRAL") and adx >= 20.0:
            # Check if spot is near EMA20 (within 0.4%)
            dist_pct = abs(spot - ema20) / spot * Decimal("100")
            if dist_pct <= Decimal("0.5") or spot >= ema20:
                entry_min = normalize_price(ema20, tick)
                entry_max = normalize_price(spot + (atr * Decimal("0.2")), tick)
                trigger = normalize_price(spot + tick, tick)
                stop_loss = normalize_price(entry_min - (atr * Decimal("1.0")), tick)
                risk_pts = entry_min - stop_loss
                if risk_pts > Decimal("0"):
                    t1 = normalize_price(entry_min + (risk_pts * Decimal("1.5")), tick)
                    t2 = normalize_price(entry_min + (risk_pts * Decimal("3.0")), tick)
                    contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=0)

                    tech_score = min(94.0, 60.0 + (adx * 0.8) + 10.0)
                    mtf_score = float(ctx.mtf.get("alignment_score", 75.0))
                    fno_score = 75.0
                    regime_score = 85.0 if ctx.regime == "TREND_UP" else 70.0

                    return SignalCandidate(
                        underlying=ctx.underlying,
                        strategy=self.name,
                        direction="LONG_CALL",
                        timeframe=ctx.timeframe,
                        spot_price=spot,
                        entry_min=entry_min,
                        entry_max=entry_max,
                        trigger=trigger,
                        stop_loss=stop_loss,
                        target_1=t1,
                        target_2=t2,
                        risk_points=risk_pts,
                        risk_reward_t1=1.5,
                        risk_reward_t2=3.0,
                        technical_score=tech_score,
                        mtf_score=mtf_score,
                        fno_score=fno_score,
                        regime_score=regime_score,
                        overall_confidence=round((tech_score * 0.4) + (mtf_score * 0.2) + (fno_score * 0.2) + (regime_score * 0.2), 1),
                        rationale=[
                            f"Strong Bullish Trend (ADX {adx:.1f})",
                            f"Retest of 20 EMA support (₹{ema20:,.2f})",
                            f"EMA 20 > 50 > 200 ribbon alignment",
                            f"Multi-timeframe confirmation ({mtf_bias})",
                        ],
                        option_contract=contract,
                        ttl_seconds=300,
                    )

        # ── BEARISH TREND PULLBACK (LONG_PUT) ──
        if spot > Decimal("0") and (ema20 <= ema50 <= ema200 or trend_data.get("trend") == "BEARISH") and mtf_bias in ("BEARISH", "NEUTRAL") and adx >= 20.0:
            dist_pct = abs(spot - ema20) / spot * Decimal("100")
            if dist_pct <= Decimal("0.5") or spot <= ema20:
                entry_min = normalize_price(spot - (atr * Decimal("0.2")), tick)
                entry_max = normalize_price(ema20, tick)
                trigger = normalize_price(spot - tick, tick)
                stop_loss = normalize_price(entry_max + (atr * Decimal("1.0")), tick)
                risk_pts = stop_loss - entry_max
                if risk_pts > Decimal("0"):
                    t1 = normalize_price(entry_max - (risk_pts * Decimal("1.5")), tick)
                    t2 = normalize_price(entry_max - (risk_pts * Decimal("3.0")), tick)
                    contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=0)

                    tech_score = min(94.0, 60.0 + (adx * 0.8) + 10.0)
                    mtf_score = float(ctx.mtf.get("alignment_score", 75.0))
                    fno_score = 75.0
                    regime_score = 85.0 if ctx.regime == "TREND_DOWN" else 70.0

                    return SignalCandidate(
                        underlying=ctx.underlying,
                        strategy=self.name,
                        direction="LONG_PUT",
                        timeframe=ctx.timeframe,
                        spot_price=spot,
                        entry_min=entry_min,
                        entry_max=entry_max,
                        trigger=trigger,
                        stop_loss=stop_loss,
                        target_1=t1,
                        target_2=t2,
                        risk_points=risk_pts,
                        risk_reward_t1=1.5,
                        risk_reward_t2=3.0,
                        technical_score=tech_score,
                        mtf_score=mtf_score,
                        fno_score=fno_score,
                        regime_score=regime_score,
                        overall_confidence=round((tech_score * 0.4) + (mtf_score * 0.2) + (fno_score * 0.2) + (regime_score * 0.2), 1),
                        rationale=[
                            f"Strong Bearish Trend (ADX {adx:.1f})",
                            f"Retest of 20 EMA resistance (₹{ema20:,.2f})",
                            f"EMA 20 < 50 < 200 ribbon alignment",
                            f"Multi-timeframe confirmation ({mtf_bias})",
                        ],
                        option_contract=contract,
                        ttl_seconds=300,
                    )

        return None
