"""Options Intelligence & Strike Selection Model for DROID ML Engine.

Implements Section 16 of the DROID ML Production & Research Specification.
Evaluates option strikes (ITM-1, ATM, OTM-1) using analytical Black-Scholes Greeks,
second-order Taylor expansion (Delta-Gamma), and theta decay over estimated holding time.
Selects the optimal strike based on Maximum Risk-Adjusted Expected Value (EV).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from app.signals.contract_resolver import INDEX_CONTRACT_CONFIGS
from app.signals.options_intelligence.greeks import BlackScholesGreeks, GreeksResult


@dataclass(frozen=True)
class StrikeEvaluation:
    strike: float
    strike_type: Literal["ITM_1", "ATM", "OTM_1"]
    option_type: Literal["CE", "PE"]
    entry_premium: float
    greeks: GreeksResult
    expected_gain_at_t1: float
    expected_loss_at_sl: float
    expected_timeout_pnl: float
    gross_ev_per_share: float
    risk_reward_ratio: float
    is_recommended: bool


class OptionsIntelligenceModel:
    """
    Selects optimal option contract strike using second-order Delta-Gamma-Theta holding returns.
    """

    def __init__(self):
        # Defaults are ASSUMPTIONS (not measured IV). Callers MUST check
        # iv_available/dte_available in evaluate_strikes output.
        self.default_iv = 0.14
        self.default_r = 0.065
        self.default_q = 0.012

    def get_strike_interval(self, underlying: str) -> float:
        cfg = INDEX_CONTRACT_CONFIGS.get(underlying.upper())
        if cfg:
            return float(cfg["strike_interval"])
        if "BANK" in underlying.upper():
            return 100.0
        if "SENSEX" in underlying.upper():
            return 100.0
        return 50.0

    def get_lot_size(self, underlying: str) -> int:
        cfg = INDEX_CONTRACT_CONFIGS.get(underlying.upper())
        if cfg:
            return int(cfg["lot_size"])
        if "BANK" in underlying.upper():
            return 30
        if "SENSEX" in underlying.upper():
            return 10
        return 75

    def evaluate_strikes(
        self,
        underlying: str,
        direction: str,
        spot_price: float,
        target_1: float,
        stop_loss: float,
        p_target: float,
        p_stop: float,
        p_timeout: float,
        dte_days: float | None = None,
        atm_iv: float | None = None,
        expected_bars_held: int = 15,
    ) -> Dict[str, Any]:
        """
        Evaluates candidate strikes (ITM-1, ATM, OTM-1) and selects the optimal strike.
        
        Args:
            underlying: Symbol (NIFTY, BANKNIFTY, SENSEX)
            direction: "LONG_CALL", "CALL", "LONG_PUT", "PUT"
            spot_price: Current spot index price
            target_1: Target 1 spot level
            stop_loss: Stop loss spot level
            p_target: Calibrated P(T1 before SL)
            p_stop: Calibrated P(SL before T1)
            p_timeout: Calibrated P(Timeout)
            dte_days: Days to expiry
            atm_iv: Implied volatility (e.g., 0.14 for 14%)
            expected_bars_held: Estimated holding period in 1-minute bars
        """
        is_call = "CALL" in direction.upper() or "BUY" in direction.upper()
        option_type: Literal["CE", "PE"] = "CE" if is_call else "PE"

        interval = self.get_strike_interval(underlying)
        lot_size = self.get_lot_size(underlying)

        # Base ATM strike rounded to nearest interval
        atm_strike = round(spot_price / interval) * interval

        if is_call:
            candidate_strikes = [
                (atm_strike - interval, "ITM_1"),
                (atm_strike, "ATM"),
                (atm_strike + interval, "OTM_1"),
            ]
            spot_move_t1 = max(0.0, target_1 - spot_price)
            spot_move_sl = -abs(spot_price - stop_loss)
        else:
            candidate_strikes = [
                (atm_strike + interval, "ITM_1"),
                (atm_strike, "ATM"),
                (atm_strike - interval, "OTM_1"),
            ]
            spot_move_t1 = -abs(spot_price - target_1)  # Drop in spot benefits PUT
            spot_move_sl = abs(stop_loss - spot_price)   # Rise in spot hurts PUT

        # Honesty: None IV/DTE are assumptions (never silent concrete numbers).
        _iv_assumed = (atm_iv is None)
        _dte_assumed = (dte_days is None)
        _atm_iv = float(atm_iv) if atm_iv is not None else float(self.default_iv)
        _dte_days = float(dte_days) if dte_days is not None else 3.0

        # Time elapsed in years for theta decay calculation
        holding_time_years = max(1e-5, (expected_bars_held / 375.0) / 252.0)
        t_years = max(1e-4, _dte_days / 365.0)

        evaluations: List[StrikeEvaluation] = []
        best_strike_eval: Optional[StrikeEvaluation] = None
        best_score = -float("inf")

        for strike, strike_type in candidate_strikes:
            greeks = BlackScholesGreeks.calculate_greeks(
                spot=spot_price,
                strike=strike,
                time_to_expiry_years=t_years,
                volatility=max(0.05, _atm_iv),
                option_type=option_type,
                risk_free_rate=self.default_r,
                dividend_yield=self.default_q,
            )

            premium = max(1.0, greeks.theoretical_price)

            # Second-order Taylor expansion for option price change:
            # dP = Delta * dS + 0.5 * Gamma * (dS)^2 + Theta * dt
            # Note: For PUT, Delta is negative, and spot_move_t1 is negative, so Delta * dS > 0
            # Theta is negative in ₹/day
            holding_days = expected_bars_held / 375.0
            theta_loss = abs(greeks.theta_day) * holding_days

            # 1. Target 1 outcome
            delta_gain = greeks.delta * spot_move_t1
            gamma_gain = 0.5 * greeks.gamma * (spot_move_t1 ** 2)
            raw_gain_t1 = delta_gain + gamma_gain - theta_loss
            gain_at_t1 = max(0.0, raw_gain_t1)

            # 2. Stop loss outcome
            delta_loss = greeks.delta * spot_move_sl
            gamma_loss = 0.5 * greeks.gamma * (spot_move_sl ** 2)
            raw_loss_sl = delta_loss + gamma_loss - theta_loss
            loss_at_sl = max(0.5, abs(min(0.0, raw_loss_sl)))
            # Max loss bounded by total premium paid
            loss_at_sl = min(premium, loss_at_sl)

            # 3. Timeout outcome (pure theta erosion, minimal spot change)
            timeout_pnl = -theta_loss

            # Expected Value calculation per share
            gross_ev = (p_target * gain_at_t1) - (p_stop * loss_at_sl) + (p_timeout * timeout_pnl)
            rr = (gain_at_t1 / loss_at_sl) if loss_at_sl > 0 else 1.0

            # Score strike by Risk-Adjusted EV (EV penalized by variance / max loss)
            strike_score = gross_ev / max(10.0, loss_at_sl)

            eval_obj = StrikeEvaluation(
                strike=strike,
                strike_type=strike_type,
                option_type=option_type,
                entry_premium=round(premium, 2),
                greeks=greeks,
                expected_gain_at_t1=round(gain_at_t1, 2),
                expected_loss_at_sl=round(loss_at_sl, 2),
                expected_timeout_pnl=round(timeout_pnl, 2),
                gross_ev_per_share=round(gross_ev, 2),
                risk_reward_ratio=round(rr, 2),
                is_recommended=False,
            )
            evaluations.append(eval_obj)

            if strike_score > best_score:
                best_score = strike_score
                best_strike_eval = eval_obj

        # Mark recommended strike
        marked_evaluations: List[Dict[str, Any]] = []
        for ev in evaluations:
            is_rec = (best_strike_eval is not None and ev.strike == best_strike_eval.strike)
            marked_evaluations.append({
                "strike": ev.strike,
                "strike_type": ev.strike_type,
                "option_type": ev.option_type,
                "entry_premium": ev.entry_premium,
                "delta": ev.greeks.delta,
                "gamma": ev.greeks.gamma,
                "theta_day": ev.greeks.theta_day,
                "vega": ev.greeks.vega,
                "expected_gain_at_t1": ev.expected_gain_at_t1,
                "expected_loss_at_sl": ev.expected_loss_at_sl,
                "gross_ev_per_share": ev.gross_ev_per_share,
                "risk_reward_ratio": ev.risk_reward_ratio,
                "is_recommended": is_rec,
            })

        chosen = best_strike_eval or evaluations[1]  # Fallback to ATM

        # Honesty: default IV/DTE are assumptions when caller uses defaults.
        # Callers pass explicit atm_iv/dte_days when measured; otherwise output
        # is marked assumption, never silent concrete numbers.
        return {
            "underlying": underlying,
            "direction": direction,
            "lot_size": lot_size,
            "selected_strike": chosen.strike,
            "selected_strike_type": chosen.strike_type,
            "selected_premium": chosen.entry_premium,
            "selected_delta": chosen.greeks.delta,
            "selected_gamma": chosen.greeks.gamma,
            "selected_theta_day": chosen.greeks.theta_day,
            "expected_gain_at_t1": chosen.expected_gain_at_t1,
            "expected_loss_at_sl": chosen.expected_loss_at_sl,
            "gross_ev_per_share": chosen.gross_ev_per_share,
            "evaluations": marked_evaluations,
            "iv_available": not _iv_assumed,
            "dte_available": not _dte_assumed,
            "assumptions": [
                *(["atm_iv-assumed-0.14-default"] if _iv_assumed else []),
                *(["dte-assumed-3.0-default"] if _dte_assumed else []),
            ],
        }


options_intelligence_model = OptionsIntelligenceModel()
