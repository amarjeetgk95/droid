"""Unit Tests for Synthetic Options Execution Simulator (Tier 3).

Tests:
- ATM strike selection
- Long Call (CE) payoff and delta tracking
- Long Put (PE) payoff and delta tracking
- Theta time decay during flat price drift
- Indian statutory options costs and spread slippage
"""

from datetime import datetime, timezone
import pytest

from app.quant.backtest.options_simulator import (
    OptionsExecutionSimulator,
    OptionsTradeResult,
    simulate_vertical_spread,
)


class TestOptionsExecutionSimulator:

    @pytest.fixture
    def simulator(self) -> OptionsExecutionSimulator:
        return OptionsExecutionSimulator(
            symbol="SENSEX",
            lot_size=10,
            strike_step=100.0,
            default_iv=0.14,
            risk_free_rate=0.065,
            spread_half_pct=0.015,
        )

    def test_select_atm_strike(self, simulator):
        assert simulator.select_atm_strike(80045.0) == 80000.0
        assert simulator.select_atm_strike(80055.0) == 80100.0
        assert simulator.select_atm_strike(80100.0) == 80100.0

    def test_call_option_profitable_move(self, simulator):
        """Spot price increases by 400 pts -> Call premium expands."""
        t0 = datetime(2026, 8, 1, 9, 30, tzinfo=timezone.utc)
        t1 = datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc)

        res = simulator.simulate_trade(
            entry_time=t0,
            exit_time=t1,
            direction=1,  # Long Call
            spot_entry=80000.0,
            spot_exit=80400.0,
            bars_held=4,
            days_to_expiry=3.0,
        )

        assert isinstance(res, OptionsTradeResult)
        assert res.option_type == "CE"
        assert res.strike == 80000.0
        assert res.premium_exit_exec > res.premium_entry_exec
        assert res.options_gross_pnl > 0.0
        assert res.options_net_roi_pct > 0.0
        assert 0.45 <= res.delta_at_entry <= 0.55  # ATM Call delta ~ 0.50
        assert res.total_statutory_cost > 40.0     # Brokerage (2x ₹20) + STT + GST

    def test_put_option_profitable_move(self, simulator):
        """Spot price decreases by 400 pts -> Put premium expands."""
        t0 = datetime(2026, 8, 1, 9, 30, tzinfo=timezone.utc)
        t1 = datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc)

        res = simulator.simulate_trade(
            entry_time=t0,
            exit_time=t1,
            direction=-1,  # Long Put
            spot_entry=80000.0,
            spot_exit=79600.0,
            bars_held=4,
            days_to_expiry=3.0,
        )

        assert res.option_type == "PE"
        assert res.strike == 80000.0
        assert res.premium_exit_exec > res.premium_entry_exec
        assert res.options_gross_pnl > 0.0
        assert -0.55 <= res.delta_at_entry <= -0.45  # ATM Put delta ~ -0.50

    def test_theta_decay_on_flat_spot(self, simulator):
        """If spot price is unchanged, holding the option loses money from time decay."""
        t0 = datetime(2026, 8, 1, 9, 30, tzinfo=timezone.utc)
        t1 = datetime(2026, 8, 1, 14, 30, tzinfo=timezone.utc)

        res = simulator.simulate_trade(
            entry_time=t0,
            exit_time=t1,
            direction=1,
            spot_entry=80000.0,
            spot_exit=80000.0,  # 0 change in spot
            bars_held=20,       # Held 5 hours
            days_to_expiry=1.0, # 1 DTE (high theta)
        )

        # Due to theta decay and spread, exit price MUST be lower than entry price
        assert res.premium_exit_exec < res.premium_entry_exec
        assert res.options_gross_pnl < 0.0
        assert res.theta_per_day < 0.0

    def test_black76_forward_parity_and_greeks_precision(self, simulator):
        """Known-answer test: Forward parity, ATM symmetry, and Greeks analytical identities."""
        from app.quant.black76 import black76_price, black76_greeks
        import math

        f = 80000.0
        k = 80000.0
        t = 7.0 / 365.0  # 1 week
        r = 0.065
        sigma = 0.14

        call_price = black76_price("CE", f=f, k=k, t=t, r=r, sigma=sigma)
        put_price = black76_price("PE", f=f, k=k, t=t, r=r, sigma=sigma)

        # Forward Put-Call Parity identity: Call - Put = e^(-r*T) * (F - K)
        # When F == K, Call price MUST exactly equal Put price
        assert abs(call_price - put_price) < 1e-6
        assert call_price > 0.0

        # Known-answer analytical price check (617.99 points for 80k SENSEX 14% IV 7 DTE)
        assert abs(call_price - 617.99) < 0.1

        # Greeks analytical identity: Delta_call - Delta_put == e^(-r*T)
        g_call = black76_greeks("CE", f=f, k=k, t=t, r=r, sigma=sigma)
        g_put = black76_greeks("PE", f=f, k=k, t=t, r=r, sigma=sigma)

        discount_factor = math.exp(-r * t)
        assert abs((g_call.delta - g_put.delta) - discount_factor) < 1e-4

        # Gamma must be strictly positive and identical for Call and Put
        assert g_call.gamma > 0.0
        assert abs(g_call.gamma - g_put.gamma) < 1e-8

        # Vega must be strictly positive and identical for Call and Put
        assert g_call.vega > 0.0
        assert abs(g_call.vega - g_put.vega) < 1e-8

        # Theta must be strictly negative for options buyer
        assert g_call.theta < 0.0
        assert g_put.theta < 0.0

    def test_black76_expiry_boundary_conditions(self):
        """Options pricing collapses to pure intrinsic value at T -> 0."""
        from app.quant.black76 import black76_price

        # ITM Call at expiration
        c_itm = black76_price("CE", f=80500.0, k=80000.0, t=0.0, r=0.065, sigma=0.14)
        assert c_itm == 500.0

        # OTM Call at expiration
        c_otm = black76_price("CE", f=79500.0, k=80000.0, t=0.0, r=0.065, sigma=0.14)
        assert c_otm == 0.0

        # ITM Put at expiration
        p_itm = black76_price("PE", f=79500.0, k=80000.0, t=0.0, r=0.065, sigma=0.14)
        assert p_itm == 500.0

    def test_bull_call_spread_net_entry_cost(self, simulator):
        """Bull call spread net entry cost > 0 and < naked ATM call."""
        res = simulator.simulate_vertical_spread(
            spot_entry=80000.0,
            spot_exit=80300.0,
            direction="LONG",
            holding_bars=4,
            bar_minutes=15,
            iv=0.14,
            dte_entry=4.0,
            strike_width=300.0,
            lot_size=10,
            contracts=1,
        )

        net_entry = res["net_entry"]
        naked_entry = res["naked_comparison"]["naked_entry"]

        # Bull call spread net entry cost must be strictly positive (debit spread)
        assert net_entry > 0.0
        # Bull call spread net entry cost must be strictly less than naked ATM call
        assert net_entry < naked_entry
        # Long strike is ATM, short strike is OTM
        assert res["legs"]["long_leg"]["strike"] == 80000.0
        assert res["legs"]["short_leg"]["strike"] == 80300.0
        # Positive bullish delta, but lower delta than naked call
        assert res["net_delta"] > 0.0
        assert res["net_delta"] < res["legs"]["long_leg"]["delta"]
        # Max loss is capped at net debit
        assert res["pnl"]["max_loss_pts"] == net_entry

    def test_spread_theta_decay_reduction_on_flat_spot(self, simulator):
        """Theta decay on a flat spot move is significantly lower (at least 40% less theta loss) than naked ATM call."""
        res = simulator.simulate_vertical_spread(
            spot_entry=80000.0,
            spot_exit=80000.0,  # Flat spot (zero price movement)
            direction="LONG",
            holding_bars=20,    # Held 5 hours (20 bars x 15m)
            bar_minutes=15,
            iv=0.14,
            dte_entry=4.0,
            strike_width=300.0,
            lot_size=10,
            contracts=1,
        )

        # Analytical theta reduction percentage must be at least 40%
        assert res["theta_decay_reduction_pct"] >= 40.0
        # Realized theta premium loss reduction percentage on flat spot must be at least 40%
        assert res["theta_comparison"]["theta_loss_reduction_pct"] >= 40.0
        # In absolute points, spread loss must be at least 40% less than naked ATM call loss
        naked_loss = res["theta_comparison"]["naked_loss_pts"]
        spread_loss = res["theta_comparison"]["spread_loss_pts"]
        assert naked_loss > 0.0
        assert spread_loss < 0.60 * naked_loss

        # Net theta must be less negative (closer to zero) than naked theta
        naked_theta = res["theta_comparison"]["naked_theta_per_day"]
        net_theta = res["greeks"]["net_theta"]
        assert abs(net_theta) < 0.60 * abs(naked_theta)

    def test_bull_call_spread_profit_capped_on_large_favorable_move(self, simulator):
        """Profit is capped at (strike_width - net_debit) on large favorable move."""
        strike_width = 300.0
        res = simulator.simulate_vertical_spread(
            spot_entry=80000.0,
            spot_exit=85000.0,  # +5,000 pts massive rally (both legs deep ITM)
            direction="LONG",
            holding_bars=4,
            bar_minutes=15,
            iv=0.14,
            dte_entry=4.0,
            strike_width=strike_width,
            lot_size=10,
            contracts=1,
        )

        net_debit = res["net_entry"]
        max_profit_cap_pts = strike_width - net_debit
        gross_pnl_pts = res["pnl"]["gross_pnl_pts"]

        # Spread gross PnL points must be positive
        assert gross_pnl_pts > 0.0
        # Spread gross PnL points must be strictly capped at (strike_width - net_debit)
        assert gross_pnl_pts <= max_profit_cap_pts + 1e-4
        assert res["pnl"]["profit_capped"] is True

        # Test even larger move (+15,000 pts) - profit must remain strictly bounded at cap
        res_massive = simulator.simulate_vertical_spread(
            spot_entry=80000.0,
            spot_exit=95000.0,
            direction="LONG",
            holding_bars=4,
            bar_minutes=15,
            iv=0.14,
            dte_entry=4.0,
            strike_width=strike_width,
            lot_size=10,
            contracts=1,
        )
        assert res_massive["pnl"]["gross_pnl_pts"] <= max_profit_cap_pts + 1e-4
        # Unlike naked call which expands to 15,000 pts, spread profit does not exceed cap
        assert res_massive["naked_comparison"]["naked_gross_pnl_pts"] > 10000.0
        assert res_massive["pnl"]["gross_pnl_pts"] < 300.0

    def test_bear_put_spread_payoff_and_capped_profit(self):
        """Bear put spread payoff, negative delta, and capped profit on large drop."""
        strike_width = 300.0
        res = simulate_vertical_spread(
            spot_entry=80000.0,
            spot_exit=75000.0,  # -5,000 pts massive drop
            direction="SHORT",
            holding_bars=4,
            bar_minutes=15,
            iv=0.14,
            dte_entry=4.0,
            strike_width=strike_width,
            lot_size=10,
            contracts=1,
        )

        assert res["spread_name"] == "Bear Put Spread"
        assert res["legs"]["long_leg"]["strike"] == 80000.0
        assert res["legs"]["short_leg"]["strike"] == 79700.0
        assert res["net_entry"] > 0.0
        assert res["net_entry"] < res["naked_comparison"]["naked_entry"]
        assert res["net_delta"] < 0.0  # Bearish delta

        # Profit is capped at strike_width - net_debit
        max_profit_cap = strike_width - res["net_entry"]
        assert res["pnl"]["gross_pnl_pts"] <= max_profit_cap + 1e-4
        assert res["pnl"]["gross_pnl_pts"] > 0.0

    def test_multi_leg_statutory_costs_bse(self):
        """Statutory multi-leg costs: 4 orders (₹80 brokerage), STT on sell legs, GST."""
        res = simulate_vertical_spread(
            spot_entry=80000.0,
            spot_exit=80300.0,
            direction="LONG",
            holding_bars=4,
            bar_minutes=15,
            iv=0.14,
            dte_entry=4.0,
            strike_width=300.0,
            lot_size=10,
            contracts=1,
        )

        costs = res["costs"]
        # 4 orders (2 on entry, 2 on exit) @ ₹20 = ₹80
        assert costs["brokerage"] == 80.0
        assert costs["num_orders"] == 4
        # STT applied on both sell turnover legs (entry short sell + exit long sell)
        assert costs["stt"] > 0.0
        # Stamp duty applied on buy turnover legs
        assert costs["stamp_duty"] > 0.0
        # GST applied on (brokerage + exchange + SEBI)
        assert costs["gst"] > 0.0
        assert costs["total_cost"] > 80.0

