"""
MICRO_MOMENTUM Strategy (§8, P1 overhaul)
Timeframe: 1M
Detection:
  - 5-candle tight consolidation range
  - Range breakout with volume >= 1.5x 20-period volume MA (measured, fail-closed)
  - RSI > 60 bullish / RSI < 40 bearish
  - P1: closed 1M candle (is_new_1m_candle) + second-tick confirmation
    (prior close inside consolidation, current close beyond) required
  - Anti-chase ceiling: max_chase_fraction = 0.50R (HIGH_VOL: 0.35R)
  - TTL: Original = 90s, Runner = 240s
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import (
    Strategy,
    StrategyContext,
    SignalCandidate,
    has_closed_1m_candle,
    VOLUME_MICRO_MIN,
)
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.strategies.candidate import make_candidate


def _dynamic_scores(vol_ratio: float, rsi_val: float, direction: str, regime: str, pcr: float = 1.0) -> tuple[float, float, float, float, float]:
    # Technical earn-from-50: volume surge + RSI expansion depth.
    if direction == "LONG_CALL":
        rsi_bonus = max(0.0, rsi_val - 60.0) * 1.5
    else:
        rsi_bonus = max(0.0, 40.0 - rsi_val) * 1.5
    tech = 50.0 + (max(0.0, vol_ratio - VOLUME_MICRO_MIN) * 12.0) + min(12.0, rsi_bonus)
    tech_score = round(min(88.0, max(50.0, tech)), 1)
    mtf_score = round(max(50.0, 70.0 - 10.0), 1)
    if direction == "LONG_CALL":
        fno_score = round(min(85.0, max(45.0, 50.0 + ((pcr - 1.0) * 30.0))), 1)
    else:
        fno_score = round(min(85.0, max(45.0, 50.0 + ((1.0 - pcr) * 30.0))), 1)
    if direction == "LONG_CALL":
        regime_score = 75.0 if regime in ("TREND_UP", "HIGH_VOL") else 55.0
    else:
        regime_score = 75.0 if regime in ("TREND_DOWN", "HIGH_VOL") else 55.0
    conf = round(0.40 * tech_score + 0.20 * mtf_score + 0.20 * fno_score + 0.20 * regime_score, 1)
    return tech_score, mtf_score, fno_score, regime_score, conf


class MicroMomentumStrategy(Strategy):
    name = "MICRO_MOMENTUM"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        if ctx.timeframe != "1M":
            return None

        # P1: closed-candle gate.
        if not has_closed_1m_candle(ctx):
            return None

        # Suppress during ranging/choppy low vol regime (§15)
        if ctx.regime in ("RANGE", "LOW_VOL"):
            return None

        spot = ctx.spot_price
        if spot <= Decimal("0"):
            return None

        candles = ctx.candles
        if not candles or len(candles) < 6:
            return None

        # Prior 5 consolidation candles
        prior_5 = candles[-6:-1]
        last_c = candles[-1]

        highs = [Decimal(str(c.get("high", spot))) for c in prior_5]
        lows = [Decimal(str(c.get("low", spot))) for c in prior_5]
        consolidation_high = max(highs)
        consolidation_low = min(lows)
        consol_range = consolidation_high - consolidation_low

        if consol_range <= Decimal("0"):
            return None

        # P1 volume: volume >= 1.5x 20-period MA, fail-closed if missing.
        cur_vol = float(last_c.get("volume", 0) or 0)
        if cur_vol <= 0:
            return None
        vol_ma = ctx.volume_ma_20
        if vol_ma is None:
            vols = [float(c.get("volume", 0)) for c in candles[-21:-1]] if len(candles) >= 21 else []
            vols = [v for v in vols if v > 0]
            if not vols:
                return None  # fail-closed: no measured MA
            vol_ma = sum(vols) / len(vols)
        if vol_ma is None or vol_ma <= 0:
            return None
        vol_ratio = cur_vol / vol_ma
        if vol_ratio < VOLUME_MICRO_MIN:
            return None

        # RSI Momentum filter
        rsi_val = float(ctx.indicators.get("rsi") or ctx.indicators.get("momentum", {}).get("rsi", 50.0))
        tick = Decimal("0.05")
        is_high_vol = ctx.regime == "HIGH_VOL"
        max_chase = 0.35 if is_high_vol else 0.50

        # Instrument micro-risk envelope
        if ctx.underlying == "NIFTY":
            min_risk = Decimal("6.0")
        elif ctx.underlying == "BANKNIFTY":
            min_risk = Decimal("22.0")
        else:
            min_risk = Decimal("45.0")

        c_close = Decimal(str(last_c.get("close", spot)))
        c_open = Decimal(str(last_c.get("open", spot)))
        try:
            prev_close = Decimal(str(candles[-2].get("close", spot)))
        except Exception:
            return None
        try:
            pcr_val = float(ctx.fno.get("pcr", 1.0) or 1.0)
        except (TypeError, ValueError):
            pcr_val = 1.0

        # ── BULLISH BREAKOUT (Close breaks above consolidation high) ──
        if c_close > consolidation_high and rsi_val >= 60.0:
            # P1 second-tick confirmation: prior close was inside the range
            # (fresh breakout on closed candle, not an extended run).
            if not (consolidation_low <= prev_close <= consolidation_high):
                return None
            # Directional second tick: current bar bullish.
            if c_close < c_open:
                return None
            chase_dist = c_close - consolidation_high
            risk_pts = max(min_risk, c_close - consolidation_low)

            # Anti-chase gate: Reject if price ran away more than max_chase_fraction of R
            if chase_dist > (risk_pts * Decimal(str(max_chase))):
                return None

            entry_min = normalize_price(consolidation_high, tick)
            entry_max = normalize_price(c_close + (consol_range * Decimal("0.15")), tick)
            trigger = normalize_price(c_close + tick, tick)
            stop_loss = normalize_price(consolidation_low, tick)
            risk_pts = max(min_risk, entry_max - stop_loss)
            stop_loss = normalize_price(entry_max - risk_pts, tick)

            t1 = normalize_price(entry_max + (risk_pts * Decimal("1.5")), tick)
            t2 = normalize_price(entry_max + (risk_pts * Decimal("2.5")), tick)
            contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=-1)

            tech_score, mtf_score, fno_score, regime_score, conf_score = _dynamic_scores(
                vol_ratio, rsi_val, "LONG_CALL", ctx.regime, pcr_val
            )

            return make_candidate(
                ctx,
                strategy=self.name,
                direction="LONG_CALL",
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
                max_chase_fraction=max_chase,
                ttl_seconds=90,
                time_stop_seconds=90,
                runner_ttl_seconds=240,
                technical_score=tech_score,
                mtf_score=mtf_score,
                fno_score=fno_score,
                regime_score=regime_score,
                overall_confidence=conf_score,
                rationale=[
                    f"5-bar micro consolidation range ({float(consolidation_low):.1f} - {float(consolidation_high):.1f}) broken bullish",
                    f"Volume explosion: {int(cur_vol)} (>{float(vol_ma*1.5):.0f}, 1.5x MA threshold satisfied)",
                    f"RSI expansion at {rsi_val:.1f}; anti-chase fraction within {max_chase}R ceiling",
                ],
                option_contract=contract,
            )

        # ── BEARISH BREAKOUT (Close breaks below consolidation low) ──
        elif c_close < consolidation_low and rsi_val <= 40.0:
            if not (consolidation_low <= prev_close <= consolidation_high):
                return None
            if c_close > c_open:
                return None
            chase_dist = consolidation_low - c_close
            risk_pts = max(min_risk, consolidation_high - c_close)

            # Anti-chase gate
            if chase_dist > (risk_pts * Decimal(str(max_chase))):
                return None

            entry_min = normalize_price(c_close - (consol_range * Decimal("0.15")), tick)
            entry_max = normalize_price(consolidation_low, tick)
            trigger = normalize_price(c_close - tick, tick)
            stop_loss = normalize_price(consolidation_high, tick)
            risk_pts = max(min_risk, stop_loss - entry_min)
            stop_loss = normalize_price(entry_min + risk_pts, tick)

            t1 = normalize_price(entry_min - (risk_pts * Decimal("1.5")), tick)
            t2 = normalize_price(entry_min - (risk_pts * Decimal("2.5")), tick)
            contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=1)

            tech_score, mtf_score, fno_score, regime_score, conf_score = _dynamic_scores(
                vol_ratio, rsi_val, "LONG_PUT", ctx.regime, pcr_val
            )

            return make_candidate(
                ctx,
                strategy=self.name,
                direction="LONG_PUT",
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
                max_chase_fraction=max_chase,
                ttl_seconds=90,
                time_stop_seconds=90,
                runner_ttl_seconds=240,
                technical_score=tech_score,
                mtf_score=mtf_score,
                fno_score=fno_score,
                regime_score=regime_score,
                overall_confidence=conf_score,
                rationale=[
                    f"5-bar micro consolidation range ({float(consolidation_low):.1f} - {float(consolidation_high):.1f}) broken bearish",
                    f"Volume explosion: {int(cur_vol)} (>{float(vol_ma*1.5):.0f}, 1.5x MA threshold satisfied)",
                    f"RSI contraction at {rsi_val:.1f}; anti-chase fraction within {max_chase}R ceiling",
                ],
                option_contract=contract,
            )

        return None
