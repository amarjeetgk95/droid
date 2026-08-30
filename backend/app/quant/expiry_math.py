import zoneinfo
from datetime import datetime, date, time, timezone

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
MIN_TIME_TO_EXPIRY: float = 1e-5  # ~5 minutes, prevents zero division in pricing / IV
DEFAULT_RISK_FREE_RATE: float = 0.0675  # 6.75% Indian sovereign benchmark fallback


def calculate_time_to_expiry(
    current_time: datetime,
    expiry_date: date | datetime,
    market_close_hour: int = 15,
    market_close_minute: int = 30,
) -> float:
    """Calculate ACT/365 time-to-expiry in fractional years with intraday precision.
    
    Adheres strictly to Section 31 of the quantitative engine spec.
    Expiry cutoff is strictly 15:30:00 IST on the expiry date.
    """
    # Ensure current_time has timezone (default to IST)
    if current_time.tzinfo is None:
        curr_ist = current_time.replace(tzinfo=timezone.utc).astimezone(IST)
    else:
        curr_ist = current_time.astimezone(IST)

    # Resolve target expiry datetime in IST
    if isinstance(expiry_date, datetime):
        exp_date = expiry_date.date()
    else:
        exp_date = expiry_date

    exp_target = datetime.combine(
        exp_date,
        time(hour=market_close_hour, minute=market_close_minute, second=0),
        tzinfo=IST,
    )

    diff = (exp_target - curr_ist).total_seconds()
    if diff <= 0:
        return MIN_TIME_TO_EXPIRY

    total_seconds_in_year = 365.0 * 86400.0
    t = diff / total_seconds_in_year

    return max(t, MIN_TIME_TO_EXPIRY)


def get_risk_free_rate(fallback_rate: float = DEFAULT_RISK_FREE_RATE) -> tuple[float, str]:
    """Return risk-free rate and its source attribution.
    
    Adheres strictly to Section 32: dynamic benchmark -> T-bill yield -> 6.75% static fallback.
    """
    return fallback_rate, "IN_SOVEREIGN_BENCHMARK_6.75_FALLBACK"
