import pytest
from app.signals.portfolio_greeks import (
    PortfolioGreeksLedger,
    PortfolioGreekPosition,
    PortfolioRiskLimits,
)


class TestPortfolioGreeksLedger:
    def test_aggregation_and_summary(self):
        ledger = PortfolioGreeksLedger()
        ledger.clear()

        # Add 1 NIFTY Scalp Call position (75 qty, 0.55 delta, -15 theta/day)
        pos1 = PortfolioGreekPosition(
            position_id="pos-nifty-scalp-1",
            underlying="NIFTY",
            horizon="SCALP",
            option_type="CE",
            strike=24900.0,
            expiry_date="2026-09-10",
            quantity=75,
            unit_delta=0.55,
            unit_gamma=0.0008,
            unit_theta_day=-15.0,
            unit_vega=12.0,
        )
        ledger.add_position(pos1)

        summary = ledger.get_summary()
        assert summary.total_open_positions == 1
        assert summary.total_delta == round(0.55 * 75, 2)  # 41.25
        assert summary.total_theta_day == round(-15.0 * 75, 2)  # -1125.0
        assert summary.net_exposure_by_underlying["NIFTY"] == 41.25
        assert summary.positions_by_horizon["SCALP"] == 1

    def test_cross_horizon_compounding_guard(self):
        ledger = PortfolioGreeksLedger(
            limits=PortfolioRiskLimits(max_same_direction_horizons=2)
        )
        ledger.clear()

        # Position 1: NIFTY SCALP CE
        ledger.add_position(
            PortfolioGreekPosition(
                position_id="pos-scalp",
                underlying="NIFTY",
                horizon="SCALP",
                option_type="CE",
                strike=24900.0,
                expiry_date="2026-09-10",
                quantity=75,
                unit_delta=0.50,
                unit_gamma=0.0005,
                unit_theta_day=-12.0,
                unit_vega=10.0,
            )
        )

        # Position 2: NIFTY INTRADAY CE
        ledger.add_position(
            PortfolioGreekPosition(
                position_id="pos-intraday",
                underlying="NIFTY",
                horizon="INTRADAY",
                option_type="CE",
                strike=24950.0,
                expiry_date="2026-09-10",
                quantity=75,
                unit_delta=0.45,
                unit_gamma=0.0005,
                unit_theta_day=-10.0,
                unit_vega=10.0,
            )
        )

        # Proposed Position 3: NIFTY SWING CE (3rd concurrent horizon in same direction!)
        marginal_check = ledger.evaluate_marginal_trade(
            underlying="NIFTY",
            horizon="SWING",
            option_type="CE",
            strike=25000.0,
            expiry_date="2026-09-17",
            quantity=75,
            unit_delta=0.40,
            unit_gamma=0.0004,
            unit_theta_day=-8.0,
            unit_vega=15.0,
        )

        # Must be rejected to prevent correlated over-leverage (§51)
        assert marginal_check.allowed is False
        assert "CROSS_HORIZON_LIMIT_EXCEEDED" in marginal_check.rejection_reason
        assert marginal_check.cross_horizon_overlap_detected is True

    def test_portfolio_delta_ceiling_enforcement(self):
        ledger = PortfolioGreeksLedger(
            limits=PortfolioRiskLimits(max_net_delta_per_underlying=100.0)
        )
        ledger.clear()

        # Adding 300 qty with 0.60 delta = 180 delta > 100 limit!
        marginal_check = ledger.evaluate_marginal_trade(
            underlying="NIFTY",
            horizon="INTRADAY",
            option_type="CE",
            strike=24800.0,
            expiry_date="2026-09-10",
            quantity=300,
            unit_delta=0.60,
            unit_gamma=0.0005,
            unit_theta_day=-15.0,
            unit_vega=12.0,
        )
        assert marginal_check.allowed is False
        assert "PORTFOLIO_DELTA_BREACH" in marginal_check.rejection_reason

    def test_portfolio_theta_burn_ceiling(self):
        ledger = PortfolioGreeksLedger(
            limits=PortfolioRiskLimits(max_portfolio_theta_day_rupees=5000.0)
        )
        ledger.clear()

        # Adding position with ₹8,000/day theta decay
        marginal_check = ledger.evaluate_marginal_trade(
            underlying="BANKNIFTY",
            horizon="SCALP",
            option_type="CE",
            strike=53000.0,
            expiry_date="2026-09-10",
            quantity=200,
            unit_delta=0.50,
            unit_gamma=0.0002,
            unit_theta_day=-45.0,  # 200 * -45 = -9,000/day!
            unit_vega=20.0,
        )
        assert marginal_check.allowed is False
        assert "PORTFOLIO_THETA_BREACH" in marginal_check.rejection_reason
