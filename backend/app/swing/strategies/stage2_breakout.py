"""
Stage 2 / 4 Trend Options Strategy (v6.0 Options Overhaul).
Detects Stan Weinstein / Mark Minervini Stage 2 structural breakouts (CE)
and Stage 4 structural breakdowns (PE) on the underlying index.
Strategies: STAGE2_CE, STAGE2_PE.
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


class Stage2OptionsStrategy(BaseSwingStrategy):
    strategy_id = "STAGE2_CE"
    strategy_name = "Stage 2 Trend Breakout"

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
        if len(candles) < 40 or features.sma_50 is None:
            return None

        spot = spot_price if spot_price > 0 else features.close
        if spot <= 0:
            return None

        is_bullish = features.price_above_sma50
        direction: Literal["LONG_CALL", "LONG_PUT"] = "LONG_CALL" if is_bullish else "LONG_PUT"
        strategy_id = "STAGE2_CE" if is_bullish else "STAGE2_PE"
        opt_type: Literal["CE", "PE"] = "CE" if is_bullish else "PE"

        if is_bullish:
            if features.dist_from_52w_high_pct < -15.0:
                return None
            trigger = features.pivot_breakout_level if features.pivot_breakout_level > 0 else features.recent_swing_high
            structural_stop = features.recent_swing_low
            stop_dist = max(features.atr_14 * 1.2, trigger - structural_stop)
            spot_stop = round(trigger - stop_dist, 2)
            expected_move = max(features.atr_14 * 3.0, stop_dist * 2.2)
        else:
            trigger = features.recent_swing_low
            structural_stop = features.recent_swing_high
            stop_dist = max(features.atr_14 * 1.2, structural_stop - trigger)
            spot_stop = round(trigger + stop_dist, 2)
            expected_move = max(features.atr_14 * 3.0, stop_dist * 2.2)

        if stop_dist <= 0:
            return None

        chain_quotes: dict[float, float] = {}
        if options_chain and hasattr(options_chain, "strikes"):
            for row in options_chain.strikes:
                side = row.call if is_bullish else row.put
                if side and side.ltp > 0:
                    chain_quotes[row.strike] = side.ltp

        cfg = INDEX_CONTRACT_CONFIGS.get(underlying)
        lot_size = int(cfg["lot_size"]) if cfg else 75
        expected_holding_days = 10

        selection = quantitative_contract_selector.select_optimal_contract(
            underlying=underlying,  # type: ignore
            spot_price=spot,
            direction=direction,
            expected_move_points=expected_move,
            stop_loss_points=stop_dist,
            target_horizon_hours=expected_holding_days * 6.25,
            current_iv=current_iv,
            option_chain_quotes=chain_quotes or None,
            candidate_types=["ITM_1", "ATM"],
            max_theta_drag_ratio=25.0,
        )

        if selection is None:
            return None

        greeks = selection.selected_greeks
        contract = selection.selected_contract
        live_prem = float(contract.live_premium) if getattr(contract, "live_premium", None) is not None else None
        entry_premium = max(1.0, round(live_prem or greeks.theoretical_price, 2))

        delta_mag = max(0.35, min(0.85, abs(greeks.delta)))
        premium_risk = max(5.0, round(stop_dist * delta_mag, 2))
        stop_premium = max(0.50, round(entry_premium - premium_risk, 2))
        target_1 = round(entry_premium + 1.5 * premium_risk, 2)
        target_2 = round(entry_premium + 3.0 * premium_risk, 2)

        risk_res = compute_swing_options_risk(
            entry_premium=entry_premium,
            stop_premium=stop_premium,
            target_premium_1=target_1,
            target_premium_2=target_2,
            lot_size=lot_size,
            unit_theta_day=greeks.theta_day,
            portfolio_equity=portfolio_equity,
        )

        implied_move = round(entry_premium / delta_mag, 1) if delta_mag > 0 else expected_move
        iv_edge = compute_iv_edge(expected_move, implied_move)
        dte = max(1, (contract.expiry_date - __import__("datetime").date.today()).days) if contract.expiry_date else 12

        score = calculate_setup_score(
            features=features,
            regime=regime,
            direction=direction,
            delta=greeks.delta,
            theta_drag_ratio=getattr(selection.all_candidates[0], "theta_drag_ratio", 15.0),
            iv_percentile=iv_percentile,
            iv_edge=iv_edge,
            spread_pct=1.0,
            open_interest=5000,
            risk_reward_t1=risk_res.risk_reward_t1,
            dte=dte,
            expected_holding_days=expected_holding_days,
        )

        validity = TradeValidity(
            underlying_valid=True,
            option_valid=selection.is_viable,
            portfolio_valid=risk_res.is_viable,
            execution_valid=True,
            overall_valid=(selection.is_viable and risk_res.is_viable),
            rejection_reasons=[] if (selection.is_viable and risk_res.is_viable) else selection.non_viability_reasons + ([risk_res.rejection_reason] if risk_res.rejection_reason else []),
        )

        tech_reasons = [
            f"Stage 2/4 trend confirmation: Spot (₹{spot:.2f}) vs 50 SMA (₹{features.sma_50:.2f})",
            f"Breaking multi-week structural level at ₹{trigger:.2f}",
            f"Volume RVOL: {features.rvol:.2f}",
        ]
        contract_sym = getattr(contract, "broker_symbol", "") or getattr(contract, "symbol", "")
        options_reasons = [
            f"Contract: {contract_sym} ({selection.selected_strike_type})",
            f"Delta: {greeks.delta:.2f}, Daily Theta: ₹{greeks.theta_day:.2f}/unit",
            f"Premium Entry: ₹{entry_premium:.2f}, Stop: ₹{stop_premium:.2f}, T1: ₹{target_1:.2f} (1.5R)",
        ]
        risk_reasons = [
            f"Risk/Lot: ₹{risk_res.premium_risk_per_lot:.0f}, Max Allocation: {risk_res.num_lots} lots",
            f"Total Premium: ₹{risk_res.total_premium_outlay:.0f} ({risk_res.capital_at_risk_pct:.1f}% equity risk)",
        ]
        invalidation = [
            f"Spot invalidation level ₹{spot_stop:.2f} breaches setup",
            f"Option premium falling below ₹{stop_premium:.2f} closes trade",
            f"Holding window exceeded ({expected_holding_days} days) triggers time stop",
        ]

        is_regime_blocked = (is_bullish and regime.regime == "BEAR") or (not is_bullish and regime.regime == "BULL")
        if is_regime_blocked:
            risk_reasons.insert(0, f"Regime {regime.regime} blocks unhedged {direction}. Gated on Radar.")

        if not validity.overall_valid or is_regime_blocked:
            state = "BLOCKED"
        elif (is_bullish and spot >= trigger) or (not is_bullish and spot <= trigger):
            state = "TRIGGERED"
        elif abs(spot - trigger) / trigger <= 0.015:
            state = "READY"
        else:
            state = "WATCH"

        return SwingSetup(
            underlying=underlying,
            direction=direction,
            option_type=opt_type,
            strategy=strategy_id,  # type: ignore
            strike=selection.selected_strike,
            expiry_date=contract.expiry_date.isoformat() if contract.expiry_date else "",
            contract_symbol=contract_sym,
            lot_size=lot_size,
            expected_holding_days=expected_holding_days,
            dte=dte,
            spot_price=spot,
            spot_trigger=round(trigger, 2),
            spot_stop=round(spot_stop, 2),
            daily_atr=features.atr_14,
            entry_premium=entry_premium,
            stop_premium=stop_premium,
            target_premium_1=target_1,
            target_premium_2=target_2,
            premium_risk_per_lot=risk_res.premium_risk_per_lot,
            iv=current_iv,
            iv_percentile=iv_percentile,
            iv_regime=regime.iv_regime,
            greeks=greeks.model_dump(),
            theta_drag_ratio=getattr(selection.all_candidates[0], "theta_drag_ratio", 15.0),
            score=score,
            trade_validity=validity,
            strike_selection_rationale=selection.selection_rationale,
            strike_selection_score=selection.selection_score,
            liquidity_score=score.liquidity,
            execution_score=score.liquidity,
            market_regime=regime.regime,
            technical_reasons=tech_reasons,
            options_reasons=options_reasons,
            risk_reasons=risk_reasons,
            invalidation_rules=invalidation,
            signal_state=state,
        )


Stage2BreakoutStrategy = Stage2OptionsStrategy

