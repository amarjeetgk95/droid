"""
MICRO_MOMENTUM Strategy (§8)
Timeframe: 1M
Detection:
  - 5-candle tight consolidation range
  - Range breakout with volume > 1.8x 20-period volume MA
  - RSI > 60 bullish / RSI < 40 bearish
  - Anti-chase ceiling: max_chase_fraction = 0.50R (HIGH_VOL: 0.35R)
  - TTL: Original = 90s, Runner = 240s
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract


class MicroMomentumStrategy(Strategy):
    name = "MICRO_MOMENTUM"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        if ctx.timeframe != "1M":
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

        # Volume condition: volume > 1.8x 20-period volume MA
        cur_vol = float(last_c.get("volume", 0))
        vol_ma = ctx.volume_ma_20
        if vol_ma is None:
            vols = [float(c.get("volume", 0)) for c in candles[-21:-1]] if len(candles) >= 21 else []
            vol_ma = (sum(vols) / len(vols)) if vols else 1.0

        if vol_ma > 0 and cur_vol < (vol_ma * 1.8):
            return None

        # RSI Momentum filter
        rsi_val = float(ctx.indicators.get("rsi", 50.0))
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

        # ── BULLISH BREAKOUT (Close breaks above consolidation high) ──
        if c_close > consolidation_high and rsi_val >= 60.0:
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
                max_chase_fraction=max_chase,
                ttl_seconds=90,
                time_stop_seconds=90,
                runner_ttl_seconds=240,
                technical_score=85.0,
                mtf_score=75.0,
                fno_score=75.0,
                regime_score=85.0 if ctx.regime in ("TREND_UP", "HIGH_VOL") else 70.0,
                overall_confidence=82.0,
                rationale=[
                    f"5-bar micro consolidation range ({float(consolidation_low):.1f} - {float(consolidation_high):.1f}) broken bullish",
                    f"Volume explosion: {int(cur_vol)} (>{float(vol_ma*1.8):.0f}, 1.8x MA threshold satisfied)",
                    f"RSI expansion at {rsi_val:.1f}; anti-chase fraction within {max_chase}R ceiling",
                ],
                option_contract=contract,
            )

        # ── BEARISH BREAKOUT (Close breaks below consolidation low) ──
        elif c_close < consolidation_low and rsi_val <= 40.0:
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
                max_chase_fraction=max_chase,
                ttl_seconds=90,
                time_stop_seconds=90,
                runner_ttl_seconds=240,
                technical_score=85.0,
                mtf_score=75.0,
                fno_score=75.0,
                regime_score=85.0 if ctx.regime in ("TREND_DOWN", "HIGH_VOL") else 70.0,
                overall_confidence=82.0,
                rationale=[
                    f"5-bar micro consolidation range ({float(consolidation_low):.1f} - {float(consolidation_high):.1f}) broken bearish",
                    f"Volume explosion: {int(cur_vol)} (>{float(vol_ma*1.8):.0f}, 1.8x MA threshold satisfied)",
                    f"RSI contraction at {rsi_val:.1f}; anti-chase fraction within {max_chase}R ceiling",
                ],
                option_contract=contract,
            )

        return None
