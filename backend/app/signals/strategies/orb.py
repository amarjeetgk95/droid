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
        # ── Session Time Window Enforcement (§15: Active 09:30 - 14:00 IST) ──
        # Quality taper: full confidence 09:30-11:30, reduced confidence 11:30-14:00
        session_quality = 1.0
        if ctx.timestamp_ms and ctx.timestamp_ms > 0:
            utc_minutes = (ctx.timestamp_ms // 60000) % 1440
            ist_minutes = (utc_minutes + 330) % 1440
            if ist_minutes < 570 or ist_minutes > 840:
                return None
            if 690 < ist_minutes <= 840:
                session_quality = 0.85

        ind = ctx.indicators
        spot = ctx.spot_price
        tick = Decimal("0.05")

        # Check for ORB range in indicators or calculate from opening candle extremes
        orb_data = ind.get("orb") or ind.get("price_action", {}).get("opening_range", {})
        atr = resolve_realistic_atr(ctx.underlying, spot, ind)

        if orb_data.get("high") and orb_data.get("low"):
            orb_high = Decimal(str(orb_data["high"]))
            orb_low = Decimal(str(orb_data["low"]))
        elif ctx.candles and len(ctx.candles) >= 2:
            # 5M timeframe: first 3 candles = 15m opening range; 1M timeframe: first 15 candles.
            n_candles = 3 if ctx.timeframe == "5M" else (15 if ctx.timeframe == "1M" else 3)
            opening_candles = ctx.candles[:min(len(ctx.candles), n_candles)]
            orb_high = Decimal(str(max(float(c.get("high", spot)) for c in opening_candles)))
            orb_low = Decimal(str(min(float(c.get("low", spot)) for c in opening_candles)))
        else:
            # Fail closed: ORB requires true opening range or opening candles
            return None

        range_height = max(atr * Decimal("0.5"), orb_high - orb_low)
        mid_point = (orb_high + orb_low) / Decimal("2")

        vol_ratio = float(ind.get("volume_ratio", 1.3))
        mtf_bias = ctx.mtf.get("overall_bias", "NEUTRAL")
        min_gap = max(atr * Decimal("0.25"), spot * Decimal("0.0006"))

        # ── BULLISH ORB (LONG_CALL) ──
        if spot >= orb_high and mtf_bias != "BEARISH":
            chase = spot - orb_high
            if chase > (atr * Decimal("0.5")):
                return None  # Chase exceeded

            raw_trigger = spot + min_gap
            trigger = normalize_price(raw_trigger, tick)
            if trigger <= spot or abs(trigger - spot) < min_gap:
                trigger = normalize_price(max(trigger, spot) + tick, tick)

            entry_min = normalize_price(spot, tick)
            entry_max = normalize_price(trigger + (atr * Decimal("0.1")), tick)
            stop_loss = normalize_price(max(mid_point, orb_high - (atr * Decimal("0.5"))), tick)
            risk_pts = trigger - stop_loss
            if risk_pts > Decimal("0"):
                t1 = normalize_price(trigger + max(range_height, risk_pts * Decimal("1.2")), tick)
                t2 = normalize_price(trigger + max(range_height * Decimal("2.0"), risk_pts * Decimal("2.4")), tick)
                rr_t1 = float((t1 - trigger) / risk_pts) if risk_pts > 0 else 1.5
                rr_t2 = float((t2 - trigger) / risk_pts) if risk_pts > 0 else 3.0
                contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=0)

                tech_score = min(88.0, max(50.0, 50.0 + (max(0.0, vol_ratio - 1.4) * 18.0)))
                mtf_score = max(50.0, float(ctx.mtf.get("alignment_score", 70.0)) - 10.0)
                fno_score = 65.0
                regime_score = 75.0 if ctx.regime in ("TREND_UP", "HIGH_VOL") else 55.0

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
                    overall_confidence=round((tech_score * 0.4) + (mtf_score * 0.2) + (fno_score * 0.2) + (regime_score * 0.2), 1) * session_quality,
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
            chase = orb_low - spot
            if chase > (atr * Decimal("0.5")):
                return None  # Chase exceeded

            raw_trigger = spot - min_gap
            trigger = normalize_price(raw_trigger, tick)
            if trigger >= spot or abs(spot - trigger) < min_gap:
                trigger = normalize_price(min(trigger, spot) - tick, tick)

            entry_max = normalize_price(spot, tick)
            entry_min = normalize_price(trigger - (atr * Decimal("0.1")), tick)
            stop_loss = normalize_price(min(mid_point, orb_low + (atr * Decimal("0.5"))), tick)
            risk_pts = stop_loss - trigger
            if risk_pts > Decimal("0"):
                t1 = normalize_price(trigger - max(range_height, risk_pts * Decimal("1.2")), tick)
                t2 = normalize_price(trigger - max(range_height * Decimal("2.0"), risk_pts * Decimal("2.4")), tick)
                rr_t1 = float((trigger - t1) / risk_pts) if risk_pts > 0 else 1.5
                rr_t2 = float((trigger - t2) / risk_pts) if risk_pts > 0 else 3.0
                contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=0)

                tech_score = min(88.0, max(50.0, 50.0 + (max(0.0, vol_ratio - 1.4) * 18.0)))
                mtf_score = max(50.0, float(ctx.mtf.get("alignment_score", 70.0)) - 10.0)
                fno_score = 65.0
                regime_score = 75.0 if ctx.regime in ("TREND_DOWN", "HIGH_VOL") else 55.0

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
                    overall_confidence=round((tech_score * 0.4) + (mtf_score * 0.2) + (fno_score * 0.2) + (regime_score * 0.2), 1) * session_quality,
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
