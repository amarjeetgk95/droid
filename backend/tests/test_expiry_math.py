from datetime import datetime, date, timezone
import zoneinfo
from app.quant.expiry_math import calculate_time_to_expiry, get_risk_free_rate, MIN_TIME_TO_EXPIRY

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


class TestExpiryMath:
    def test_future_expiry_fractional_year(self):
        # 10 days before expiry at 15:30 IST
        curr = datetime(2026, 8, 24, 15, 30, tzinfo=IST)
        expiry = date(2026, 9, 3)  # 10 days later
        t = calculate_time_to_expiry(curr, expiry)
        assert abs(t - (10.0 / 365.0)) < 1e-4

    def test_same_day_intraday_hours(self):
        # On expiry day at 09:30 IST (6 hours left till 15:30)
        curr = datetime(2026, 9, 3, 9, 30, tzinfo=IST)
        expiry = date(2026, 9, 3)
        t = calculate_time_to_expiry(curr, expiry)
        expected = (6.0 / 24.0) / 365.0
        assert abs(t - expected) < 1e-4

    def test_past_expiry_clamps_to_min(self):
        # After 15:30 on expiry day
        curr = datetime(2026, 9, 3, 16, 0, tzinfo=IST)
        expiry = date(2026, 9, 3)
        t = calculate_time_to_expiry(curr, expiry)
        assert t == MIN_TIME_TO_EXPIRY

    def test_risk_free_rate_attribution(self):
        rate, source = get_risk_free_rate()
        assert rate == 0.0675
        assert "FALLBACK" in source
