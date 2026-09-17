"""
Trend Pullback & EMA Ribbon Retest Strategy (P1 overhaul)
Mathematical rules:
  - LONG_CALL: EMA20 > EMA50 (> EMA200 when available), ADX >= 22, Spot pulls
    back to EMA20 within 0.6% tolerance, 15M/1H MTF Bullish, VWAP aligned
  - LONG_PUT: EMA20 < EMA50 (< EMA200 when available), ADX >= 22, Spot pulls
    back to EMA20 within 0.6% tolerance, 15M/1H MTF Bearish, VWAP aligned
  - SL = Below EMA50 / swing low, T1 = 1.5R (previous high test), T2 = 3.0R (trend extension)
  - P1: fail-closed on missing EMA20/EMA50/ADX (no spot* synthetic fallbacks).
  - Demoted EMA_RIBBON scalp entry is folded here conceptually (pullback-to-
    ribbon with rejection + recovery); the standalone EMA_RIBBON scanner entry
    is disabled by default.
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
from app.signals.options_intelligence.selector import quantitative_contract_selector
from app.signals.risk_engine import resolve_realistic_atr
from app.signals.strategies.candidate import make_candidate


def _dynamic_fno_score(fno: dict, direction: str) -> float:
    try:
        raw = fno.get("pcr")
        pcr = float(raw) if raw is not None else 1.0
    except (TypeError, ValueError):
        pcr = 1.0
    if direction == "LONG_CALL":
        return round(min(88.0, max(45.0, 50.0 + ((pcr - 1.0) * 40.0))), 1)
    return round(min(88.0, max(45.0, 50.0 + ((1.0 - pcr) * 40.0))), 1)


class TrendPullbackStrategy(Strategy):
    name = "TREND_PULLBACK"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        ind = ctx.indicators
        spot = ctx.spot_price
        tick = Decimal("0.05")

        trend_data = ind.get("trend", {})
        if not isinstance(trend_data, dict):
            trend_data = {}
        # P1 fail-closed: no spot* synthetic EMA fallbacks.
        raw_ema20 = trend_data.get("ema20")
        raw_ema50 = trend_data.get("ema50")
        if raw_ema20 is None or raw_ema50 is None:
            return None
        try:
            ema20 = Decimal(str(raw_ema20))
            ema50 = Decimal(str(raw_ema50))
        except Exception:
            return None
        if ema20 <= Decimal("0") or ema50 <= Decimal("0"):
            return None
        ema200 = trend_data.get("ema200")
        # P1 fail-closed ADX: single cutoff 22 shared.
        raw_adx = ind.get("adx")
        if raw_adx is None:
            raw_adx = trend_data.get("adx")
        if raw_adx is None:
            return None
        try:
            adx = float(raw_adx)
        except (TypeError, ValueError):
            return None
        atr = resolve_realistic_atr(ctx.underlying, spot, ind)
        mtf_bias = ctx.mtf.get("overall_bias", "NEUTRAL")

        # EMA200 gate: if EMA200 available, require full ribbon alignment
        ema200_ok = True
        if ema200 is not None:
            try:
                ema200_dec = Decimal(str(ema200))
                ema200_ok = (ema20 > ema50 > ema200_dec) or (ema20 < ema50 < ema200_dec)
            except Exception:
                return None

        # ── BULLISH TREND PULLBACK (LONG_CALL) ──
        # v3.1 §6: ADX >= 22.0, EMA ribbon aligned, VWAP alignment.
        vwap_bull_ok = (ctx.vwap is None) or (spot >= ctx.vwap * Decimal("0.999"))
        trend_label = str(trend_data.get("trend") or "").upper()
        is_bull_trend = (
            (ema20 > ema50)
            and trend_label != "BEARISH"
            and ctx.regime != "TREND_DOWN"
        )
        mtf_bull_ok = (mtf_bias == "BULLISH") or (mtf_bias == "NEUTRAL" and ctx.regime == "TREND_UP")

        if spot > Decimal("0") and is_bull_trend and ema200_ok and vwap_bull_ok and mtf_bull_ok and adx >= ADX_TREND_CUTOFF:
            # Spot must be pulled back TO EMA20 (proximity only — a price
            # extended above the ribbon is chasing, not a pullback).
            dist_pct = abs(spot - ema20) / spot * Decimal("100")
            if dist_pct <= Decimal("0.6"):
                min_gap = max(atr * Decimal("0.25"), spot * Decimal("0.0006"))
                raw_trigger = spot + min_gap
                trigger = normalize_price(raw_trigger, tick)
                if abs(trigger - spot) < min_gap:
                    trigger = normalize_price(trigger + tick, tick)

                entry_min = normalize_price(spot, tick)
                entry_max = normalize_price(trigger + (atr * Decimal("0.05")), tick)
                stop_loss = normalize_price(trigger - (atr * Decimal("0.9")), tick)
                risk_pts = trigger - stop_loss
                if risk_pts > Decimal("0"):
                    t1 = normalize_price(trigger + (risk_pts * Decimal("1.5")), tick)
                    t2 = normalize_price(trigger + (risk_pts * Decimal("3.0")), tick)

                    # v3.1 §9 & §10: Quantitative Contract Selection (ATM vs ITM-1)
                    opt_res = None
                    try:
                        opt_res = quantitative_contract_selector.select_optimal_contract(
                            underlying=ctx.underlying,
                            spot_price=float(spot),
                            direction="LONG_CALL",
                            expected_move_points=float(t2 - trigger),
                            stop_loss_points=float(risk_pts),
                            target_horizon_hours=1.0,
                            candidate_types=["ITM_1", "ATM"],
                            max_theta_drag_ratio=20.0,
                            min_net_rr=1.5,
                            max_spread_pct=2.5,
                        )
                    except Exception:
                        pass

                    if opt_res is not None:
                        contract = opt_res.selected_contract
                        greeks = opt_res.selected_greeks.model_dump()
                        path_sim = opt_res.path_simulation.model_dump()
                        contract_rationale = opt_res.selection_rationale
                    else:
                        contract = resolve_option_contract(ctx.underlying, spot, "CE", strike_offset=-1)
                        greeks = None
                        path_sim = None
                        contract_rationale = ["Fallback: Selected 1-strike ITM Call (Delta ~0.60)"]

                    # Dynamic scoring earn-from-50 (P1): ADX strength + tightness of pullback.
                    tightness_bonus = max(0.0, (0.6 - float(dist_pct)) * 10.0)
                    tech_score = round(min(90.0, max(50.0, 50.0 + (max(0.0, adx - ADX_TREND_CUTOFF) * 0.8) + 8.0 + tightness_bonus)), 1)
                    mtf_score = max(50.0, float(ctx.mtf.get("alignment_score", 75.0)) - 10.0)
                    fno_score = _dynamic_fno_score(ctx.fno or {}, "LONG_CALL")
                    regime_score = 80.0 if ctx.regime == "TREND_UP" else 60.0

                    base_rationale = [
                        f"Strong Bullish Trend (ADX {adx:.1f})",
                        f"Retest of 20 EMA support (₹{ema20:,.2f})",
                        f"EMA 20 > 50 ribbon alignment (VWAP aligned)",
                        f"Multi-timeframe confirmation ({mtf_bias})",
                    ]
                    base_rationale.extend(contract_rationale[:2])

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
                        risk_reward_t2=3.0,
                        technical_score=tech_score,
                        mtf_score=mtf_score,
                        fno_score=fno_score,
                        regime_score=regime_score,
                        overall_confidence=round((tech_score * 0.4) + (mtf_score * 0.2) + (fno_score * 0.2) + (regime_score * 0.2), 1),
                        rationale=base_rationale,
                        option_contract=contract,
                        greeks=greeks,
                        path_simulation=path_sim,
                        ttl_seconds=600,
                        time_stop_seconds=180 * 60,  # v3.1 §20: 180 min max holding
                    )

        # ── BEARISH TREND PULLBACK (LONG_PUT) ──
        vwap_bear_ok = (ctx.vwap is None) or (spot <= ctx.vwap * Decimal("1.001"))
        is_bear_trend = (
            (ema20 < ema50)
            and trend_label != "BULLISH"
            and ctx.regime != "TREND_UP"
        )
        mtf_bear_ok = (mtf_bias == "BEARISH") or (mtf_bias == "NEUTRAL" and ctx.regime == "TREND_DOWN")

        if spot > Decimal("0") and is_bear_trend and ema200_ok and vwap_bear_ok and mtf_bear_ok and adx >= ADX_TREND_CUTOFF:
            dist_pct = abs(spot - ema20) / spot * Decimal("100")
            if dist_pct <= Decimal("0.6"):
                min_gap = max(atr * Decimal("0.25"), spot * Decimal("0.0006"))
                raw_trigger = spot - min_gap
                trigger = normalize_price(raw_trigger, tick)
                if abs(spot - trigger) < min_gap:
                    trigger = normalize_price(trigger - tick, tick)

                entry_min = normalize_price(trigger - (atr * Decimal("0.05")), tick)
                entry_max = normalize_price(spot, tick)
                stop_loss = normalize_price(trigger + (atr * Decimal("0.9")), tick)
                risk_pts = stop_loss - trigger
                if risk_pts > Decimal("0"):
                    t1 = normalize_price(trigger - (risk_pts * Decimal("1.5")), tick)
                    t2 = normalize_price(trigger - (risk_pts * Decimal("3.0")), tick)

                    # v3.1 §9 & §10: Quantitative Contract Selection (ATM vs ITM-1)
                    opt_res = None
                    try:
                        opt_res = quantitative_contract_selector.select_optimal_contract(
                            underlying=ctx.underlying,
                            spot_price=float(spot),
                            direction="LONG_PUT",
                            expected_move_points=float(trigger - t2),
                            stop_loss_points=float(risk_pts),
                            target_horizon_hours=1.0,
                            candidate_types=["ITM_1", "ATM"],
                            max_theta_drag_ratio=20.0,
                            min_net_rr=1.5,
                            max_spread_pct=2.5,
                        )
                    except Exception:
                        pass

                    if opt_res is not None:
                        contract = opt_res.selected_contract
                        greeks = opt_res.selected_greeks.model_dump()
                        path_sim = opt_res.path_simulation.model_dump()
                        contract_rationale = opt_res.selection_rationale
                    else:
                        contract = resolve_option_contract(ctx.underlying, spot, "PE", strike_offset=-1)
                        greeks = None
                        path_sim = None
                        contract_rationale = ["Fallback: Selected 1-strike ITM Put (Delta ~-0.60)"]

                    tightness_bonus = max(0.0, (0.6 - float(dist_pct)) * 10.0)
                    tech_score = round(min(90.0, max(50.0, 50.0 + (max(0.0, adx - ADX_TREND_CUTOFF) * 0.8) + 8.0 + tightness_bonus)), 1)
                    mtf_score = max(50.0, float(ctx.mtf.get("alignment_score", 75.0)) - 10.0)
                    fno_score = _dynamic_fno_score(ctx.fno or {}, "LONG_PUT")
                    regime_score = 80.0 if ctx.regime == "TREND_DOWN" else 60.0

                    base_rationale = [
                        f"Strong Bearish Trend (ADX {adx:.1f})",
                        f"Retest of 20 EMA resistance (₹{ema20:,.2f})",
                        f"EMA 20 < 50 ribbon alignment (VWAP aligned)",
                        f"Multi-timeframe confirmation ({mtf_bias})",
                    ]
                    base_rationale.extend(contract_rationale[:2])

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
                        risk_reward_t2=3.0,
                        technical_score=tech_score,
                        mtf_score=mtf_score,
                        fno_score=fno_score,
                        regime_score=regime_score,
                        overall_confidence=round((tech_score * 0.4) + (mtf_score * 0.2) + (fno_score * 0.2) + (regime_score * 0.2), 1),
                        rationale=base_rationale,
                        option_contract=contract,
                        greeks=greeks,
                        path_simulation=path_sim,
                        ttl_seconds=600,
                        time_stop_seconds=180 * 60,  # v3.1 §20: 180 min max holding
                    )

        return None
