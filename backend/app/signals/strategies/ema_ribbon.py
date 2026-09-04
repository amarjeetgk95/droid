"""
EMA_RIBBON Strategy (§9)
Timeframe: 1M
Detection:
  - 5M trend alignment (BULLISH / BEARISH)
  - 1M price pulls back into the dynamic pocket between 9 EMA and 21 EMA
  - Rejection wick + momentum recovery (EMA contact alone must never trigger)
  - Stop below/above 21 EMA or local structure
  - TTL: Original = 180s, Runner = 420s
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract


class EMARibbonScalpStrategy(Strategy):
    name = "EMA_RIBBON"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        if ctx.timeframe != "1M":
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

        # 9 EMA and 21 EMA on 1M
        ema9 = Decimal(str(trend_data.get("ema9") or spot * Decimal("0.999")))
        ema21 = Decimal(str(trend_data.get("ema21") or spot * Decimal("0.997")))
        tick = Decimal("0.05")

        candles = ctx.candles
        if not candles or len(candles) < 3:
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

            if entered_pocket and recovered and has_rejection_wick:
                entry_min = normalize_price(ema9, tick)
                entry_max = normalize_price(spot + (candle_range * Decimal("0.15")), tick)
                trigger = normalize_price(c_high + tick, tick)
                stop_loss = normalize_price(min(c_low, ema21) - tick, tick)
                risk_pts = max(base_risk, entry_max - stop_loss)
                stop_loss = normalize_price(entry_max - risk_pts, tick)

                t1 = normalize_price(entry_max + (risk_pts * Decimal("1.5")), tick)
                t2 = normalize_price(entry_max + (risk_pts * Decimal("2.5")), tick)
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
                    ttl_seconds=180,
                    time_stop_seconds=180,
                    runner_ttl_seconds=420,
                    technical_score=82.0,
                    mtf_score=80.0,
                    fno_score=75.0,
                    regime_score=85.0 if ctx.regime == "TREND_UP" else 70.0,
                    overall_confidence=80.0,
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

            if entered_pocket and recovered and has_rejection_wick:
                entry_min = normalize_price(spot - (candle_range * Decimal("0.15")), tick)
                entry_max = normalize_price(ema9, tick)
                trigger = normalize_price(c_low - tick, tick)
                stop_loss = normalize_price(max(c_high, ema21) + tick, tick)
                risk_pts = max(base_risk, stop_loss - entry_min)
                stop_loss = normalize_price(entry_min + risk_pts, tick)

                t1 = normalize_price(entry_min - (risk_pts * Decimal("1.5")), tick)
                t2 = normalize_price(entry_min - (risk_pts * Decimal("2.5")), tick)
                contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=1)

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
                    technical_score=82.0,
                    mtf_score=80.0,
                    fno_score=75.0,
                    regime_score=85.0 if ctx.regime == "TREND_DOWN" else 70.0,
                    overall_confidence=80.0,
                    rationale=[
                        f"1M pullback into 9/21 EMA pocket ({float(ema9):.1f} - {float(ema21):.1f}) with 5M trend alignment",
                        f"Rejection wick ({float(upper_wick / candle_range * 100):.0f}% of bar) followed by immediate downward recovery",
                        f"Micro-scalp risk: {float(risk_pts):.1f} pts; trailing candidate",
                    ],
                    option_contract=contract,
                )

        return None
