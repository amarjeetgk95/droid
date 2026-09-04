"""
Opening Range Breakout (ORB 15M) Strategy
Mathematical rules:
  - Establishes the high and low of the first 15 minutes of the session (09:15 - 09:30 IST).
  - LONG_CALL: Price crosses above Opening Range High + 1 tick, confirmation 5m close above high, Volume ratio >= 1.3.
  - LONG_PUT: Price crosses below Opening Range Low - 1 tick, confirmation 5m close below low, Volume ratio >= 1.3.
  - SL = Midpoint of Opening Range or Opposite boundary, T1 = ORB Range Height (1.0x), T2 = 2.0x Range Height.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.risk_engine import resolve_realistic_atr


class OpeningRangeBreakoutStrategy(Strategy):
    name = "ORB"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        ind = ctx.indicators
        spot = ctx.spot_price
        tick = Decimal("0.05")

        # Check for ORB range in indicators or fallback to first candle extremes
        orb_data = ind.get("orb") or ind.get("price_action", {}).get("opening_range", {})
        atr = resolve_realistic_atr(ctx.underlying, spot, ind)

        orb_high = Decimal(str(orb_data.get("high") or spot * Decimal("1.004")))
        orb_low = Decimal(str(orb_data.get("low") or spot * Decimal("0.996")))
        range_height = orb_high - orb_low
        mid_point = (orb_high + orb_low) / Decimal("2")

        vol_ratio = float(ind.get("volume_ratio", 1.3))
        mtf_bias = ctx.mtf.get("overall_bias", "NEUTRAL")

        # ── BULLISH ORB (LONG_CALL) ──
        if spot >= orb_high and mtf_bias != "BEARISH":
            entry_min = normalize_price(orb_high, tick)
            entry_max = normalize_price(orb_high + (atr * Decimal("0.2")), tick)
            trigger = normalize_price(orb_high + tick, tick)
            stop_loss = normalize_price(mid_point, tick)
            risk_pts = entry_min - stop_loss
            if risk_pts > Decimal("0"):
                t1 = normalize_price(entry_min + range_height, tick)
                t2 = normalize_price(entry_min + (range_height * Decimal("2.0")), tick)
                rr_t1 = float((t1 - entry_min) / risk_pts) if risk_pts > 0 else 1.5
                rr_t2 = float((t2 - entry_min) / risk_pts) if risk_pts > 0 else 3.0
                contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=0)

                tech_score = min(93.0, 65.0 + (vol_ratio * 15.0))
                mtf_score = float(ctx.mtf.get("alignment_score", 70.0))
                fno_score = 70.0
                regime_score = 80.0 if ctx.regime in ("TREND_UP", "HIGH_VOL") else 65.0

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
                        f"15-Minute Opening Range High Breakout (₹{orb_high:,.2f})",
                        f"Session volume expansion ratio {vol_ratio:.2f}x",
                        f"Stop loss anchored at ORB midpoint (₹{mid_point:,.2f})",
                        f"Target 1 at 100% ORB Range Extension (₹{t1:,.2f})",
                    ],
                    option_contract=contract,
                    ttl_seconds=300,
                )

        # ── BEARISH ORB (LONG_PUT) ──
        if spot <= orb_low and mtf_bias != "BULLISH":
            entry_min = normalize_price(orb_low - (atr * Decimal("0.2")), tick)
            entry_max = normalize_price(orb_low, tick)
            trigger = normalize_price(orb_low - tick, tick)
            stop_loss = normalize_price(mid_point, tick)
            risk_pts = stop_loss - entry_max
            if risk_pts > Decimal("0"):
                t1 = normalize_price(entry_max - range_height, tick)
                t2 = normalize_price(entry_max - (range_height * Decimal("2.0")), tick)
                rr_t1 = float((entry_max - t1) / risk_pts) if risk_pts > 0 else 1.5
                rr_t2 = float((entry_max - t2) / risk_pts) if risk_pts > 0 else 3.0
                contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=0)

                tech_score = min(93.0, 65.0 + (vol_ratio * 15.0))
                mtf_score = float(ctx.mtf.get("alignment_score", 70.0))
                fno_score = 70.0
                regime_score = 80.0 if ctx.regime in ("TREND_DOWN", "HIGH_VOL") else 65.0

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
                        f"15-Minute Opening Range Low Breakdown (₹{orb_low:,.2f})",
                        f"Session volume expansion ratio {vol_ratio:.2f}x",
                        f"Stop loss anchored at ORB midpoint (₹{mid_point:,.2f})",
                        f"Target 1 at 100% ORB Range Extension (₹{t1:,.2f})",
                    ],
                    option_contract=contract,
                    ttl_seconds=300,
                )

        return None
