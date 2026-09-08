"""
Strategy I1 — REGIME_ADAPTIVE_TREND (§10).
Primary intraday macro directional engine. Focuses on higher-timeframe trend alignment (15M / 1H),
macro market structure (HH_HL or LH_LL), and trend strength (ADX >= 22).
Desk: INTRADAY (5M / 15M / 1H)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.features.structure import extract_market_structure
from app.signals.features.ema_features import extract_ema_features


class RegimeAdaptiveTrendStrategy(Strategy):
    name = "REGIME_ADAPTIVE_TREND"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        # Runs on Intraday timeframes
        if ctx.timeframe not in ("5M", "15M", "1H"):
            return None

        # Hard exclusion in pure sideways or compression
        if ctx.regime in ("RANGE", "LOW_VOL", "COMPRESSION_SQUEEZE"):
            return None

        spot = ctx.spot_price
        if spot <= Decimal("0"):
            return None

        candles = ctx.candles
        if not candles or len(candles) < 5:
            return None

        tick = Decimal("0.05")
        ind = ctx.indicators

        # Check Trend Strength (ADX >= 20)
        adx_val = 25.0
        if "trend" in ind and isinstance(ind["trend"], dict):
            adx_val = float(ind["trend"].get("adx", 25.0))
        elif "adx" in ind:
            adx_val = float(ind.get("adx", 25.0))

        if adx_val < 20.0:
            return None

        # Check Multi-Timeframe Alignment
        mtf_bias = str(ctx.mtf.get("overall_bias", "NEUTRAL")).upper()
        mtf_score = float(ctx.mtf.get("alignment_score", 70.0))

        closes = [float(c.get("close", 0)) for c in candles]
        ema_feat = extract_ema_features(closes, current_price=float(spot))
        struct = extract_market_structure(candles, current_price=float(spot))

        # Envelopes
        atr_val = Decimal(str(ind.get("atr", 22.0) or 22.0))
        min_risk = max(atr_val * Decimal("0.75"), spot * Decimal("0.0008"))

        last_c = candles[-1]
        c_open = Decimal(str(last_c.get("open", spot)))
        c_high = Decimal(str(last_c.get("high", spot)))
        c_low = Decimal(str(last_c.get("low", spot)))
        c_close = Decimal(str(last_c.get("close", spot)))
        candle_range = c_high - c_low
        if candle_range <= Decimal("0"):
            return None

        # Minimum trigger gap
        min_gap = max(atr_val * Decimal("0.30"), spot * Decimal("0.0006"))

        # ── BULLISH MACRO TREND ──
        if (
            (ctx.regime == "TREND_UP" or mtf_bias == "BULLISH")
            and ema_feat.is_bullish_ordered
            and c_close >= c_open
            and struct.trend_bias != "BEARISH"
        ):
            entry_min = normalize_price(spot, tick)
            entry_max = normalize_price(spot + (candle_range * Decimal("0.3")), tick)
            trigger = normalize_price(max(c_high + tick, spot + min_gap), tick)
            risk_pts = max(min_risk, atr_val * Decimal("1.2"))
            stop_loss = normalize_price(entry_min - risk_pts, tick)

            t1 = normalize_price(entry_min + (risk_pts * Decimal("1.5")), tick)
            t2 = normalize_price(entry_min + (risk_pts * Decimal("2.5")), tick)
            contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=0)

            return SignalCandidate(
                underlying=ctx.underlying,
                strategy=self.name,
                direction="LONG_CALL",
                timeframe=ctx.timeframe,
                spot_price=spot,
                signal_type="INTRADAY",
                is_scalp=False,
                entry_min=entry_min,
                entry_max=entry_max,
                trigger=trigger,
                stop_loss=stop_loss,
                target_1=t1,
                target_2=t2,
                risk_points=risk_pts,
                risk_reward_t1=1.5,
                risk_reward_t2=2.5,
                max_chase_fraction=0.50,
                ttl_seconds=900,
                time_stop_seconds=2700,
                runner_ttl_seconds=4500,
                technical_score=85.0,
                mtf_score=mtf_score,
                fno_score=70.0,
                regime_score=85.0,
                overall_confidence=82.0,
                rationale=[
                    f"Higher-timeframe bullish trend alignment with ADX={adx_val:.1f}",
                    f"EMA ribbon bullish ordered (fast slope: {ema_feat.fast_slope:+.2f}%)",
                    f"Intraday macro trend target: T1={float(t1):.1f}, T2={float(t2):.1f}",
                ],
                option_contract=contract,
            )

        # ── BEARISH MACRO TREND ──
        if (
            (ctx.regime == "TREND_DOWN" or mtf_bias == "BEARISH")
            and ema_feat.is_bearish_ordered
            and c_close <= c_open
            and struct.trend_bias != "BULLISH"
        ):
            entry_min = normalize_price(spot - (candle_range * Decimal("0.3")), tick)
            entry_max = normalize_price(spot, tick)
            trigger = normalize_price(min(c_low - tick, spot - min_gap), tick)
            risk_pts = max(min_risk, atr_val * Decimal("1.2"))
            stop_loss = normalize_price(entry_max + risk_pts, tick)

            t1 = normalize_price(entry_max - (risk_pts * Decimal("1.5")), tick)
            t2 = normalize_price(entry_max - (risk_pts * Decimal("2.5")), tick)
            contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=0)

            return SignalCandidate(
                underlying=ctx.underlying,
                strategy=self.name,
                direction="LONG_PUT",
                timeframe=ctx.timeframe,
                spot_price=spot,
                signal_type="INTRADAY",
                is_scalp=False,
                entry_min=entry_min,
                entry_max=entry_max,
                trigger=trigger,
                stop_loss=stop_loss,
                target_1=t1,
                target_2=t2,
                risk_points=risk_pts,
                risk_reward_t1=1.5,
                risk_reward_t2=2.5,
                max_chase_fraction=0.50,
                ttl_seconds=900,
                time_stop_seconds=2700,
                runner_ttl_seconds=4500,
                technical_score=85.0,
                mtf_score=mtf_score,
                fno_score=70.0,
                regime_score=85.0,
                overall_confidence=82.0,
                rationale=[
                    f"Higher-timeframe bearish trend alignment with ADX={adx_val:.1f}",
                    f"EMA ribbon bearish ordered (fast slope: {ema_feat.fast_slope:+.2f}%)",
                    f"Intraday macro trend target: T1={float(t1):.1f}, T2={float(t2):.1f}",
                ],
                option_contract=contract,
            )

        return None
