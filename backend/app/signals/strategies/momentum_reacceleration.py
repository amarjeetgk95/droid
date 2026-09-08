"""
Strategy S4 — MOMENTUM_REACCELERATION (§8).
Captures continuation after a controlled momentum reset/pullback where structure remains intact
and price re-accelerates in the original trend direction.
Desk: SCALP (1M / 3M)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.features.ema_features import extract_ema_features


class MomentumReaccelerationStrategy(Strategy):
    name = "MOMENTUM_REACCELERATION"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        if ctx.timeframe not in ("1M", "3M"):
            return None

        # Exclude sideways range - requires active trend or volatility expansion
        if ctx.regime in ("RANGE", "LOW_VOL"):
            return None

        spot = ctx.spot_price
        if spot <= Decimal("0"):
            return None

        candles = ctx.candles
        if not candles or len(candles) < 5:
            return None

        tick = Decimal("0.05")
        is_high_vol = ctx.regime == "HIGH_VOL"

        # Risk parameters
        if ctx.underlying == "NIFTY":
            min_risk = Decimal("14.0") if is_high_vol else Decimal("10.0")
        elif ctx.underlying == "BANKNIFTY":
            min_risk = Decimal("40.0") if is_high_vol else Decimal("30.0")
        else:  # SENSEX
            min_risk = Decimal("80.0") if is_high_vol else Decimal("60.0")

        closes = [float(c.get("close", 0)) for c in candles]
        ema_feat = extract_ema_features(closes, current_price=float(spot))

        last_c = candles[-1]
        c_open = Decimal(str(last_c.get("open", spot)))
        c_high = Decimal(str(last_c.get("high", spot)))
        c_low = Decimal(str(last_c.get("low", spot)))
        c_close = Decimal(str(last_c.get("close", spot)))
        candle_range = c_high - c_low
        if candle_range <= Decimal("0"):
            return None

        # Inspect last 4 candles to check: impulse -> 1-2 candle pause/reset -> current candle expanding
        c_prev1 = candles[-2]
        c_prev2 = candles[-3]
        c_prev3 = candles[-4]

        # ── BULLISH REACCELERATION ──
        # Fast EMA slope positive, prior candle was pullback/small body, current candle closes strong
        if (
            ema_feat.fast_slope > 0.02
            and c_close > c_open
            and float(spot) >= (ema_feat.ema_fast or 0)
        ):
            # Prior candle had smaller range or was red (controlled reset)
            prev_rng = float(c_prev1.get("high", 0)) - float(c_prev1.get("low", 0))
            is_reset = float(c_prev1.get("close", 0)) <= float(c_prev1.get("open", 0)) or prev_rng < float(candle_range) * 0.85
            if is_reset and c_close > Decimal(str(c_prev1.get("high", spot))):
                entry_min = normalize_price(spot, tick)
                entry_max = normalize_price(spot + (candle_range * Decimal("0.2")), tick)
                trigger = normalize_price(c_high + tick, tick)
                pullback_low = min(c_low, Decimal(str(c_prev1.get("low", c_low))))
                raw_risk = entry_min - pullback_low
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
                    technical_score=80.0,
                    mtf_score=float(ctx.mtf.get("alignment_score", 70.0)),
                    fno_score=60.0,
                    regime_score=80.0,
                    overall_confidence=78.0,
                    rationale=[
                        f"Controlled momentum reset resolved into bullish reacceleration above fast EMA",
                        f"Prior reset held support; breaking prior high {float(c_prev1.get('high', 0)):.2f}",
                        f"Scalp risk: {float(risk_pts):.1f} pts (SL: {float(stop_loss):.1f})",
                    ],
                    option_contract=contract,
                )

        # ── BEARISH REACCELERATION ──
        if (
            ema_feat.fast_slope < -0.02
            and c_close < c_open
            and float(spot) <= (ema_feat.ema_fast or float("inf"))
        ):
            prev_rng = float(c_prev1.get("high", 0)) - float(c_prev1.get("low", 0))
            is_reset = float(c_prev1.get("close", 0)) >= float(c_prev1.get("open", 0)) or prev_rng < float(candle_range) * 0.85
            if is_reset and c_close < Decimal(str(c_prev1.get("low", spot))):
                entry_min = normalize_price(spot - (candle_range * Decimal("0.2")), tick)
                entry_max = normalize_price(spot, tick)
                trigger = normalize_price(c_low - tick, tick)
                pullback_high = max(c_high, Decimal(str(c_prev1.get("high", c_high))))
                raw_risk = pullback_high - entry_max
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
                    technical_score=80.0,
                    mtf_score=float(ctx.mtf.get("alignment_score", 70.0)),
                    fno_score=60.0,
                    regime_score=80.0,
                    overall_confidence=78.0,
                    rationale=[
                        f"Controlled momentum reset resolved into bearish reacceleration below fast EMA",
                        f"Prior reset held resistance; breaking prior low {float(c_prev1.get('low', 0)):.2f}",
                        f"Scalp risk: {float(risk_pts):.1f} pts (SL: {float(stop_loss):.1f})",
                    ],
                    option_contract=contract,
                )

        return None
