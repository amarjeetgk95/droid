import pytest
from app.quant.black76 import black76_price
from app.quant.iv_solver import calculate_iv_black76, calculate_iv_black_scholes


class TestIVSolver:
    def test_brent_iv_inversion_precision(self):
        f = 25000.0
        k = 25000.0
        t = 20.0 / 365.0
        r = 0.0675
        known_sigma = 0.1825  # 18.25% IV

        # Generate theoretical price
        market_price = black76_price("CE", f, k, t, r, known_sigma)

        # Invert to solve for IV
        solved_iv = calculate_iv_black76("CE", market_price, f, k, t, r)
        assert solved_iv is not None
        assert abs(solved_iv - known_sigma) < 0.001

    def test_put_iv_inversion(self):
        f = 25000.0
        k = 24800.0
        t = 15.0 / 365.0
        r = 0.0675
        known_sigma = 0.1450

        market_price = black76_price("PE", f, k, t, r, known_sigma)
        solved_iv = calculate_iv_black76("PE", market_price, f, k, t, r)
        assert solved_iv is not None
        assert abs(solved_iv - known_sigma) < 0.001

    def test_below_intrinsic_returns_none(self):
        f = 25000.0
        k = 24000.0  # ITM Call, intrinsic = 1000
        t = 10.0 / 365.0
        r = 0.0675
        impossible_price = 50.0  # Far below intrinsic

        solved_iv = calculate_iv_black76("CE", impossible_price, f, k, t, r)
        assert solved_iv is None
