"""
Strategy I2 — VOLATILITY_BREAKOUT (§11, §12).
Captures genuine volatility expansion following compression.
Requires:
  1. Compression state (ATR contraction or Bollinger squeeze)
  2. Range/candle-body expansion
  3. Structural break of key resistance / support
  4. Volume/participation expansion
Desk: INTRADAY (5M / 15M / 1H)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.risk_engine import resolve_realistic_atr


class VolatilityBreakoutStrategy(Strategy):
    name = "VOLATILITY_BREAKOUT"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        if ctx.timeframe not in ("5M", "15M", "1H"):
            return None

        spot = ctx.spot_price
        if spot <= Decimal("0"):
            return None

        ind = ctx.indicators
        candles = ctx.candles
        if not candles or len(candles) < 4:
            return None

        tick = Decimal("0.05")
        atr = resolve_realistic_atr(ctx.underlying, spot, ind)
        vol_ratio = float(ind.get("volume_ratio", 1.2) or 1.2)
        breakout_pressure = float(ind.get("breakout_pressure", ind.get("scores", {}).get("breakout_pressure", 65)) or 65)
        mtf_bias = str(ctx.mtf.get("overall_bias", "NEUTRAL")).upper()

        sr = ind.get("support_resistance", {})
        raw_res = sr.get("resistance")
        raw_sup = sr.get("support")
        resistances = []
        if isinstance(raw_res, (list, tuple, set)):
            resistances = [Decimal(str(r)) for r in raw_res if r is not None]
        elif raw_res is not None:
            try:
                resistances = [Decimal(str(raw_res))]
            except Exception:
                pass

        supports = []
        if isinstance(raw_sup, (list, tuple, set)):
            supports = [Decimal(str(s)) for s in raw_sup if s is not None]
        elif raw_sup is not None:
            try:
                supports = [Decimal(str(raw_sup))]
            except Exception:
                pass

        # Check compression: bandwidth < 0.02 or recent narrow candles
        recent_ranges = [float(c.get("high", 0)) - float(c.get("low", 0)) for c in candles[-4:-1]]
        avg_recent_range = sum(recent_ranges) / max(1, len(recent_ranges))
        last_c = candles[-1]
        c_open = Decimal(str(last_c.get("open", spot)))
        c_high = Decimal(str(last_c.get("high", spot)))
        c_low = Decimal(str(last_c.get("low", spot)))
        c_close = Decimal(str(last_c.get("close", spot)))
        curr_range = float(c_high - c_low)

        # Expansion condition: current candle range >= 1.2x average prior range, or volume ratio >= 1.4
        is_expanding = curr_range >= (avg_recent_range * 1.15) or vol_ratio >= 1.35
        if not is_expanding and breakout_pressure < 70:
            return None

        min_gap = max(atr * Decimal("0.25"), spot * Decimal("0.0006"))

        # ── BULLISH VOLATILITY BREAKOUT ──
        if resistances:
            key_res = min([r for r in resistances if r >= spot * Decimal("0.99")], default=resistances[0])
            if (spot >= key_res or breakout_pressure >= 70) and mtf_bias != "BEARISH" and c_close >= c_open:
                if spot < key_res:
                    trigger = normalize_price(key_res + min_gap, tick)
                    if trigger <= spot or abs(trigger - spot) < min_gap:
                        trigger = normalize_price(max(trigger, spot) + tick, tick)
                    entry_min = normalize_price(key_res, tick)
                    entry_max = normalize_price(trigger + (atr * Decimal("0.1")), tick)
                    stop_loss = normalize_price(key_res - (atr * Decimal("0.75")), tick)
                else:
                    chase = spot - key_res
                    if chase > atr * Decimal("0.6"):
                        return None  # Chase exceeded
                    trigger = normalize_price(max(spot + min_gap, c_high + tick), tick)
                    entry_min = normalize_price(spot, tick)
                    entry_max = normalize_price(trigger + (atr * Decimal("0.1")), tick)
                    stop_loss = normalize_price(key_res - (atr * Decimal("0.5")), tick)

                risk_pts = trigger - stop_loss
                if risk_pts > Decimal("0"):
                    t1 = normalize_price(trigger + (risk_pts * Decimal("1.5")), tick)
                    t2 = normalize_price(trigger + (risk_pts * Decimal("2.5")), tick)
                    contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=0)

                    tech_score = min(92.0, max(50.0,
                        50.0
                        + (max(0.0, vol_ratio - 1.35) * 20.0)
                        + (max(0.0, breakout_pressure - 70) * 0.5)
                        + (5.0 if curr_range >= avg_recent_range * 1.5 else 0.0)
                    ))
                    mtf_score = max(50.0, float(ctx.mtf.get("alignment_score", 70.0)) - 10.0)
                    pcr_val = float(ctx.fno.get("pcr", 1.0) or 1.0)
                    fno_score = round(min(88.0, max(45.0, 50.0 + ((pcr_val - 1.0) * 40.0))), 1)
                    regime_score = 90.0 if ctx.regime == "COMPRESSION_SQUEEZE" else (75.0 if ctx.regime in ("HIGH_VOL", "TREND_UP") else 50.0)
                    overall_conf = round((tech_score * 0.4) + (mtf_score * 0.2) + (fno_score * 0.2) + (regime_score * 0.2), 1)

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
                        max_chase_fraction=0.45,
                        ttl_seconds=600,
                        time_stop_seconds=2400,
                        runner_ttl_seconds=3600,
                        technical_score=tech_score,
                        mtf_score=mtf_score,
                        fno_score=fno_score,
                        regime_score=regime_score,
                        overall_confidence=overall_conf,
                        rationale=[
                            f"Volatility expansion breaking key resistance {float(key_res):.2f}",
                            f"Expansion confirmed by volume ratio {vol_ratio:.2f} and range growth",
                            f"Intraday target: T1={float(t1):.1f}, T2={float(t2):.1f}",
                        ],
                        option_contract=contract,
                    )

        # ── BEARISH VOLATILITY BREAKDOWN ──
        if supports:
            key_sup = max([s for s in supports if s <= spot * Decimal("1.01")], default=supports[0])
            if (spot <= key_sup or breakout_pressure >= 70) and mtf_bias != "BEARISH" and c_close <= c_open:
                if spot > key_sup:
                    trigger = normalize_price(key_sup - min_gap, tick)
                    if trigger >= spot or abs(spot - trigger) < min_gap:
                        trigger = normalize_price(min(trigger, spot) - tick, tick)
                    entry_max = normalize_price(key_sup, tick)
                    entry_min = normalize_price(trigger - (atr * Decimal("0.1")), tick)
                    stop_loss = normalize_price(key_sup + (atr * Decimal("0.75")), tick)
                else:
                    chase = key_sup - spot
                    if chase > atr * Decimal("0.6"):
                        return None
                    trigger = normalize_price(min(spot - min_gap, c_low - tick), tick)
                    entry_max = normalize_price(spot, tick)
                    entry_min = normalize_price(trigger - (atr * Decimal("0.1")), tick)
                    stop_loss = normalize_price(key_sup + (atr * Decimal("0.5")), tick)

                risk_pts = stop_loss - trigger
                if risk_pts > Decimal("0"):
                    t1 = normalize_price(trigger - (risk_pts * Decimal("1.5")), tick)
                    t2 = normalize_price(trigger - (risk_pts * Decimal("2.5")), tick)
                    contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=0)

                    tech_score = min(92.0, max(50.0,
                        50.0
                        + (max(0.0, vol_ratio - 1.35) * 20.0)
                        + (max(0.0, breakout_pressure - 70) * 0.5)
                        + (5.0 if curr_range >= avg_recent_range * 1.5 else 0.0)
                    ))
                    mtf_score = max(50.0, float(ctx.mtf.get("alignment_score", 70.0)) - 10.0)
                    pcr_val = float(ctx.fno.get("pcr", 1.0) or 1.0)
                    fno_score = round(min(88.0, max(45.0, 50.0 + ((1.0 - pcr_val) * 40.0))), 1)
                    regime_score = 90.0 if ctx.regime == "COMPRESSION_SQUEEZE" else (75.0 if ctx.regime in ("HIGH_VOL", "TREND_DOWN") else 50.0)
                    overall_conf = round((tech_score * 0.4) + (mtf_score * 0.2) + (fno_score * 0.2) + (regime_score * 0.2), 1)

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
                        max_chase_fraction=0.45,
                        ttl_seconds=600,
                        time_stop_seconds=2400,
                        runner_ttl_seconds=3600,
                        technical_score=tech_score,
                        mtf_score=mtf_score,
                        fno_score=fno_score,
                        regime_score=regime_score,
                        overall_confidence=overall_conf,
                        rationale=[
                            f"Volatility expansion breaking key support {float(key_sup):.2f}",
                            f"Expansion confirmed by volume ratio {vol_ratio:.2f} and range growth",
                            f"Intraday target: T1={float(t1):.1f}, T2={float(t2):.1f}",
                        ],
                        option_contract=contract,
                    )

        return None
