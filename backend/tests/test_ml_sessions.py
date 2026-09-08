"""Phase 1 session-aware settlement tests: window classification,
forward-spot resolution, and settlement planning. Pure — no brokers or DB."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.ml.sessions import classify_window, is_crypto_symbol, resolve_forward_spot
from app.ml.settlement import plan_row
from app.services.calendar_service import calendar_service

IST = ZoneInfo("Asia/Kolkata")

# Wednesday 2026-09-09: regular trading day (no holiday in calendar table).
WED_10AM_IST = datetime(2026, 9, 9, 10, 0, tzinfo=IST)
WED_1430_IST = datetime(2026, 9, 9, 14, 30, tzinfo=IST)
SAT_NOON_IST = datetime(2026, 9, 12, 12, 0, tzinfo=IST)


def test_universe_split():
    assert is_crypto_symbol("BTCUSDT")
    assert is_crypto_symbol("ethusdt")
    assert not is_crypto_symbol("NIFTY")
    assert not is_crypto_symbol("BANKNIFTY")


def test_crypto_always_settleable():
    w = classify_window("BTCUSDT", datetime.now(timezone.utc), 120)
    assert w["universe"] == "crypto" and w["settleable"] is True


def test_nse_same_session_settleable():
    assert calendar_service.is_trading_day(WED_10AM_IST.date())
    w = classify_window("NIFTY", WED_10AM_IST, 15)
    assert w["settleable"] is True
    assert w["reason"] == "same-regular-session"


def test_nse_late_day_long_horizon_crosses_close():
    # 14:30 + 120m = 16:30 IST, past the 15:30 close
    w = classify_window("NIFTY", WED_1430_IST, 120)
    assert w["settleable"] is False
    assert w["reason"] == "crosses-session-close"


def test_nse_short_horizon_late_day_ok():
    # 14:30 + 30m = 15:00 IST, still in session
    w = classify_window("NIFTY", WED_1430_IST, 30)
    assert w["settleable"] is True


def test_nse_weekend_unsettleable():
    w = classify_window("NIFTY", SAT_NOON_IST, 15)
    assert w["settleable"] is False
    assert "non-trading-day" in w["reason"]


def test_resolve_forward_spot_picks_last_in_window():
    t = datetime(2026, 9, 9, 4, 0, tzinfo=timezone.utc)  # 09:30 IST
    h = t + timedelta(minutes=15)
    candles = [
        (t - timedelta(minutes=5), 100.0),  # before T: ignored
        (t, 100.0),
        (t + timedelta(minutes=7), 101.0),
        (t + timedelta(minutes=14), 102.5),  # winner
        (t + timedelta(minutes=30), 999.0),  # after H: ignored (future leak check)
    ]
    spot, reason = resolve_forward_spot(candles, t, h)
    assert spot == 102.5 and reason == ""


def test_resolve_forward_spot_insufficient():
    t = datetime(2026, 9, 9, 4, 0, tzinfo=timezone.utc)
    spot, reason = resolve_forward_spot([], t, t + timedelta(minutes=15))
    assert spot is None and reason == "no-candle-covering-horizon"


def test_plan_row_waits_for_horizon():
    now = datetime(2026, 9, 9, 4, 5, tzinfo=timezone.utc)
    row = {"symbol": "NIFTY", "timestamp": now, "spot_price": 100.0,
           "horizon_minutes": 15, "atr_at_t": 2.0}
    assert plan_row(row, [], now)["action"] == "wait"


def test_plan_row_skips_missing_atr_and_crossing():
    t = WED_10AM_IST.astimezone(timezone.utc)
    now = t + timedelta(minutes=30)
    no_atr = {"symbol": "NIFTY", "timestamp": t, "spot_price": 100.0,
              "horizon_minutes": 15, "atr_at_t": 0.0}
    assert plan_row(no_atr, [], now)["reason"] == "missing-atr-at-t"

    t2 = WED_1430_IST.astimezone(timezone.utc)
    late = {"symbol": "NIFTY", "timestamp": t2, "spot_price": 100.0,
            "horizon_minutes": 120, "atr_at_t": 2.0}
    plan = plan_row(late, [], t2 + timedelta(minutes=130))
    assert plan == {"action": "skip", "reason": "crosses-session-close"}


def test_plan_row_settles_crypto():
    t = datetime(2026, 9, 9, 4, 0, tzinfo=timezone.utc)
    now = t + timedelta(minutes=130)
    row = {"symbol": "BTCUSDT", "timestamp": t, "spot_price": 90000.0,
           "horizon_minutes": 120, "atr_at_t": 200.0}
    candles = [(t + timedelta(minutes=m), 90000.0 + m) for m in (0, 60, 119)]
    plan = plan_row(row, candles, now)
    assert plan["action"] == "settle"
    assert plan["outcome_spot"] == 90119.0
