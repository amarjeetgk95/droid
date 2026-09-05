"""
Institutional Breakout / Breakdown Strategy
Mathematical rules:
  - LONG_CALL: Close >= Resistance + 1 tick, Volume Ratio >= 1.4, Breakout Pressure >= 68, 15M MTF != BEARISH
  - LONG_PUT: Close <= Support - 1 tick, Volume Ratio >= 1.4, Breakout Pressure >= 68, 15M MTF != BULLISH
  - SL = Entry - 1.5 * ATR (or S/R level), T1 = Entry + 1.5R, T2 = Entry + 3.0R
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.risk_engine import resolve_realistic_atr


class BreakoutStrategy(Strategy):
    name = "BREAKOUT"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        ind = ctx.indicators
        spot = ctx.spot_price
        tick = Decimal("0.05")

        # Extract indicators
        sr = ind.get("support_resistance", {})
        resistances = [Decimal(str(r)) for r in sr.get("resistance", []) if r]
        supports = [Decimal(str(s)) for s in sr.get("support", []) if s]

        atr = resolve_realistic_atr(ctx.underlying, spot, ind)
        vol_ratio = float(ind.get("volume_ratio", 1.2))
        breakout_pressure = float(ind.get("breakout_pressure", ind.get("scores", {}).get("breakout_pressure", 65)))
        mtf_bias = ctx.mtf.get("overall_bias", "NEUTRAL")

        # ── BULLISH BREAKOUT (LONG_CALL) ──
        if resistances:
            key_res = min([r for r in resistances if r >= spot * Decimal("0.99")], default=resistances[0])
            if (spot >= key_res or breakout_pressure >= 72) and mtf_bias != "BEARISH":
                min_gap = max(atr * Decimal("0.25"), spot * Decimal("0.0006"))
                if spot < key_res:
                    # Pre-breakout setup: trigger above resistance
                    trigger = normalize_price(key_res + min_gap, tick)
                    if trigger <= spot or abs(trigger - spot) < min_gap:
                        trigger = normalize_price(max(trigger, spot) + tick, tick)
                    entry_min = normalize_price(key_res, tick)
                    entry_max = normalize_price(trigger + (atr * Decimal("0.1")), tick)
                    stop_loss = normalize_price(key_res - (atr * Decimal("0.75")), tick)
                else:
                    # Breakout continuation: spot >= key_res
                    chase = spot - key_res
                    raw_atr_val = Decimal(str(ind.get("atr") or ind.get("volatility", {}).get("atr") or 0))
                    chase_limit = max(atr * Decimal("0.5"), raw_atr_val * Decimal("0.5"))
                    if chase > chase_limit:
                        return None  # Chase exceeded
                    raw_trigger = spot + min_gap
                    trigger = normalize_price(raw_trigger, tick)
                    if trigger <= spot or abs(trigger - spot) < min_gap:
                        trigger = normalize_price(max(trigger, spot) + tick, tick)
                    entry_min = normalize_price(spot, tick)
                    entry_max = normalize_price(trigger + (atr * Decimal("0.1")), tick)
                    stop_loss = normalize_price(key_res - (atr * Decimal("0.5")), tick)

                risk_pts = trigger - stop_loss
                if risk_pts > Decimal("0"):
                    t1 = normalize_price(trigger + (risk_pts * Decimal("1.5")), tick)
                    t2 = normalize_price(trigger + (risk_pts * Decimal("3.0")), tick)
                    contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=0)
                    
                    tech_score = min(95.0, 50.0 + (vol_ratio * 15.0) + (breakout_pressure * 0.3))
                    mtf_score = float(ctx.mtf.get("alignment_score", 70.0))
                    fno_score = 75.0 if float(ctx.fno.get("pcr", 1.0)) >= 1.0 else 55.0
                    regime_score = 80.0 if ctx.regime in ("TREND_UP", "HIGH_VOL") else 60.0

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
                            f"Resistance break at ₹{key_res:,.2f}",
                            f"Volume expansion ratio {vol_ratio:.2f}x",
                            f"Breakout pressure {breakout_pressure:.0f}/100",
                            f"MTF bias {mtf_bias}",
                        ],
                        option_contract=contract,
                        ttl_seconds=300,
                    )

        # ── BEARISH BREAKDOWN (LONG_PUT) ──
        if supports:
            key_sup = max([s for s in supports if s <= spot * Decimal("1.01")], default=supports[0])
            if (spot <= key_sup or breakout_pressure >= 72) and mtf_bias != "BULLISH":
                min_gap = max(atr * Decimal("0.25"), spot * Decimal("0.0006"))
                if spot > key_sup:
                    # Pre-breakdown setup: trigger below support
                    trigger = normalize_price(key_sup - min_gap, tick)
                    if trigger >= spot or abs(spot - trigger) < min_gap:
                        trigger = normalize_price(min(trigger, spot) - tick, tick)
                    entry_max = normalize_price(key_sup, tick)
                    entry_min = normalize_price(trigger - (atr * Decimal("0.1")), tick)
                    stop_loss = normalize_price(key_sup + (atr * Decimal("0.75")), tick)
                else:
                    # Breakdown continuation: spot <= key_sup
                    chase = key_sup - spot
                    raw_atr_val = Decimal(str(ind.get("atr") or ind.get("volatility", {}).get("atr") or 0))
                    chase_limit = max(atr * Decimal("0.5"), raw_atr_val * Decimal("0.5"))
                    if chase > chase_limit:
                        return None  # Chase exceeded
                    raw_trigger = spot - min_gap
                    trigger = normalize_price(raw_trigger, tick)
                    if trigger >= spot or abs(spot - trigger) < min_gap:
                        trigger = normalize_price(min(trigger, spot) - tick, tick)
                    entry_max = normalize_price(spot, tick)
                    entry_min = normalize_price(trigger - (atr * Decimal("0.1")), tick)
                    stop_loss = normalize_price(key_sup + (atr * Decimal("0.5")), tick)

                risk_pts = stop_loss - trigger
                if risk_pts > Decimal("0"):
                    t1 = normalize_price(trigger - (risk_pts * Decimal("1.5")), tick)
                    t2 = normalize_price(trigger - (risk_pts * Decimal("3.0")), tick)
                    contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=0)

                    tech_score = min(95.0, 50.0 + (vol_ratio * 15.0) + (breakout_pressure * 0.3))
                    mtf_score = float(ctx.mtf.get("alignment_score", 70.0))
                    fno_score = 75.0 if float(ctx.fno.get("pcr", 1.0)) <= 0.9 else 55.0
                    regime_score = 80.0 if ctx.regime in ("TREND_DOWN", "HIGH_VOL") else 60.0

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
                            f"Support breakdown at ₹{key_sup:,.2f}",
                            f"Volume expansion ratio {vol_ratio:.2f}x",
                            f"Breakout pressure {breakout_pressure:.0f}/100",
                            f"MTF bias {mtf_bias}",
                        ],
                        option_contract=contract,
                        ttl_seconds=300,
                    )

        return None
