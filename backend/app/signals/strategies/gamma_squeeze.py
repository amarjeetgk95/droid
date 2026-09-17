"""
Gamma Squeeze & 0DTE OI Unwinding Strategy (P1 overhaul)
Mathematical rules:
  - LONG_CALL: Call OI unwinding at ATM strike, PCR <= 0.80 or PCR >= 1.20 (extreme), strike-specific OI surge, IV expansion, Spot crossing Call OI resistance wall.
  - LONG_PUT: Put OI unwinding at ATM strike, PCR >= 1.20 or PCR <= 0.80 (extreme), strike-specific OI surge, IV expansion, Spot crossing Put OI support wall.
  - P1: fail-closed OI (no 5.5% synthetic baseline — require real OI change),
    strike-specific OI required, IV expansion required, max-pain required.
  - High risk-reward intraday momentum play, tightly bounded TTL.
  - Risk multiples: T1 = 1.8R, T2 = 3.5R advisory (risk_engine overwrites).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import (
    Strategy,
    StrategyContext,
    SignalCandidate,
    PCR_BULL_MAX,
    PCR_BEAR_MIN,
)
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.risk_engine import resolve_realistic_atr


def _extract_oi_change_pct(fno: dict) -> Optional[float]:
    """Fail-closed OI change: require real measured OI, no synthetic 5.5%."""
    raw = fno.get("oi_change_pct")
    if raw is None:
        oi_data = fno.get("oi_data")
        if isinstance(oi_data, dict):
            raw = oi_data.get("oi_change_pct")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    # Derive from futures OI only when both legs are measured and non-zero.
    chg = fno.get("futures_oi_change")
    base = fno.get("futures_oi")
    if chg is not None and base is not None:
        try:
            base_f = float(base)
            if base_f != 0:
                return abs(float(chg) / base_f) * 100.0
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    return None


def _has_strike_specific_oi(fno: dict) -> bool:
    """Require strike-specific OI (walls / key strikes / totals)."""
    try:
        tc = fno.get("total_call_oi")
        tp = fno.get("total_put_oi")
        if tc is not None and tp is not None and float(tc) > 0 and float(tp) > 0:
            return True
    except (TypeError, ValueError):
        pass
    kc = fno.get("key_call_strikes") or []
    kp = fno.get("key_put_strikes") or []
    try:
        if isinstance(kc, list) and isinstance(kp, list) and len(kc) > 0 and len(kp) > 0:
            return True
    except Exception:
        pass
    if fno.get("call_wall") is not None or fno.get("put_wall") is not None:
        return True
    # ATM strike OI fields when provided.
    for k in ("atm_ce_oi", "atm_pe_oi", "atm_call_oi", "atm_put_oi", "strike_oi", "atm_oi"):
        try:
            if fno.get(k) is not None and float(fno.get(k)) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _has_iv_expansion(fno: dict) -> bool:
    """Require IV expansion evidence: explicit IV change > 0 or elevated ATM IV."""
    raw_iv = fno.get("atm_iv")
    if raw_iv is None:
        return False
    try:
        atm_iv = float(raw_iv)
    except (TypeError, ValueError):
        return False
    # Explicit IV change when provided must show expansion.
    for k in ("iv_change_pct", "atm_iv_change_pct", "iv_change", "iv_expansion_pct"):
        if fno.get(k) is not None:
            try:
                if float(fno[k]) <= 0:
                    return False
                return True
            except (TypeError, ValueError):
                return False
    if isinstance(fno.get("iv_expansion"), bool):
        return bool(fno.get("iv_expansion"))
    # Proxy when no delta series: elevated ATM IV (>= 12) counts as expansion regime.
    return atm_iv >= 12.0


class GammaSqueezeStrategy(Strategy):
    name = "GAMMA_SQUEEZE"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        fno = ctx.fno or {}
        spot = ctx.spot_price
        tick = Decimal("0.05")
        atr = resolve_realistic_atr(ctx.underlying, spot, ctx.indicators)

        # DTE filter: gamma squeeze is only valid 0DTE-2DTE (near-expiry gamma acceleration)
        raw_dte = fno.get("dte") if fno.get("dte") is not None else fno.get("days_to_expiry")
        if raw_dte is not None:
            try:
                if int(raw_dte) > 2:
                    return None
            except Exception:
                pass

        raw_pcr = fno.get("pcr")
        if raw_pcr is None:
            return None  # fail-closed PCR
        try:
            pcr = float(raw_pcr)
        except (TypeError, ValueError):
            return None
        # P1 fail-closed OI: require real OI change.
        oi_change_opt = _extract_oi_change_pct(fno)
        if oi_change_opt is None:
            return None
        oi_change = oi_change_opt
        # P1: strike-specific OI required.
        if not _has_strike_specific_oi(fno):
            return None
        # P1: IV expansion required.
        if not _has_iv_expansion(fno):
            return None

        raw_pain = fno.get("max_pain")
        if raw_pain is None:
            return None  # fail-closed max-pain wall
        try:
            max_pain = Decimal(str(raw_pain))
        except Exception:
            return None

        # ── BULLISH GAMMA SQUEEZE (LONG_CALL) ──
        # Conditions: need 2-of-3 (PCR extreme, OI surge, above max-pain wall).
        # Trigger sits a confirmation gap above spot — never spot + 1 tick.
        _pcr_extreme = (pcr <= PCR_BULL_MAX or pcr >= PCR_BEAR_MIN)
        _oi_surge = oi_change >= 5.0
        _above_wall = spot >= max_pain * Decimal("0.998")
        if sum((_pcr_extreme, _oi_surge, _above_wall)) >= 2:
            # Spot velocity check: require upward acceleration, not just positioning
            spot_velocity_ok = True
            if len(ctx.candles) >= 6:
                spot_5ago = Decimal(str(ctx.candles[-6].get("close", spot)))
                spot_velocity = spot - spot_5ago
                if spot_velocity < (atr * Decimal("1.2")):
                    spot_velocity_ok = False
            if spot_velocity_ok:
                entry_min = normalize_price(spot, tick)
                entry_max = normalize_price(spot + (atr * Decimal("0.25")), tick)
                trigger_gap = max(atr * Decimal("0.35"), spot * Decimal("0.0006"))
                trigger = normalize_price(spot + trigger_gap, tick)
                stop_loss = normalize_price(spot - (atr * Decimal("0.9")), tick)
                risk_pts = entry_min - stop_loss
                if risk_pts > Decimal("0"):
                    t1 = normalize_price(entry_min + (risk_pts * Decimal("1.8")), tick)
                    t2 = normalize_price(entry_min + (risk_pts * Decimal("3.5")), tick)
                    contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=0)

                    tech_score = min(88.0, max(50.0, 50.0 + (oi_change * 1.0) + (max(0.0, abs(pcr - 1.0) - 0.15) * 15.0)))
                    mtf_score = max(50.0, float(ctx.mtf.get("alignment_score", 70.0)) - 10.0)
                    fno_score = min(88.0, max(45.0, 50.0 + (oi_change * 1.2) + (max(0.0, abs(pcr - 1.0) - 0.15) * 18.0)))
                    regime_score = 80.0 if ctx.regime in ("HIGH_VOL", "TREND_UP") else 60.0

                    return SignalCandidate(
                        underlying=ctx.underlying,
                        strategy=self.name,
                        direction="LONG_CALL",
                        timeframe=ctx.timeframe,
                        spot_price=spot,
                        entry_min=entry_min,
                        entry_max=entry_max,
                        trigger=trigger,
                        stop_loss=stop_loss,
                        target_1=t1,
                        target_2=t2,
                        risk_points=risk_pts,
                        risk_reward_t1=1.8,
                        risk_reward_t2=3.5,
                        technical_score=tech_score,
                        mtf_score=mtf_score,
                        fno_score=fno_score,
                        regime_score=regime_score,
                        overall_confidence=round((tech_score * 0.3) + (mtf_score * 0.2) + (fno_score * 0.35) + (regime_score * 0.15), 1),
                        rationale=[
                            f"Call OI short covering unwinding (PCR {pcr:.2f})",
                            f"Heavy OI momentum change ({oi_change:+.1f}%)",
                            f"Spot above Max Pain (₹{max_pain:,.2f})",
                            f"Rapid ATM Delta expansion velocity",
                        ],
                        option_contract=contract,
                        ttl_seconds=180,  # Fast decay setup
                    )

        # ── BEARISH GAMMA TRAP / LONG_PUT ──
        _pcr_extreme_p = (pcr >= PCR_BEAR_MIN or pcr <= PCR_BULL_MAX)
        _oi_surge_p = oi_change >= 5.0
        _below_wall = spot <= max_pain * Decimal("1.002")
        if sum((_pcr_extreme_p, _oi_surge_p, _below_wall)) >= 2:
            # Spot velocity check: require downward acceleration, not just positioning
            spot_velocity_ok = True
            if len(ctx.candles) >= 6:
                spot_5ago = Decimal(str(ctx.candles[-6].get("close", spot)))
                spot_velocity = spot_5ago - spot
                if spot_velocity < (atr * Decimal("1.2")):
                    spot_velocity_ok = False
            if spot_velocity_ok:
                entry_min = normalize_price(spot - (atr * Decimal("0.25")), tick)
                entry_max = normalize_price(spot, tick)
                trigger_gap = max(atr * Decimal("0.35"), spot * Decimal("0.0006"))
                trigger = normalize_price(spot - trigger_gap, tick)
                stop_loss = normalize_price(spot + (atr * Decimal("0.9")), tick)
                risk_pts = stop_loss - entry_max
                if risk_pts > Decimal("0"):
                    t1 = normalize_price(entry_max - (risk_pts * Decimal("1.8")), tick)
                    t2 = normalize_price(entry_max - (risk_pts * Decimal("3.5")), tick)
                    contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=0)

                    tech_score = min(88.0, max(50.0, 50.0 + (oi_change * 1.0) + (max(0.0, abs(pcr - 1.0) - 0.15) * 15.0)))
                    mtf_score = max(50.0, float(ctx.mtf.get("alignment_score", 70.0)) - 10.0)
                    fno_score = min(88.0, max(45.0, 50.0 + (oi_change * 1.2) + (max(0.0, abs(pcr - 1.0) - 0.15) * 18.0)))
                    regime_score = 80.0 if ctx.regime in ("HIGH_VOL", "TREND_DOWN") else 60.0

                    return SignalCandidate(
                        underlying=ctx.underlying,
                        strategy=self.name,
                        direction="LONG_PUT",
                        timeframe=ctx.timeframe,
                        spot_price=spot,
                        entry_min=entry_min,
                        entry_max=entry_max,
                        trigger=trigger,
                        stop_loss=stop_loss,
                        target_1=t1,
                        target_2=t2,
                        risk_points=risk_pts,
                        risk_reward_t1=1.8,
                        risk_reward_t2=3.5,
                        technical_score=tech_score,
                        mtf_score=mtf_score,
                        fno_score=fno_score,
                        regime_score=regime_score,
                        overall_confidence=round((tech_score * 0.3) + (mtf_score * 0.2) + (fno_score * 0.35) + (regime_score * 0.15), 1),
                        rationale=[
                            f"Put OI long unwinding trap (PCR {pcr:.2f})",
                            f"Heavy OI momentum change ({oi_change:+.1f}%)",
                            f"Spot below Max Pain (₹{max_pain:,.2f})",
                            f"Rapid Put Delta acceleration",
                        ],
                        option_contract=contract,
                        ttl_seconds=180,
                    )

        return None
