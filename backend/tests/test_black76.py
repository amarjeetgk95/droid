import math
from app.quant.black76 import black76_price, black76_greeks


class TestBlack76Engine:
    def test_atm_call_and_put_pricing(self):
        f = 25000.0
        k = 25000.0
        t = 10.0 / 365.0
        r = 0.0675
        sigma = 0.15

        call_p = black76_price("CE", f, k, t, r, sigma)
        put_p = black76_price("PE", f, k, t, r, sigma)

        assert call_p > 0.0
        assert put_p > 0.0
        # Under Black-76 when F == K, Call == Put (discounted symmetric straddle)
        assert abs(call_p - put_p) < 0.01

    def test_put_call_parity(self):
        # Black-76 Parity: Call - Put = e^(-rT) * (F - K)
        f = 25200.0
        k = 25000.0
        t = 30.0 / 365.0
        r = 0.0675
        sigma = 0.16

        c = black76_price("CE", f, k, t, r, sigma)
        p = black76_price("PE", f, k, t, r, sigma)
        df = math.exp(-r * t)

        assert abs((c - p) - df * (f - k)) < 0.05

    def test_analytical_greeks_boundaries(self):
        f = 25000.0
        k = 25000.0
        t = 15.0 / 365.0
        r = 0.0675
        sigma = 0.14

        g_ce = black76_greeks("CE", f, k, t, r, sigma)
        g_pe = black76_greeks("PE", f, k, t, r, sigma)

        # Delta ranges: Call between 0 and 1, Put between -1 and 0
        assert 0.40 <= g_ce.delta <= 0.60
        assert -0.60 <= g_pe.delta <= -0.40

        # Gamma should be identical and positive
        assert g_ce.gamma > 0
        assert abs(g_ce.gamma - g_pe.gamma) < 1e-6

        # Theta should be negative (time decay)
        assert g_ce.theta < 0
        assert g_pe.theta < 0

        # Vega should be identical and positive
        assert g_ce.vega > 0
        assert abs(g_ce.vega - g_pe.vega) < 1e-4

    def test_deep_itm_and_otm_delta(self):
        f = 25000.0
        t = 5.0 / 365.0
        r = 0.0675
        sigma = 0.15

        # Deep ITM Call (K = 23000)
        g_itm = black76_greeks("CE", f, 23000.0, t, r, sigma)
        assert g_itm.delta > 0.95

        # Deep OTM Call (K = 27000)
        g_otm = black76_greeks("CE", f, 27000.0, t, r, sigma)
        assert g_otm.delta < 0.05
