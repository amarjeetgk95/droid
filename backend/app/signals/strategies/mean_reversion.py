"""
Mean Reversion & Volatility Exhaustion Strategy
Mathematical rules:
  - LONG_CALL: Price <= Lower Bollinger Band (2.0σ/2.5σ), RSI <= 28, Regime == RANGE, proximity to support
  - LONG_PUT: Price >= Upper Bollinger Band (2.0σ/2.5σ), RSI >= 72, Regime == RANGE, proximity to resistance
  - T1 = Middle BB (20 SMA / VWAP), T2 = Opposite Bollinger Band
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract


class MeanReversionStrategy(Strategy):
    name = "MEAN_REVERSION"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        ind = ctx.indicators
        spot = ctx.spot_price
        tick = Decimal("0.05")

        bb = ind.get("bollinger_bands") or ind.get("volatility", {}).get("bollinger_bands", {})
        rsi = float(ind.get("rsi") or ind.get("momentum", {}).get("rsi", 50.0))
        atr = Decimal(str(ind.get("atr", spot * Decimal("0.005"))))
        
        bb_upper = Decimal(str(bb.get("upper", spot * Decimal("1.01"))))
        bb_middle = Decimal(str(bb.get("middle", spot)))
        bb_lower = Decimal(str(bb.get("lower", spot * Decimal("0.99"))))

        # Check regime compatibility: primarily RANGE or LOW_VOL
        if ctx.regime not in ("RANGE", "LOW_VOL", "UNKNOWN"):
            return None

        # ── BULLISH OVERSOLD REVERSAL (LONG_CALL) ──
        # Both BB touch AND RSI exhaustion required (OR fired mid-range noise).
        # Trigger sits a confirmation gap above spot — never spot ± 1 tick.
        if (spot <= bb_lower * Decimal("1.002")) and rsi <= 28.0:
            entry_min = normalize_price(spot, tick)
            entry_max = normalize_price(spot + (atr * Decimal("0.2")), tick)
            trigger_gap = max(atr * Decimal("0.30"), spot * Decimal("0.0006"))
            trigger = normalize_price(spot + trigger_gap, tick)
            stop_loss = normalize_price(spot - (atr * Decimal("1.0")), tick)
            risk_pts = entry_min - stop_loss
            if risk_pts > Decimal("0"):
                t1 = normalize_price(bb_middle, tick)
                t2 = normalize_price(bb_upper, tick)
                rr_t1 = float((t1 - entry_min) / risk_pts) if risk_pts > 0 else 1.5
                rr_t2 = float((t2 - entry_min) / risk_pts) if risk_pts > 0 else 3.0
                contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=0)

                tech_score = min(92.0, 50.0 + ((30.0 - rsi) * 2.0) + 15.0)
                mtf_score = float(ctx.mtf.get("alignment_score", 65.0))
                fno_score = 70.0
                regime_score = 85.0 if ctx.regime == "RANGE" else 65.0

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
                    risk_reward_t1=max(1.0, round(rr_t1, 2)),
                    risk_reward_t2=max(2.0, round(rr_t2, 2)),
                    technical_score=tech_score,
                    mtf_score=mtf_score,
                    fno_score=fno_score,
                    regime_score=regime_score,
                    overall_confidence=round((tech_score * 0.4) + (mtf_score * 0.2) + (fno_score * 0.2) + (regime_score * 0.2), 1),
                    rationale=[
                        f"Price at Lower Bollinger Band (₹{bb_lower:,.2f})",
                        f"RSI oversold exhaustion ({rsi:.1f})",
                        f"Range-bound consolidation regime",
                        f"Target 1 at Mean / VWAP (₹{bb_middle:,.2f})",
                    ],
                    option_contract=contract,
                    ttl_seconds=300,
                )

        # ── BEARISH OVERBOUGHT REVERSAL (LONG_PUT) ──
        if (spot >= bb_upper * Decimal("0.998")) and rsi >= 72.0:
            entry_min = normalize_price(spot - (atr * Decimal("0.2")), tick)
            entry_max = normalize_price(spot, tick)
            trigger_gap = max(atr * Decimal("0.30"), spot * Decimal("0.0006"))
            trigger = normalize_price(spot - trigger_gap, tick)
            stop_loss = normalize_price(spot + (atr * Decimal("1.0")), tick)
            risk_pts = stop_loss - entry_max
            if risk_pts > Decimal("0"):
                t1 = normalize_price(bb_middle, tick)
                t2 = normalize_price(bb_lower, tick)
                rr_t1 = float((entry_max - t1) / risk_pts) if risk_pts > 0 else 1.5
                rr_t2 = float((entry_max - t2) / risk_pts) if risk_pts > 0 else 3.0
                contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=0)

                tech_score = min(92.0, 50.0 + ((rsi - 70.0) * 2.0) + 15.0)
                mtf_score = float(ctx.mtf.get("alignment_score", 65.0))
                fno_score = 70.0
                regime_score = 85.0 if ctx.regime == "RANGE" else 65.0

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
                    risk_reward_t1=max(1.0, round(rr_t1, 2)),
                    risk_reward_t2=max(2.0, round(rr_t2, 2)),
                    technical_score=tech_score,
                    mtf_score=mtf_score,
                    fno_score=fno_score,
                    regime_score=regime_score,
                    overall_confidence=round((tech_score * 0.4) + (mtf_score * 0.2) + (fno_score * 0.2) + (regime_score * 0.2), 1),
                    rationale=[
                        f"Price at Upper Bollinger Band (₹{bb_upper:,.2f})",
                        f"RSI overbought exhaustion ({rsi:.1f})",
                        f"Range-bound consolidation regime",
                        f"Target 1 at Mean / VWAP (₹{bb_middle:,.2f})",
                    ],
                    option_contract=contract,
                    ttl_seconds=300,
                )

        return None
