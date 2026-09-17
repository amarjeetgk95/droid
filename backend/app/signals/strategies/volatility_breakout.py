"""
Strategy I2 — VOLATILITY_BREAKOUT (§11, §12).
Captures genuine volatility expansion following compression.
Requires (P1 overhaul):
  1. Compression/squeeze state (BB bandwidth percentile or 3-bar ATR
     contraction, or COMPRESSION_SQUEEZE regime) — fail-closed if absent.
  2. Range/candle-body expansion.
  3. Structural CLOSE beyond key resistance/support (not intrabar spot touch).
  4. Measured volume expansion vol_ratio >= 1.5x — fail-closed if missing.
  5. Breakout pressure measured — fail-closed if missing.
Desk: INTRADAY (5M / 15M / 1H)
Single logic for BREAKOUT alias (see strategies/__init__.py).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import (
    Strategy,
    StrategyContext,
    SignalCandidate,
    extract_volume_ratio,
    extract_breakout_pressure,
    VOLUME_BREAKOUT_MIN,
)
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.risk_engine import resolve_realistic_atr
from app.signals.strategies.candidate import make_candidate


def _has_squeeze(ctx: StrategyContext, ind: dict, candles: list[dict], atr: Decimal) -> bool:
    """P1 squeeze gate: BB bandwidth percentile or 3-bar ATR contraction."""
    if ctx.regime == "COMPRESSION_SQUEEZE":
        return True
    # Explicit squeeze flags / bandwidth percentile when provided.
    for key in ("squeeze", "compression", "bb_squeeze"):
        if ind.get(key) is True:
            return True
    vol = ind.get("volatility", {}) if isinstance(ind.get("volatility"), dict) else {}
    bb = ind.get("bollinger_bands") or {}
    bw_pct = (
        ind.get("bollinger_bandwidth_percentile")
        or ind.get("bb_bandwidth_percentile")
        or (vol.get("bandwidth_percentile") if isinstance(vol, dict) else None)
        or (bb.get("bandwidth_percentile") if isinstance(bb, dict) else None)
    )
    if bw_pct is not None:
        try:
            if float(bw_pct) < 40.0:
                return True
        except (TypeError, ValueError):
            pass
    bw = (
        ind.get("bollinger_bandwidth")
        or ind.get("bb_bandwidth")
        or (vol.get("bandwidth") if isinstance(vol, dict) else None)
        or (bb.get("bandwidth") if isinstance(bb, dict) else None)
    )
    if bw is not None:
        try:
            # Bandwidth < 2% of spot counts as squeeze.
            spot_f = float(ctx.spot_price)
            if spot_f > 0 and float(bw) < 0.02 * spot_f:
                return True
        except (TypeError, ValueError):
            pass
    # 3-bar ATR contraction fallback: prior 3 ranges compressed vs older baseline.
    try:
        atr_f = float(atr)
    except Exception:
        atr_f = 0.0
    if len(candles) >= 7:
        try:
            prior3 = [float(c.get("high", 0)) - float(c.get("low", 0)) for c in candles[-4:-1]]
            older3 = [float(c.get("high", 0)) - float(c.get("low", 0)) for c in candles[-7:-4]]
            if prior3 and older3:
                avg_prior = sum(prior3) / len(prior3)
                avg_older = sum(older3) / len(older3)
                if avg_older > 0 and avg_prior < avg_older * 0.90:
                    return True
                if atr_f > 0 and avg_prior < atr_f * 1.0:
                    return True
        except Exception:
            pass
    elif len(candles) >= 4:
        try:
            recent = [float(c.get("high", 0)) - float(c.get("low", 0)) for c in candles[-4:-1]]
            if recent:
                avg_r = sum(recent) / len(recent)
                if atr_f > 0 and avg_r < atr_f * 1.0:
                    return True
        except Exception:
            pass
    return False


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
        # P1 fail-closed: no synthetic vol/pressure defaults.
        vol_ratio = extract_volume_ratio(ind)
        if vol_ratio is None:
            return None
        breakout_pressure = extract_breakout_pressure(ind)
        if breakout_pressure is None:
            return None
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

        # Fail-closed if S/R missing.
        if not resistances and not supports:
            return None

        # P1 squeeze gate (required).
        if not _has_squeeze(ctx, ind, candles, atr):
            return None

        # Check compression baseline for expansion measurement.
        recent_ranges = [float(c.get("high", 0)) - float(c.get("low", 0)) for c in candles[-4:-1]]
        avg_recent_range = sum(recent_ranges) / max(1, len(recent_ranges))
        last_c = candles[-1]
        c_open = Decimal(str(last_c.get("open", spot)))
        c_high = Decimal(str(last_c.get("high", spot)))
        c_low = Decimal(str(last_c.get("low", spot)))
        c_close = Decimal(str(last_c.get("close", spot)))
        curr_range = float(c_high - c_low)

        # Expansion condition: current candle range >= 1.1x average prior range.
        is_expanding = curr_range >= (avg_recent_range * 1.10)
        # P1: measured volume >= 1.5x required (no pressure-only bypass).
        if vol_ratio < VOLUME_BREAKOUT_MIN:
            return None
        if not is_expanding and breakout_pressure < 68:
            return None

        min_gap = max(atr * Decimal("0.25"), spot * Decimal("0.0006"))

        # ── BULLISH VOLATILITY BREAKOUT (requires CLOSE beyond level) ──
        if resistances:
            key_res = min([r for r in resistances if r >= spot * Decimal("0.99")], default=resistances[0])
            # P1: close-beyond gate — intrabar spot touch is not enough.
            if c_close >= key_res and mtf_bias != "BEARISH" and c_close >= c_open:
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

                    return make_candidate(
                        ctx,
                        strategy=self.name,
                        direction="LONG_CALL",
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

        # ── BEARISH VOLATILITY BREAKDOWN (requires CLOSE beyond level) ──
        if supports:
            key_sup = max([s for s in supports if s <= spot * Decimal("1.01")], default=supports[0])
            if c_close <= key_sup and mtf_bias != "BULLISH" and c_close <= c_open:
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

                    return make_candidate(
                        ctx,
                        strategy=self.name,
                        direction="LONG_PUT",
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
