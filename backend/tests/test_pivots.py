from app.quant.pivots import (
    calculate_classic_pivots, calculate_fibonacci_pivots,
    calculate_camarilla_pivots, calculate_value_area
)


class TestPivots:
    def test_classic_pivots(self):
        h, l, c = 25100.0, 24900.0, 25050.0
        piv = calculate_classic_pivots(h, l, c)

        assert piv.r3 > piv.r2 > piv.r1 > piv.pivot > piv.s1 > piv.s2 > piv.s3
        assert piv.pivot == round((h + l + c) / 3.0, 2)

    def test_fibonacci_pivots(self):
        h, l, c = 25100.0, 24900.0, 25050.0
        piv = calculate_fibonacci_pivots(h, l, c)

        assert piv.r3 > piv.r2 > piv.r1 > piv.pivot > piv.s1 > piv.s2 > piv.s3
        diff = h - l
        assert piv.r1 == round(piv.pivot + 0.382 * diff, 2)

    def test_camarilla_pivots(self):
        h, l, c = 25100.0, 24900.0, 25050.0
        piv = calculate_camarilla_pivots(h, l, c)

        assert piv.r4 is not None and piv.s4 is not None
        assert piv.r4 > piv.r3 > piv.r2 > piv.r1
        assert piv.s1 > piv.s2 > piv.s3 > piv.s4

    def test_value_area_volume_profile(self):
        prices = [25000.0, 25020.0, 25040.0, 25060.0, 25080.0]
        volumes = [1000.0, 5000.0, 20000.0, 6000.0, 1500.0]  # POC at 25040

        poc, vah, val = calculate_value_area(prices, volumes)
        assert poc == 25040.0
        assert vah >= poc >= val
