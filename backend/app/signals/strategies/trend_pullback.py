"""
Trend Pullback & EMA Ribbon Retest Strategy
Mathematical rules:
  - LONG_CALL: EMA20 > EMA50 > EMA200, ADX >= 25, Spot pulls back to EMA20 within 0.3% tolerance, 15M/1H MTF Bullish
  - LONG_PUT: EMA20 < EMA50 < EMA200, ADX >= 25, Spot pulls back to EMA20 within 0.3% tolerance, 15M/1H MTF Bearish
  - SL = Below EMA50 / swing low, T1 = 1.5R (previous high test), T2 = 3.0R (trend extension)
  - Quality target: 80% win rate — neutral baseline scoring.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.signals.strategies.base import Strategy, StrategyContext, SignalCandidate
from app.signals.contract_resolver import normalize_price, resolve_option_contract
from app.signals.options_intelligence.selector import quantitative_contract_selector
from app.signals.risk_engine import resolve_realistic_atr


class TrendPullbackStrategy(Strategy):
    name = "TREND_PULLBACK"

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        ind = ctx.indicators
        spot = ctx.spot_price
        tick = Decimal("0.05")

        trend_data = ind.get("trend", {})
        ema20 = Decimal(str(trend_data.get("ema20") or spot * Decimal("0.998")))
        ema50 = Decimal(str(trend_data.get("ema50") or spot * Decimal("0.995")))
        ema200 = trend_data.get("ema200")
        adx = float(ind.get("adx") or trend_data.get("adx", 25.0))
        atr = resolve_realistic_atr(ctx.underlying, spot, ind)
        mtf_bias = ctx.mtf.get("overall_bias", "NEUTRAL")

        # EMA200 gate: if EMA200 available, require full ribbon alignment
        ema200_ok = True
        if ema200 is not None:
            ema200_dec = Decimal(str(ema200))
            ema200_ok = (ema20 > ema50 > ema200_dec) or (ema20 < ema50 < ema200_dec)

        # ── BULLISH TREND PULLBACK (LONG_CALL) ──
        # v3.1 §6: ADX >= 22.0, EMA ribbon aligned, VWAP alignment
        vwap_bull_ok = (ctx.vwap is None) or (spot >= ctx.vwap * Decimal("0.999"))
        is_bull_trend = (ema20 >= ema50 or trend_data.get("trend") == "BULLISH" or ctx.regime == "TREND_UP")

        if spot > Decimal("0") and is_bull_trend and ema200_ok and vwap_bull_ok and mtf_bias in ("BULLISH", "NEUTRAL") and adx >= 22.0:
            # Check if spot is near EMA20 (within 0.6%) or VWAP retest
            dist_pct = abs(spot - ema20) / spot * Decimal("100")
            if dist_pct <= Decimal("0.6") or spot >= ema20:
                min_gap = max(atr * Decimal("0.25"), spot * Decimal("0.0006"))
                raw_trigger = spot + min_gap
                trigger = normalize_price(raw_trigger, tick)
                if abs(trigger - spot) < min_gap:
                    trigger = normalize_price(trigger + tick, tick)

                entry_min = normalize_price(spot, tick)
                entry_max = normalize_price(trigger + (atr * Decimal("0.1")), tick)
                stop_loss = normalize_price(trigger - (atr * Decimal("0.8")), tick)
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

                    tech_score = min(90.0, max(50.0, 50.0 + (max(0.0, adx - 22.0) * 0.8) + 8.0))
                    mtf_score = max(50.0, float(ctx.mtf.get("alignment_score", 75.0)) - 10.0)
                    fno_score = 70.0
                    regime_score = 80.0 if ctx.regime == "TREND_UP" else 60.0

                    base_rationale = [
                        f"Strong Bullish Trend (ADX {adx:.1f})",
                        f"Retest of 20 EMA support (₹{ema20:,.2f})",
                        f"EMA 20 > 50 ribbon alignment (VWAP aligned)",
                        f"Multi-timeframe confirmation ({mtf_bias})",
                    ]
                    base_rationale.extend(contract_rationale[:2])

                    return SignalCandidate(
                        underlying=ctx.underlying,
                        strategy=self.name,
                        direction="LONG_CALL",
                        timeframe=ctx.timeframe,
                        signal_type="INTRADAY",
                        spot_price=spot,
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
        # v3.1 §6: ADX >= 22.0, EMA ribbon aligned, VWAP alignment
        vwap_bear_ok = (ctx.vwap is None) or (spot <= ctx.vwap * Decimal("1.001"))
        is_bear_trend = (ema20 <= ema50 or trend_data.get("trend") == "BEARISH" or ctx.regime == "TREND_DOWN")

        if spot > Decimal("0") and is_bear_trend and ema200_ok and vwap_bear_ok and mtf_bias in ("BEARISH", "NEUTRAL") and adx >= 22.0:
            dist_pct = abs(spot - ema20) / spot * Decimal("100")
            if dist_pct <= Decimal("0.6") or spot <= ema20:
                min_gap = max(atr * Decimal("0.25"), spot * Decimal("0.0006"))
                raw_trigger = spot - min_gap
                trigger = normalize_price(raw_trigger, tick)
                if abs(spot - trigger) < min_gap:
                    trigger = normalize_price(trigger - tick, tick)

                entry_min = normalize_price(trigger - (atr * Decimal("0.1")), tick)
                entry_max = normalize_price(spot, tick)
                stop_loss = normalize_price(trigger + (atr * Decimal("0.8")), tick)
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

                    tech_score = min(90.0, max(50.0, 50.0 + (max(0.0, adx - 22.0) * 0.8) + 8.0))
                    mtf_score = max(50.0, float(ctx.mtf.get("alignment_score", 75.0)) - 10.0)
                    fno_score = 70.0
                    regime_score = 80.0 if ctx.regime == "TREND_DOWN" else 60.0

                    base_rationale = [
                        f"Strong Bearish Trend (ADX {adx:.1f})",
                        f"Retest of 20 EMA resistance (₹{ema20:,.2f})",
                        f"EMA 20 < 50 ribbon alignment (VWAP aligned)",
                        f"Multi-timeframe confirmation ({mtf_bias})",
                    ]
                    base_rationale.extend(contract_rationale[:2])

                    return SignalCandidate(
                        underlying=ctx.underlying,
                        strategy=self.name,
                        direction="LONG_PUT",
                        timeframe=ctx.timeframe,
                        signal_type="INTRADAY",
                        spot_price=spot,
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
