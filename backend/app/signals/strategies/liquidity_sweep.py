"""
Strategy S2 — LIQUIDITY_SWEEP_RECLAIM (§6, P1 overhaul).
Captures failed breaks of meaningful swing levels (15-60m swing points, session high/low)
followed by an immediate bar reclaim with participation confirmation.
Desk: SCALP (1M / 3M)
P1: closed 1M candle (is_new_1m_candle) + second-tick confirmation
(reclaim persists on second tick) + measured volume >= 1.2x fail-closed.
P1 regime filter: veto strong trend against the sweep direction.
Dynamic earn-from-50 scoring.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import (
    Strategy,
    StrategyContext,
    SignalCandidate,
    extract_volume_ratio,
    extract_adx,
    has_closed_1m_candle,
    ADX_TREND_CUTOFF,
    VOLUME_SCALP_MIN,
)
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.features.structure import extract_market_structure


def _dynamic_scores(
    sweep_depth_pts: float,
    wick_ratio: float,
    vol_ratio: float,
    pcr: float,
    direction: str,
    mtf_align: float,
) -> tuple[float, float, float, float, float]:
    tech = 50.0 + min(12.0, sweep_depth_pts * 0.4) + (wick_ratio * 20.0) + (max(0.0, vol_ratio - 1.2) * 8.0)
    tech_score = round(min(90.0, max(50.0, tech)), 1)
    mtf_score = round(max(50.0, float(mtf_align)), 1)
    if direction == "LONG_CALL":
        fno_score = round(min(85.0, max(45.0, 50.0 + ((pcr - 1.0) * 30.0))), 1)
    else:
        fno_score = round(min(85.0, max(45.0, 50.0 + ((1.0 - pcr) * 30.0))), 1)
    regime_score = 75.0
    conf = round(0.40 * tech_score + 0.20 * mtf_score + 0.20 * fno_score + 0.20 * regime_score, 1)
    return tech_score, mtf_score, fno_score, regime_score, conf


class LiquiditySweepReclaimStrategy(Strategy):
    name = "LIQUIDITY_SWEEP_RECLAIM"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        if ctx.timeframe not in ("1M", "3M"):
            return None

        # P1 closed-candle gate.
        if not has_closed_1m_candle(ctx):
            return None

        spot = ctx.spot_price
        if spot <= Decimal("0"):
            return None

        candles = ctx.candles
        if not candles or len(candles) < 4:
            return None

        # P1 volume gate: measured >= 1.2x, fail-closed.
        vol_ratio = extract_volume_ratio(ctx.indicators)
        if vol_ratio is None:
            return None
        if vol_ratio < VOLUME_SCALP_MIN:
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

        # Second-tick persistence: prev close must already be back on the reclaim
        # side (two consecutive closes beyond the swept level).
        try:
            prev_close = Decimal(str(candles[-2].get("close", spot)))
        except Exception:
            return None

        mtf_bias = str(ctx.mtf.get("overall_bias", "NEUTRAL")).upper()
        adx_val = extract_adx(ctx.indicators)
        try:
            pcr_val = float(ctx.fno.get("pcr", 1.0) or 1.0)
        except (TypeError, ValueError):
            pcr_val = 1.0
        mtf_align = float(ctx.mtf.get("alignment_score", 70.0))

        # ── BULLISH LIQUIDITY SWEEP & RECLAIM ──
        # Low pierced below key swing low, but candle closed back ABOVE that level
        if recent_sl and struct.low_swept_and_reclaimed:
            # P1 regime veto: strong downtrend against a bullish sweep.
            if ctx.regime == "TREND_DOWN" and adx_val is not None and adx_val >= ADX_TREND_CUTOFF:
                pass  # veto bull sweep
            elif mtf_bias == "BEARISH" and ctx.regime == "TREND_DOWN":
                pass  # veto bull sweep into aligned downtrend
            else:
                level_dec = Decimal(str(round(recent_sl, 2)))
                # Reclaimed: close > level and candle is bullish (or hammer)
                if c_close > level_dec and c_close >= c_open and prev_close > level_dec:
                    sweep_depth = float(level_dec - min(c_low, level_dec))
                    wick = float((min(c_open, c_close) - c_low) / candle_range) if float(candle_range) > 0 else 0.0
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

                    tech_s, mtf_s, fno_s, reg_s, conf = _dynamic_scores(
                        sweep_depth, wick, vol_ratio, pcr_val, "LONG_CALL", mtf_align
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
                            f"Liquidity swept below swing low {float(level_dec):.2f} and reclaimed at {float(c_close):.2f}",
                            f"Failed continuation / trapped breakout sellers",
                            f"Scalp risk: {float(risk_pts):.1f} pts (SL: {float(stop_loss):.1f})",
                        ],
                        option_contract=contract,
                    )

        # ── BEARISH LIQUIDITY SWEEP & RECLAIM ──
        # High pierced above key swing high, but candle closed back BELOW that level
        if recent_sh and struct.high_swept_and_reclaimed:
            if ctx.regime == "TREND_UP" and adx_val is not None and adx_val >= ADX_TREND_CUTOFF:
                return None  # veto bear sweep into strong uptrend
            if mtf_bias == "BULLISH" and ctx.regime == "TREND_UP":
                return None
            level_dec = Decimal(str(round(recent_sh, 2)))
            if c_close < level_dec and c_close <= c_open and prev_close < level_dec:
                sweep_depth = float(max(c_high, level_dec) - level_dec)
                wick = float((c_high - max(c_open, c_close)) / candle_range) if float(candle_range) > 0 else 0.0
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

                tech_s, mtf_s, fno_s, reg_s, conf = _dynamic_scores(
                    sweep_depth, wick, vol_ratio, pcr_val, "LONG_PUT", mtf_align
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
                        f"Liquidity swept above swing high {float(level_dec):.2f} and reclaimed at {float(c_close):.2f}",
                        f"Failed continuation / trapped breakout buyers",
                        f"Scalp risk: {float(risk_pts):.1f} pts (SL: {float(stop_loss):.1f})",
                    ],
                    option_contract=contract,
                )

        return None
