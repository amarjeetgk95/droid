import pytest
from app.quant.payoff import calculate_strategy_payoff, LegParams


class TestPayoffMath:
    def test_bull_call_spread_payoff(self):
        spot = 25000.0
        t = 10.0 / 365.0
        legs = [
            LegParams(option_type="CE", side="BUY", strike=25000.0, quantity=1, price=150.0, iv=0.15, lot_size=75),
            LegParams(option_type="CE", side="SELL", strike=25200.0, quantity=1, price=60.0, iv=0.15, lot_size=75),
        ]

        result = calculate_strategy_payoff(legs, spot, t)

        # Net Debit = (150 - 60) * 75 = 90 * 75 = 6750
        assert result.net_premium == 6750.0
        assert result.max_loss == 6750.0

        # Max Profit = (200 - 90) * 75 = 110 * 75 = 8250
        assert result.max_profit == 8250.0

        # Breakeven = 25000 + 90 = 25090
        assert len(result.breakevens) == 1
        assert abs(result.breakevens[0] - 25090.0) < 5.0

        # Delta should be positive for Bull Call
        assert result.net_delta > 0
        assert len(result.payoff_curve) > 0

    def test_iron_condor_payoff(self):
        spot = 25000.0
        t = 15.0 / 365.0
        legs = [
            LegParams(option_type="PE", side="BUY", strike=24600.0, quantity=1, price=25.0, iv=0.16, lot_size=75),
            LegParams(option_type="PE", side="SELL", strike=24800.0, quantity=1, price=65.0, iv=0.15, lot_size=75),
            LegParams(option_type="CE", side="SELL", strike=25200.0, quantity=1, price=70.0, iv=0.14, lot_size=75),
            LegParams(option_type="CE", side="BUY", strike=25400.0, quantity=1, price=28.0, iv=0.14, lot_size=75),
        ]

        result = calculate_strategy_payoff(legs, spot, t)

        # Net Credit = (65 + 70 - 25 - 28) * 75 = 82 * 75 = 6150 (Negative net_premium indicates credit)
        assert result.net_premium == -6150.0
        assert result.max_profit == 6150.0

        # Max Loss = (200 - 82) * 75 = 118 * 75 = 8850
        assert result.max_loss == 8850.0

        # Should have 2 breakeven points
        assert len(result.breakevens) == 2
        assert result.breakevens[0] < spot < result.breakevens[1]

        # Theta should be positive (seller strategy benefiting from decay)
        assert result.net_theta > 0
        assert result.pop_percent > 0
