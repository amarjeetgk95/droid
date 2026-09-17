"""
Strategy S4 — MOMENTUM_REACCELERATION (§8, P1 overhaul).
Captures continuation after a controlled momentum reset/pullback where structure remains intact
and price re-accelerates in the original trend direction.
Desk: SCALP (1M / 3M)
P1: closed 1M candle (is_new_1m_candle) + second-tick confirmation
(current close beyond prior high/low with directional close) + measured
volume >= 1.2x fail-closed. Dynamic earn-from-50 scoring.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import (
    Strategy,
    StrategyContext,
    SignalCandidate,
    extract_volume_ratio,
    has_closed_1m_candle,
    VOLUME_SCALP_MIN,
)
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.features.ema_features import extract_ema_features


def _dynamic_scores(
    slope: float,
    body_ratio: float,
    pcr: float,
    direction: str,
    regime: str,
    mtf_align: float,
    vol_ratio: float,
) -> tuple[float, float, float, float, float]:
    tech = 50.0 + min(10.0, abs(slope) * 120.0) + (body_ratio * 12.0) + (max(0.0, vol_ratio - 1.2) * 8.0)
    tech_score = round(min(90.0, max(50.0, tech)), 1)
    mtf_score = round(max(50.0, float(mtf_align)), 1)
    if direction == "LONG_CALL":
        fno_score = round(min(85.0, max(45.0, 50.0 + ((pcr - 1.0) * 30.0))), 1)
        regime_score = 80.0 if regime in ("TREND_UP", "HIGH_VOL") else 60.0
    else:
        fno_score = round(min(85.0, max(45.0, 50.0 + ((1.0 - pcr) * 30.0))), 1)
        regime_score = 80.0 if regime in ("TREND_DOWN", "HIGH_VOL") else 60.0
    conf = round(0.40 * tech_score + 0.20 * mtf_score + 0.20 * fno_score + 0.20 * regime_score, 1)
    return tech_score, mtf_score, fno_score, regime_score, conf


class MomentumReaccelerationStrategy(Strategy):
    name = "MOMENTUM_REACCELERATION"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        if ctx.timeframe not in ("1M", "3M"):
            return None

        # P1 closed-candle gate.
        if not has_closed_1m_candle(ctx):
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

        # P1 volume gate: measured >= 1.2x, fail-closed.
        vol_ratio = extract_volume_ratio(ctx.indicators)
        if vol_ratio is None:
            return None
        if vol_ratio < VOLUME_SCALP_MIN:
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
        body = abs(c_close - c_open)
        body_ratio = float(body / candle_range) if candle_range > 0 else 0.0

        # Inspect last 4 candles to check: impulse -> 1-2 candle pause/reset -> current candle expanding
        c_prev1 = candles[-2]
        c_prev2 = candles[-3]

        try:
            pcr_val = float(ctx.fno.get("pcr", 1.0) or 1.0)
        except (TypeError, ValueError):
            pcr_val = 1.0
        mtf_align = float(ctx.mtf.get("alignment_score", 70.0))

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
            # P1 second-tick: current close beyond prior high with bullish close.
            if is_reset and c_close > Decimal(str(c_prev1.get("high", spot))):
                # Acceleration confirmation: current close above prev close and body strong.
                if body_ratio < 0.40:
                    return None
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

                tech_s, mtf_s, fno_s, reg_s, conf = _dynamic_scores(
                    float(ema_feat.fast_slope or 0.0), body_ratio, pcr_val,
                    "LONG_CALL", ctx.regime, mtf_align, vol_ratio,
                )
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
                    technical_score=tech_s,
                    mtf_score=mtf_s,
                    fno_score=fno_s,
                    regime_score=reg_s,
                    overall_confidence=conf,
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
                if body_ratio < 0.40:
                    return None
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

                tech_s, mtf_s, fno_s, reg_s, conf = _dynamic_scores(
                    float(ema_feat.fast_slope or 0.0), body_ratio, pcr_val,
                    "LONG_PUT", ctx.regime, mtf_align, vol_ratio,
                )
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
                    technical_score=tech_s,
                    mtf_score=mtf_s,
                    fno_score=fno_s,
                    regime_score=reg_s,
                    overall_confidence=conf,
                    rationale=[
                        f"Controlled momentum reset resolved into bearish reacceleration below fast EMA",
                        f"Prior reset held resistance; breaking prior low {float(c_prev1.get('low', 0)):.2f}",
                        f"Scalp risk: {float(risk_pts):.1f} pts (SL: {float(stop_loss):.1f})",
                    ],
                    option_contract=contract,
                )

        return None
