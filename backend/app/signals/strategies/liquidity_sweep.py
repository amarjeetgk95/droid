"""
Strategy S2 — LIQUIDITY_SWEEP_RECLAIM (§6).
Captures failed breaks of meaningful swing levels (15-60m swing points, session high/low)
followed by an immediate bar reclaim with participation confirmation.
Desk: SCALP (1M / 3M)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.features.structure import extract_market_structure


class LiquiditySweepReclaimStrategy(Strategy):
    name = "LIQUIDITY_SWEEP_RECLAIM"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        if ctx.timeframe not in ("1M", "3M"):
            return None

        spot = ctx.spot_price
        if spot <= Decimal("0"):
            return None

        candles = ctx.candles
        if not candles or len(candles) < 4:
            return None

        tick = Decimal("0.05")
        is_high_vol = ctx.regime == "HIGH_VOL"

        # Minimum base risk envelopes
        if ctx.underlying == "NIFTY":
            min_risk = Decimal("14.0") if is_high_vol else Decimal("10.0")
        elif ctx.underlying == "BANKNIFTY":
            min_risk = Decimal("40.0") if is_high_vol else Decimal("30.0")
        else:  # SENSEX
            min_risk = Decimal("80.0") if is_high_vol else Decimal("60.0")

        # Extract market structure features
        struct = extract_market_structure(candles, current_price=float(spot))
        recent_sh = struct.recent_swing_high or struct.session_high
        recent_sl = struct.recent_swing_low or struct.session_low

        last_c = candles[-1]
        c_open = Decimal(str(last_c.get("open", spot)))
        c_high = Decimal(str(last_c.get("high", spot)))
        c_low = Decimal(str(last_c.get("low", spot)))
        c_close = Decimal(str(last_c.get("close", spot)))
        candle_range = c_high - c_low
        if candle_range <= Decimal("0"):
            return None

        # ── BULLISH LIQUIDITY SWEEP & RECLAIM ──
        # Low pierced below key swing low, but candle closed back ABOVE that level
        if recent_sl and struct.low_swept_and_reclaimed:
            level_dec = Decimal(str(round(recent_sl, 2)))
            # Reclaimed: close > level and candle is bullish (or hammer)
            if c_close > level_dec and c_close >= c_open:
                entry_min = normalize_price(spot, tick)
                entry_max = normalize_price(spot + (candle_range * Decimal("0.25")), tick)
                trigger = normalize_price(c_high + tick, tick)
                sweep_low = min(c_low, level_dec - (candle_range * Decimal("0.2")))
                raw_risk = entry_min - sweep_low
                risk_pts = max(min_risk, raw_risk)
                stop_loss = normalize_price(entry_min - risk_pts, tick)

                t1 = normalize_price(entry_min + (risk_pts * Decimal("1.5")), tick)
                t2 = normalize_price(entry_min + (risk_pts * Decimal("2.5")), tick)
                contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=-1)

                return SignalCandidate(
                    underlying=ctx.underlying,
                    strategy=self.name,
                    direction="LONG_CALL",
                    timeframe=ctx.timeframe,
                    spot_price=spot,
                    signal_type="SCALP",
                    is_scalp=True,
                    entry_min=entry_min,
                    entry_max=entry_max,
                    trigger=trigger,
                    stop_loss=stop_loss,
                    target_1=t1,
                    target_2=t2,
                    risk_points=risk_pts,
                    risk_reward_t1=1.5,
                    risk_reward_t2=2.5,
                    max_chase_fraction=0.35 if is_high_vol else 0.50,
                    ttl_seconds=240,
                    time_stop_seconds=240,
                    runner_ttl_seconds=480,
                    technical_score=82.0,
                    mtf_score=float(ctx.mtf.get("alignment_score", 70.0)),
                    fno_score=65.0,
                    regime_score=75.0,
                    overall_confidence=78.0,
                    rationale=[
                        f"Liquidity swept below swing low {float(level_dec):.2f} and reclaimed at {float(c_close):.2f}",
                        f"Failed continuation / trapped breakout sellers",
                        f"Scalp risk: {float(risk_pts):.1f} pts (SL: {float(stop_loss):.1f})",
                    ],
                    option_contract=contract,
                )

        # ── BEARISH LIQUIDITY SWEEP & RECLAIM ──
        # High pierced above key swing high, but candle closed back BELOW that level
        if recent_sh and struct.high_swept_and_reclaimed:
            level_dec = Decimal(str(round(recent_sh, 2)))
            if c_close < level_dec and c_close <= c_open:
                entry_min = normalize_price(spot - (candle_range * Decimal("0.25")), tick)
                entry_max = normalize_price(spot, tick)
                trigger = normalize_price(c_low - tick, tick)
                sweep_high = max(c_high, level_dec + (candle_range * Decimal("0.2")))
                raw_risk = sweep_high - entry_max
                risk_pts = max(min_risk, raw_risk)
                stop_loss = normalize_price(entry_max + risk_pts, tick)

                t1 = normalize_price(entry_max - (risk_pts * Decimal("1.5")), tick)
                t2 = normalize_price(entry_max - (risk_pts * Decimal("2.5")), tick)
                contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=-1)

                return SignalCandidate(
                    underlying=ctx.underlying,
                    strategy=self.name,
                    direction="LONG_PUT",
                    timeframe=ctx.timeframe,
                    spot_price=spot,
                    signal_type="SCALP",
                    is_scalp=True,
                    entry_min=entry_min,
                    entry_max=entry_max,
                    trigger=trigger,
                    stop_loss=stop_loss,
                    target_1=t1,
                    target_2=t2,
                    risk_points=risk_pts,
                    risk_reward_t1=1.5,
                    risk_reward_t2=2.5,
                    max_chase_fraction=0.35 if is_high_vol else 0.50,
                    ttl_seconds=240,
                    time_stop_seconds=240,
                    runner_ttl_seconds=480,
                    technical_score=82.0,
                    mtf_score=float(ctx.mtf.get("alignment_score", 70.0)),
                    fno_score=65.0,
                    regime_score=75.0,
                    overall_confidence=78.0,
                    rationale=[
                        f"Liquidity swept above swing high {float(level_dec):.2f} and reclaimed at {float(c_close):.2f}",
                        f"Failed continuation / trapped breakout buyers",
                        f"Scalp risk: {float(risk_pts):.1f} pts (SL: {float(stop_loss):.1f})",
                    ],
                    option_contract=contract,
                )

        return None
