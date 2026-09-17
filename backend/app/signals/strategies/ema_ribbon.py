"""
EMA_RIBBON Strategy (§9, P1 overhaul — DEMOTED legacy).
Timeframe: 1M
Detection:
  - 5M trend alignment (BULLISH / BEARISH)
  - 1M price pulls back into the dynamic pocket between 9 EMA and 21 EMA
  - Rejection wick + momentum recovery (EMA contact alone must never trigger)
  - P1: fail-closed EMA9/EMA21 (no spot* synthetic fallbacks), closed 1M
    candle (is_new_1m_candle) + second-tick confirmation + measured volume
    >= 1.2x fail-closed required.
  - Stop below/above 21 EMA or local structure
  - TTL: Original = 180s, Runner = 420s
  - Status: demoted — importable for back-compat, disabled by default, NOT in
    STRATEGY_REGISTRY auto-scan. Scalp ribbon entries are folded into
    TREND_PULLBACK context.
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


def _dynamic_scores(
    wick_ratio: float,
    pocket_pos: float,
    pcr: float,
    direction: str,
    regime: str,
    mtf_align: float,
    vol_ratio: float,
) -> tuple[float, float, float, float, float]:
    tech = 50.0 + (wick_ratio * 28.0) + (max(0.0, 1.0 - pocket_pos) * 8.0) + (max(0.0, vol_ratio - 1.2) * 8.0)
    tech_score = round(min(88.0, max(50.0, tech)), 1)
    mtf_score = round(max(50.0, float(mtf_align) - 10.0), 1)
    if direction == "LONG_CALL":
        fno_score = round(min(85.0, max(45.0, 50.0 + ((pcr - 1.0) * 30.0))), 1)
        regime_score = 75.0 if regime == "TREND_UP" else 60.0
    else:
        fno_score = round(min(85.0, max(45.0, 50.0 + ((1.0 - pcr) * 30.0))), 1)
        regime_score = 75.0 if regime == "TREND_DOWN" else 60.0
    conf = round(0.40 * tech_score + 0.20 * mtf_score + 0.20 * fno_score + 0.20 * regime_score, 1)
    return tech_score, mtf_score, fno_score, regime_score, conf


class EMARibbonScalpStrategy(Strategy):
    name = "EMA_RIBBON"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        if ctx.timeframe != "1M":
            return None

        # P1 closed-candle gate.
        if not has_closed_1m_candle(ctx):
            return None

        # Ranging or low vol suppresses trend ribbon scalps (§15)
        if ctx.regime in ("RANGE", "LOW_VOL"):
            return None

        spot = ctx.spot_price
        if spot <= Decimal("0"):
            return None

        mtf = ctx.mtf or {}
        mtf_bias = mtf.get("overall_bias", "NEUTRAL")

        ind = ctx.indicators
        trend_data = ind.get("trend", {})
        if not isinstance(trend_data, dict):
            trend_data = {}

        # P1 fail-closed: no spot* synthetic EMA fallbacks.
        raw_ema9 = trend_data.get("ema9")
        raw_ema21 = trend_data.get("ema21")
        if raw_ema9 is None or raw_ema21 is None:
            return None
        try:
            ema9 = Decimal(str(raw_ema9))
            ema21 = Decimal(str(raw_ema21))
        except Exception:
            return None
        if ema9 <= Decimal("0") or ema21 <= Decimal("0"):
            return None
        tick = Decimal("0.05")

        # P1 volume gate: measured >= 1.2x, fail-closed.
        vol_ratio = extract_volume_ratio(ind)
        if vol_ratio is None:
            return None
        if vol_ratio < VOLUME_SCALP_MIN:
            return None

        candles = ctx.candles
        if not candles or len(candles) < 4:
            return None

        last_c = candles[-1]
        prev_c = candles[-2]

        c_open = Decimal(str(last_c.get("open", spot)))
        c_high = Decimal(str(last_c.get("high", spot)))
        c_low = Decimal(str(last_c.get("low", spot)))
        c_close = Decimal(str(last_c.get("close", spot)))
        candle_range = c_high - c_low
        if candle_range <= Decimal("0"):
            return None
        try:
            prev_close = Decimal(str(prev_c.get("close", spot)))
            prev_open = Decimal(str(prev_c.get("open", spot)))
        except Exception:
            return None
        try:
            pcr_val = float(ctx.fno.get("pcr", 1.0) or 1.0)
        except (TypeError, ValueError):
            pcr_val = 1.0
        mtf_align = float(mtf.get("alignment_score", 75.0))

        # Instrument micro-risk envelope
        is_high_vol = ctx.regime == "HIGH_VOL"
        if ctx.underlying == "NIFTY":
            base_risk = Decimal("8.0") if is_high_vol else Decimal("6.0")
        elif ctx.underlying == "BANKNIFTY":
            base_risk = Decimal("26.0") if is_high_vol else Decimal("20.0")
        else:
            base_risk = Decimal("55.0") if is_high_vol else Decimal("42.0")

        # ── BULLISH PULLBACK INTO POCKET (5M Bullish + 1M EMA9 > EMA21) ──
        if mtf_bias in ("BULLISH", "NEUTRAL") and ema9 > ema21:
            # Price must have entered the pocket between ema21 and ema9
            entered_pocket = c_low <= ema9 and c_low >= (ema21 - (ema21 * Decimal("0.001")))
            # Must have momentum recovery: close back above EMA9 or bullish close
            recovered = c_close > c_open and c_close >= ema9
            # EMA contact alone is rejected: require rejection wick
            lower_wick = min(c_open, c_close) - c_low
            has_rejection_wick = (lower_wick / candle_range) >= Decimal("0.25")
            # P1 second-tick: prev close also shows pocket persistence / recovery.
            second_tick = prev_close >= ema21 and prev_close <= (ema9 + (ema9 * Decimal("0.002"))) and c_close > prev_close

            if entered_pocket and recovered and has_rejection_wick and second_tick:
                entry_min = normalize_price(ema9, tick)
                entry_max = normalize_price(spot + (candle_range * Decimal("0.15")), tick)
                trigger = normalize_price(c_high + tick, tick)
                stop_loss = normalize_price(min(c_low, ema21) - tick, tick)
                risk_pts = max(base_risk, entry_max - stop_loss)
                stop_loss = normalize_price(entry_max - risk_pts, tick)

                t1 = normalize_price(entry_max + (risk_pts * Decimal("1.5")), tick)
                t2 = normalize_price(entry_max + (risk_pts * Decimal("2.5")), tick)
                contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=-1)

                wick_ratio = float(lower_wick / candle_range)
                pocket_width = float(ema9 - ema21) / float(ema9) if float(ema9) > 0 else 0.0
                tech_s, mtf_s, fno_s, reg_s, conf = _dynamic_scores(
                    wick_ratio, pocket_width * 100.0, pcr_val, "LONG_CALL",
                    ctx.regime, mtf_align, vol_ratio,
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
                    ttl_seconds=180,
                    time_stop_seconds=180,
                    runner_ttl_seconds=420,
                    technical_score=tech_s,
                    mtf_score=mtf_s,
                    fno_score=fno_s,
                    regime_score=reg_s,
                    overall_confidence=conf,
                    rationale=[
                        f"1M pullback into 9/21 EMA pocket ({float(ema21):.1f} - {float(ema9):.1f}) with 5M trend alignment",
                        f"Rejection wick ({float(lower_wick / candle_range * 100):.0f}% of bar) followed by immediate momentum recovery",
                        f"Micro-scalp risk: {float(risk_pts):.1f} pts; trailing candidate",
                    ],
                    option_contract=contract,
                )

        # ── BEARISH PULLBACK INTO POCKET (5M Bearish + 1M EMA9 < EMA21) ──
        elif mtf_bias in ("BEARISH", "NEUTRAL") and ema9 < ema21:
            entered_pocket = c_high >= ema9 and c_high <= (ema21 + (ema21 * Decimal("0.001")))
            recovered = c_close < c_open and c_close <= ema9
            upper_wick = c_high - max(c_open, c_close)
            has_rejection_wick = (upper_wick / candle_range) >= Decimal("0.25")
            second_tick = prev_close <= ema21 and prev_close >= (ema9 - (ema9 * Decimal("0.002"))) and c_close < prev_close

            if entered_pocket and recovered and has_rejection_wick and second_tick:
                entry_min = normalize_price(spot - (candle_range * Decimal("0.15")), tick)
                entry_max = normalize_price(ema9, tick)
                trigger = normalize_price(c_low - tick, tick)
                stop_loss = normalize_price(max(c_high, ema21) + tick, tick)
                risk_pts = max(base_risk, stop_loss - entry_min)
                stop_loss = normalize_price(entry_min + risk_pts, tick)

                t1 = normalize_price(entry_min - (risk_pts * Decimal("1.5")), tick)
                t2 = normalize_price(entry_min - (risk_pts * Decimal("2.5")), tick)
                contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=1)

                wick_ratio = float(upper_wick / candle_range)
                pocket_width = float(ema21 - ema9) / float(ema21) if float(ema21) > 0 else 0.0
                tech_s, mtf_s, fno_s, reg_s, conf = _dynamic_scores(
                    wick_ratio, pocket_width * 100.0, pcr_val, "LONG_PUT",
                    ctx.regime, mtf_align, vol_ratio,
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
                    ttl_seconds=180,
                    time_stop_seconds=180,
                    runner_ttl_seconds=420,
                    technical_score=tech_s,
                    mtf_score=mtf_s,
                    fno_score=fno_s,
                    regime_score=reg_s,
                    overall_confidence=conf,
                    rationale=[
                        f"1M pullback into 9/21 EMA pocket ({float(ema9):.1f} - {float(ema21):.1f}) with 5M trend alignment",
                        f"Rejection wick ({float(upper_wick / candle_range * 100):.0f}% of bar) followed by immediate downward recovery",
                        f"Micro-scalp risk: {float(risk_pts):.1f} pts; trailing candidate",
                    ],
                    option_contract=contract,
                )

        return None
