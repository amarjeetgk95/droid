"""
Strategy I1 — REGIME_ADAPTIVE_TREND (§10, P1 overhaul).
Primary intraday macro directional engine. Focuses on higher-timeframe trend alignment (15M / 1H),
macro market structure (HH_HL or LH_LL), and trend strength (ADX >= 22, single shared cutoff).
Desk: INTRADAY (5M / 15M / 1H)
P1: fail-closed ADX (no 25.0 default), dynamic earn-from-50 scoring.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import (
    Strategy,
    StrategyContext,
    SignalCandidate,
    ADX_TREND_CUTOFF,
)
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.features.structure import extract_market_structure
from app.signals.features.ema_features import extract_ema_features


def _dynamic_scores(
    adx_val: float,
    ema_fast_slope: float,
    pcr: float,
    direction: str,
    regime: str,
    mtf_align: float,
    vol_ratio: Optional[float] = None,
) -> tuple[float, float, float, float, float]:
    # Technical: earn from 50 on ADX strength + EMA slope + expansion.
    tech = 50.0 + (max(0.0, adx_val - ADX_TREND_CUTOFF) * 1.2) + (min(6.0, abs(ema_fast_slope) * 40.0))
    if vol_ratio is not None:
        tech += max(0.0, vol_ratio - 1.2) * 8.0
    tech_score = round(min(90.0, max(50.0, tech)), 1)
    mtf_score = round(max(50.0, float(mtf_align) - 10.0), 1)
    if direction == "LONG_CALL":
        fno_score = round(min(88.0, max(45.0, 50.0 + ((pcr - 1.0) * 40.0))), 1)
    else:
        fno_score = round(min(88.0, max(45.0, 50.0 + ((1.0 - pcr) * 40.0))), 1)
    if direction == "LONG_CALL":
        regime_score = 85.0 if regime == "TREND_UP" else (70.0 if regime == "HIGH_VOL" else 55.0)
    else:
        regime_score = 85.0 if regime == "TREND_DOWN" else (70.0 if regime == "HIGH_VOL" else 55.0)
    overall = round(0.40 * tech_score + 0.20 * mtf_score + 0.20 * fno_score + 0.20 * regime_score, 1)
    return tech_score, mtf_score, fno_score, regime_score, overall


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

        # P1: Check Trend Strength (ADX >= 22, fail-closed, no 25.0 default).
        adx_val: Optional[float] = None
        if "trend" in ind and isinstance(ind["trend"], dict) and ind["trend"].get("adx") is not None:
            try:
                adx_val = float(ind["trend"].get("adx"))
            except (TypeError, ValueError):
                adx_val = None
        elif ind.get("adx") is not None:
            try:
                adx_val = float(ind.get("adx"))
            except (TypeError, ValueError):
                adx_val = None
        if adx_val is None:
            return None

        if adx_val < ADX_TREND_CUTOFF:
            return None

        # Check Multi-Timeframe Alignment
        mtf_bias = str(ctx.mtf.get("overall_bias", "NEUTRAL")).upper()
        mtf_score_raw = float(ctx.mtf.get("alignment_score", 70.0))

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

        # F&O + volume context for dynamic scoring (fail-open scoring only).
        try:
            pcr_val = float(ctx.fno.get("pcr", 1.0) or 1.0)
        except (TypeError, ValueError):
            pcr_val = 1.0
        vol_ratio: Optional[float] = None
        try:
            vr = ind.get("volume_ratio")
            if vr is None and isinstance(ind.get("volume"), dict):
                vr = ind["volume"].get("relative_volume")
            if vr is not None:
                vol_ratio = float(vr)
        except (TypeError, ValueError):
            vol_ratio = None

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

            tech_s, mtf_s, fno_s, reg_s, conf = _dynamic_scores(
                adx_val, float(ema_feat.fast_slope or 0.0), pcr_val, "LONG_CALL",
                ctx.regime, mtf_score_raw, vol_ratio,
            )
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
                technical_score=tech_s,
                mtf_score=mtf_s,
                fno_score=fno_s,
                regime_score=reg_s,
                overall_confidence=conf,
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

            tech_s, mtf_s, fno_s, reg_s, conf = _dynamic_scores(
                adx_val, float(ema_feat.fast_slope or 0.0), pcr_val, "LONG_PUT",
                ctx.regime, mtf_score_raw, vol_ratio,
            )
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
                technical_score=tech_s,
                mtf_score=mtf_s,
                fno_score=fno_s,
                regime_score=reg_s,
                overall_confidence=conf,
                rationale=[
                    f"Higher-timeframe bearish trend alignment with ADX={adx_val:.1f}",
                    f"EMA ribbon bearish ordered (fast slope: {ema_feat.fast_slope:+.2f}%)",
                    f"Intraday macro trend target: T1={float(t1):.1f}, T2={float(t2):.1f}",
                ],
                option_contract=contract,
            )

        return None
