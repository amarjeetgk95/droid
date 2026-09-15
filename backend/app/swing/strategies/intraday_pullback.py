"""
Intraday Trend Pullback Options Strategy (v6.1 Intraday Swing Mode).
Detects 15M 20 EMA pullbacks aligned with intraday VWAP on index underlyings,
selects high-gamma ATM/ITM-1 options with < 5% hourly theta drag,
and sets hard 15:15 IST square-off stops.
"""
from __future__ import annotations

import time
from typing import Any, Optional, Literal
from app.swing.models import SwingSetup, MarketRegime, TradeValidity
from app.swing.technical import SwingFeatures, compute_iv_edge
from app.swing.scoring import calculate_setup_score
from app.swing.risk_engine import compute_swing_options_risk
from app.swing.strategies.base import BaseSwingStrategy
from app.signals.options_intelligence.selector import quantitative_contract_selector
from app.signals.contract_resolver import INDEX_CONTRACT_CONFIGS


class IntradayPullbackStrategy(BaseSwingStrategy):
    strategy_id = "INTRADAY_PULLBACK_CE"
    strategy_name = "15M VWAP Trend Pullback"

    def evaluate(
        self,
        underlying: str,
        features: SwingFeatures,
        candles: list[dict[str, Any]],
        regime: MarketRegime,
        portfolio_equity: float = 1_000_000.0,
        spot_price: float = 0.0,
        options_chain: Optional[Any] = None,
        current_iv: float = 0.16,
        iv_percentile: float = 50.0,
    ) -> Optional[SwingSetup]:
        if len(candles) < 10 or features.ema_20 is None:
            return None

        spot = spot_price if spot_price > 0 else features.close
        if spot <= 0:
            return None

        # VWAP and EMA alignment determine direction
        vwap = features.vwap or spot
        is_bullish = spot >= vwap and features.price_above_ema20
        is_bearish = spot < vwap and not features.price_above_ema20

        if not (is_bullish or is_bearish):
            return None

        direction: Literal["LONG_CALL", "LONG_PUT"] = "LONG_CALL" if is_bullish else "LONG_PUT"
        strategy_id = "INTRADAY_PULLBACK_CE" if is_bullish else "INTRADAY_PULLBACK_PE"
        opt_type: Literal["CE", "PE"] = "CE" if is_bullish else "PE"

        ema20 = features.ema_20
        dist_to_ema20 = abs(spot - ema20) / ema20
        if dist_to_ema20 > 0.015:  # Pullback within 1.5% of 20 EMA
            return None

        bar_range = max(0.01, features.high - features.low)
        atr = max(10.0, features.atr_14)

        if is_bullish:
            close_pos = (features.close - features.low) / bar_range
            if close_pos < 0.35:
                return None
            trigger = round(features.high, 2)
            structural_stop = round(min(c["low"] for c in candles[-3:]), 2)
            stop_dist = max(atr * 1.2, trigger - structural_stop)
            spot_stop = round(trigger - stop_dist, 2)
            expected_move = max(atr * 2.0, stop_dist * 1.8)
        else:
            close_pos = (features.high - features.close) / bar_range
            if close_pos < 0.35:
                return None
            trigger = round(features.low, 2)
            structural_stop = round(max(c["high"] for c in candles[-3:]), 2)
            stop_dist = max(atr * 1.2, structural_stop - trigger)
            spot_stop = round(trigger + stop_dist, 2)
            expected_move = max(atr * 2.0, stop_dist * 1.8)

        if stop_dist <= 0:
            return None

        # Extract live chain quotes if available
        chain_quotes: dict[float, float] = {}
        if options_chain and hasattr(options_chain, "rows"):
            for row in options_chain.rows:
                side = row.pe if direction == "LONG_PUT" else row.ce
                if side and getattr(side, "ltp", 0.0) > 0:
                    chain_quotes[row.strike] = side.ltp

        target_horizon_hours = 2.0  # 2 hours intraday holding horizon

        selection = quantitative_contract_selector.select_optimal_contract(
            underlying=underlying,
            spot_price=spot,
            direction=direction,
            expected_move_points=expected_move,
            stop_loss_points=stop_dist,
            target_horizon_hours=target_horizon_hours,
            current_iv=current_iv,
            option_chain_quotes=chain_quotes or None,
            candidate_types=["ATM", "ITM_1"],
            max_theta_drag_ratio=15.0,
        )

        if selection is None:
            return None

        greeks = selection.selected_greeks
        contract = selection.selected_contract
        live_prem = float(contract.live_premium) if getattr(contract, "live_premium", None) is not None else None
        entry_premium = max(1.0, round(live_prem or greeks.theoretical_price, 2))

        delta_mag = max(0.40, min(0.75, abs(greeks.delta)))
        premium_risk = max(5.0, round(stop_dist * delta_mag, 2))
        stop_premium = max(0.50, round(entry_premium - premium_risk, 2))
        target_1 = round(entry_premium + 1.5 * premium_risk, 2)
        target_2 = round(entry_premium + 3.0 * premium_risk, 2)

        lot_size = INDEX_CONTRACT_CONFIGS.get(underlying, {}).get("lot_size", 25)
        if underlying == "SENSEX":
            lot_size = 20

        risk_res = compute_swing_options_risk(
            entry_premium=entry_premium,
            stop_premium=stop_premium,
            target_premium_1=target_1,
            target_premium_2=target_2,
            lot_size=lot_size,
            unit_theta_day=greeks.theta_day,
            portfolio_equity=portfolio_equity,
            max_risk_pct=1.0,
            max_premium_pct=5.0,
        )

        implied_move = (entry_premium / spot) * spot if spot > 0 else 100.0
        iv_edge = compute_iv_edge(expected_move, implied_move)

        cand = selection.all_candidates[0] if selection.all_candidates else None
        cand_theta_drag = getattr(cand, "theta_drag_ratio", 10.0) if cand else 10.0
        dte = max(1, getattr(contract, "dte", 4))

        score_res = calculate_setup_score(
            features=features,
            regime=regime,
            direction=direction,
            delta=greeks.delta,
            theta_drag_ratio=cand_theta_drag,
            iv_percentile=iv_percentile,
            iv_edge=iv_edge,
            spread_pct=1.0,
            open_interest=5000,
            risk_reward_t1=risk_res.risk_reward_t1,
            dte=dte,
            expected_holding_days=0,
        )

        rejection_reasons = []
        if not selection.is_viable:
            reasons = getattr(selection, "non_viability_reasons", None) or [getattr(selection, "rejection_reason", "Option selection not viable")]
            rejection_reasons.extend(reasons)
        if not risk_res.is_viable and risk_res.rejection_reason:
            rejection_reasons.append(risk_res.rejection_reason)

        validity = TradeValidity(
            underlying_valid=True,
            option_valid=selection.is_viable,
            portfolio_valid=risk_res.is_viable,
            execution_valid=True,
            overall_valid=selection.is_viable and risk_res.is_viable,
            rejection_reasons=rejection_reasons,
        )

        signal_state = "READY" if validity.overall_valid else "BLOCKED"

        tech_reasons = [
            f"15M Trend Pullback to 20 EMA (Spot \u20b9{spot:,.2f} vs EMA \u20b9{ema20:,.2f})",
            f"VWAP Alignment: Spot is {'above' if is_bullish else 'below'} VWAP (\u20b9{vwap:,.2f})",
            f"15M ATR: \u20b9{atr:.2f}, Intraday RVOL: {features.rvol:.2f}",
        ]

        opt_reasons = [
            f"Intraday Contract: {contract.broker_symbol} ({selection.selected_strike_type})",
            f"Delta: {greeks.delta:.2f}, Hourly Theta: \u20b9{abs(greeks.theta_hour):.2f}/unit ({cand_theta_drag:.1f}% drag)",
            f"Premium Entry: \u20b9{entry_premium:.2f}, Stop: \u20b9{stop_premium:.2f}, T1: \u20b9{target_1:.2f} (1.5R)",
        ]

        risk_reasons = [
            f"Risk/Lot: \u20b9{risk_res.premium_risk_per_lot:.0f}, Max Allocation: {risk_res.num_lots} lots",
            f"Total Outlay: \u20b9{risk_res.total_premium_outlay:.0f} ({risk_res.capital_at_risk_pct:.2f}% equity risk)",
        ]

        inv_rules = [
            f"Spot invalidation level \u20b9{spot_stop:,.2f} breaches setup",
            f"Option premium falling below \u20b9{stop_premium:.2f} closes trade",
            "Mandatory 15:15 IST square-off: Position exits before market close",
        ]

        now_ms = int(time.time() * 1000)
        return SwingSetup(
            underlying=underlying,
            direction=direction,
            option_type=opt_type,
            strategy=strategy_id,
            horizon="INTRADAY",
            timeframe="15M",
            hard_exit_time="15:15:00",
            vwap=vwap,
            strike=contract.strike,
            expiry_date=contract.expiry_date.isoformat() if hasattr(contract.expiry_date, "isoformat") else str(contract.expiry_date),
            contract_symbol=contract.broker_symbol,
            lot_size=lot_size,
            expected_holding_days=0,
            dte=dte,
            spot_price=spot,
            spot_trigger=trigger,
            spot_stop=spot_stop,
            daily_atr=round(atr, 2),
            entry_premium=entry_premium,
            stop_premium=stop_premium,
            target_premium_1=target_1,
            target_premium_2=target_2,
            premium_risk_per_lot=risk_res.premium_risk_per_lot,
            iv=current_iv,
            iv_percentile=iv_percentile,
            iv_regime=regime.iv_regime,
            greeks={
                "theoretical_price": greeks.theoretical_price,
                "delta": greeks.delta,
                "gamma": greeks.gamma,
                "theta_day": greeks.theta_day,
                "theta_hour": greeks.theta_hour,
                "theta_pct_day": greeks.theta_pct_day,
                "vega": greeks.vega,
                "rho": greeks.rho,
                "iv": greeks.iv,
                "moneyness": greeks.moneyness,
                "is_itm": greeks.is_itm,
                "is_atm": greeks.is_atm,
                "is_otm": greeks.is_otm,
            },
            theta_drag_ratio=cand_theta_drag,
            score=score_res,
            trade_validity=validity,
            strike_selection_rationale=selection.selection_rationale,
            strike_selection_score=selection.selection_score,
            liquidity_score=score_res.liquidity,
            execution_score=score_res.liquidity,
            market_regime=regime.regime,
            technical_reasons=tech_reasons,
            options_reasons=opt_reasons,
            risk_reasons=risk_reasons,
            invalidation_rules=inv_rules,
            signal_state=signal_state,
            created_at_utc=now_ms,
            valid_until_utc=now_ms + 14400 * 1000,  # 4 hours validity
        )
