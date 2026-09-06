import math
from decimal import Decimal
import pytest

from app.signals.options_intelligence.greeks import BlackScholesGreeks, GreeksResult
from app.signals.options_intelligence.path_simulator import (
    PathDependentOptionSimulator,
    IndianOptionCosts,
)
from app.signals.options_intelligence.selector import (
    QuantitativeContractSelector,
    quantitative_contract_selector,
)
from app.signals.contract_resolver import calculate_option_buyer_sizing
from app.signals.risk_engine import StrategySetup, CentralRiskEngine


class TestBlackScholesGreeksAndIV:
    def test_put_call_parity(self):
        spot = 24500.0
        strike = 24500.0
        t_years = 7.0 / 365.0  # 7 DTE
        vol = 0.15  # 15% IV
        r = 0.065
        q = 0.012

        call_price = BlackScholesGreeks.calculate_price(spot, strike, t_years, vol, "CE", r, q)
        put_price = BlackScholesGreeks.calculate_price(spot, strike, t_years, vol, "PE", r, q)

        # Put-Call Parity: C - P = S*exp(-q*T) - K*exp(-r*T)
        lhs = call_price - put_price
        rhs = spot * math.exp(-q * t_years) - strike * math.exp(-r * t_years)
        assert abs(lhs - rhs) < 0.05, f"Put-Call parity violation: {lhs} vs {rhs}"

    def test_greeks_properties(self):
        spot = 25000.0
        strike = 25000.0
        t_years = 5.0 / 365.0
        vol = 0.14

        call_greeks = BlackScholesGreeks.calculate_greeks(spot, strike, t_years, vol, "CE")
        put_greeks = BlackScholesGreeks.calculate_greeks(spot, strike, t_years, vol, "PE")

        # Delta bounds
        assert 0.45 < call_greeks.delta < 0.55, f"ATM call delta unexpected: {call_greeks.delta}"
        assert -0.55 < put_greeks.delta < -0.45, f"ATM put delta unexpected: {put_greeks.delta}"

        # Gamma must be positive and equal for Call and Put
        assert call_greeks.gamma > 0
        assert abs(call_greeks.gamma - put_greeks.gamma) < 1e-5

        # Vega must be positive
        assert call_greeks.vega > 0
        assert abs(call_greeks.vega - put_greeks.vega) < 1e-4

        # Theta must be negative (decay)
        assert call_greeks.theta_day < 0
        assert call_greeks.theta_hour < 0
        assert put_greeks.theta_day < 0
        assert put_greeks.theta_hour < 0

        # At-the-money classification
        assert call_greeks.is_atm is True
        assert call_greeks.is_itm is False

    def test_solve_iv_roundtrip(self):
        spot = 24800.0
        strike = 25000.0  # OTM Call
        t_years = 6.0 / 365.0
        target_vol = 0.175  # 17.5%

        # Generate theoretical price
        mkt_price = BlackScholesGreeks.calculate_price(spot, strike, t_years, target_vol, "CE")

        # Recover IV
        recovered_iv = BlackScholesGreeks.solve_iv(mkt_price, spot, strike, t_years, "CE")
        assert abs(recovered_iv - target_vol) < 0.001, f"IV solver divergence: {recovered_iv} vs {target_vol}"


class TestPathDependentOptionSimulation:
    def test_indian_transaction_costs(self):
        costs = IndianOptionCosts(
            brokerage_per_order=20.0,
            default_spread_pts=1.0,
            default_slippage_pts=0.5,
        )
        friction = costs.calculate_total_costs(
            entry_premium=120.0,
            exit_premium=150.0,
            quantity=75,  # 1 lot NIFTY
        )
        assert friction["brokerage"] == 40.0
        assert friction["stt"] > 0
        assert friction["market_friction_rupees"] == (1.0 + 1.0) * 75  # spread + 2*slippage = 2.0 * 75 = 150
        assert friction["total_friction"] > 190.0

    def test_path_scenarios_evaluation(self):
        simulator = PathDependentOptionSimulator()
        spot = 24900.0
        strike = 24900.0
        target_spot = 24980.0  # +80 pts move
        stop_spot = 24860.0    # -40 pts move
        dte_days = 4.0
        iv = 0.15
        quantity = 75

        report = simulator.evaluate_candidate(
            underlying="NIFTY",
            spot=spot,
            strike=strike,
            option_type="CE",
            dte_days=dte_days,
            iv=iv,
            target_spot=target_spot,
            stop_spot=stop_spot,
            quantity=quantity,
            expected_fast_hours=0.5,
            expected_slow_hours=3.0,
        )

        # Fast target must have higher net P&L than slow target due to theta
        assert report.fast_target.net_pnl_total > report.slow_target.net_pnl_total
        # Sideways market must have negative P&L strictly from theta bleed
        assert report.sideways.net_pnl_total < 0
        assert report.sideways.theta_drag_total > 0
        # Adverse stop must be negative
        assert report.adverse_stop.net_pnl_total < 0
        # Check overall viability
        assert report.is_economically_viable is True


class TestQuantitativeContractSelector:
    def test_strike_selection_nifty_call(self):
        selector = QuantitativeContractSelector()
        result = selector.select_optimal_contract(
            underlying="NIFTY",
            spot_price=24915.0,
            direction="LONG_CALL",
            expected_move_points=65.0,
            stop_loss_points=25.0,
            target_horizon_hours=1.0,
            current_iv=0.15,
        )
        assert result is not None
        assert result.underlying == "NIFTY"
        assert result.selected_contract is not None
        assert result.selected_strike in (24850.0, 24900.0, 24950.0)
        assert len(result.all_candidates) == 3
        assert result.selection_score > 50.0

    def test_strike_selection_banknifty_put(self):
        selector = QuantitativeContractSelector()
        result = selector.select_optimal_contract(
            underlying="BANKNIFTY",
            spot_price=53240.0,
            direction="LONG_PUT",
            expected_move_points=220.0,
            stop_loss_points=80.0,
            target_horizon_hours=1.5,
            current_iv=0.17,
        )
        assert result is not None
        assert result.direction == "LONG_PUT"
        assert result.selected_contract.option_type == "PE"
        assert result.selected_greeks.delta < 0  # Put delta must be negative


class TestOptionPositionSizingAndRiskIntegration:
    def test_calculate_option_buyer_sizing(self):
        sizing = calculate_option_buyer_sizing(
            available_capital=100000.0,
            risk_percent=1.5,  # ₹1,500 risk capital
            option_entry_premium=120.0,
            option_stop_premium=90.0,  # ₹30 risk per share
            lot_size=75,
            max_capital_allocation_pct=25.0,
        )
        assert sizing["allowed"] is False
        # risk per lot = 30 * 75 = 2250 -> budget 1500 can't take 1 lot
        assert sizing["lots"] == 0
        assert "Insufficient risk capital" in sizing["reason"]

        # With 3% risk (₹3,000 risk capital)
        sizing2 = calculate_option_buyer_sizing(
            available_capital=100000.0,
            risk_percent=3.0,  # ₹3,000 budget
            option_entry_premium=120.0,
            option_stop_premium=90.0,  # ₹30 risk per share
            lot_size=75,
            max_capital_allocation_pct=25.0,
        )
        assert sizing2["allowed"] is True
        assert sizing2["lots"] == 1
        assert sizing2["quantity"] == 75
        assert sizing2["max_rupee_loss"] == 2250.0

    def test_central_risk_engine_theta_drag_guard(self):
        engine = CentralRiskEngine()

        # Normal setup with moderate theta drag
        setup_ok = StrategySetup(
            strategy_name="VWAP_SCALP",
            underlying="NIFTY",
            direction="LONG_CALL",
            timeframe="1M",
            is_scalp=True,
            spot_price=Decimal("24900.0"),
            entry_trigger=Decimal("24900.0"),
            raw_structural_stop=Decimal("24888.0"),  # 12 pts risk
            atr_5m=Decimal("16.0"),
            confidence=80.0,
            option_delta=0.55,
            option_theta_hour=-2.0,  # ₹2.0/hr decay on ~10 pt gain
        )
        decision_ok = engine.evaluate(setup_ok, available_capital=200000.0, risk_per_trade_pct=2.0, allow_closed_market=True)
        assert decision_ok.accepted is True
        assert decision_ok.option_delta == 0.55

        # Extreme theta drag setup (e.g. expiring in 1 hour OTM with huge decay)
        setup_bad_theta = StrategySetup(
            strategy_name="MICRO_MOMENTUM",
            underlying="NIFTY",
            direction="LONG_CALL",
            timeframe="1M",
            is_scalp=True,
            spot_price=Decimal("24900.0"),
            entry_trigger=Decimal("24900.0"),
            raw_structural_stop=Decimal("24888.0"),
            atr_5m=Decimal("16.0"),
            confidence=80.0,
            option_delta=0.40,
            option_theta_hour=-15.0,  # ₹15/hr decay on 8 pt gain is > 100% theta drag!
        )
        decision_bad = engine.evaluate(setup_bad_theta, available_capital=200000.0, risk_per_trade_pct=2.0, allow_closed_market=True)
        assert decision_bad.accepted is False
        assert "EXCESSIVE_THETA_DRAG" in decision_bad.rejection_reason
