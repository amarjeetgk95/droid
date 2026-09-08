"""
Session-Aware Horizon Windows — Phase 1

Decides whether a prediction's forward window [T, T+H] is settleable and,
if so, which spot counts as "price at T+H" — without ever inventing data.

Rules:
- Crypto (24/7, e.g. BTCUSDT/ETHUSDT): always settleable in principle;
  forward spot = last 1m close at or before T+H (and at or after T).
- NSE equity (09:15-15:30 IST, holidays/special sessions per calendar):
  T and T+H must fall in the SAME regular session. Windows crossing the
  close, weekends, holidays, or touching a special session are
  INSUFFICIENT_DATA — never bridged with the next open, which would mix
  overnight-gap returns into an intraday label.

PIT discipline: resolution only reads candles with timestamps <= T+H that
were fetched AFTER T+H (historical fact at settle time). Candle timestamps
are trusted as published; a candle dated after T+H is never used.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def is_crypto_symbol(symbol: str) -> bool:
    """NSE names never contain USDT; crypto pairs always do (or are bare coins)."""
    s = (symbol or "").upper().strip()
    if "USDT" in s:
        return True
    return s in ("BTC", "ETH", "SOL", "BTCUSD", "ETHUSD")


def _as_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def classify_window(
    symbol: str,
    t_utc: datetime,
    horizon_minutes: int,
    calendar: Any | None = None,
) -> dict:
    """Classify whether [T, T+H] is settleable.

    Returns {"universe", "settleable", "reason", "t_plus_h_utc",
    "session_close_utc"}. Pure except for the calendar read.
    """
    from app.ml.targets import validate_horizon

    horizon_minutes = validate_horizon(horizon_minutes)
    t = _as_utc(t_utc)
    t_plus_h = t + timedelta(minutes=horizon_minutes)

    if is_crypto_symbol(symbol):
        return {
            "universe": "crypto",
            "settleable": True,
            "reason": "crypto-24/7",
            "t_plus_h_utc": t_plus_h,
            "session_close_utc": None,
        }

    if calendar is None:
        from app.services.calendar_service import IST, calendar_service

        calendar = calendar_service
    else:
        from app.services.calendar_service import IST

    t_ist = t.astimezone(IST)
    h_ist = t_plus_h.astimezone(IST)
    info = calendar.get_session_info(t_ist.date())

    if not info.is_trading_day:
        return {
            "universe": "nse",
            "settleable": False,
            "reason": f"observation-on-non-trading-day ({info.holiday_name or 'weekend'})",
            "t_plus_h_utc": t_plus_h,
            "session_close_utc": None,
        }
    if info.is_special_session or info.market_open is None or info.market_close is None:
        return {
            "universe": "nse",
            "settleable": False,
            "reason": "special-session-involved",
            "t_plus_h_utc": t_plus_h,
            "session_close_utc": None,
        }
    if not (info.market_open <= t_ist < info.market_close):
        return {
            "universe": "nse",
            "settleable": False,
            "reason": "observation-outside-session",
            "t_plus_h_utc": t_plus_h,
            "session_close_utc": info.market_close.astimezone(timezone.utc),
        }
    if h_ist.date() != t_ist.date() or h_ist >= info.market_close:
        return {
            "universe": "nse",
            "settleable": False,
            "reason": "crosses-session-close",
            "t_plus_h_utc": t_plus_h,
            "session_close_utc": info.market_close.astimezone(timezone.utc),
        }
    return {
        "universe": "nse",
        "settleable": True,
        "reason": "same-regular-session",
        "t_plus_h_utc": t_plus_h,
        "session_close_utc": info.market_close.astimezone(timezone.utc),
    }


def resolve_forward_spot(
    candles: list[Any],
    t_utc: datetime,
    t_plus_h_utc: datetime,
) -> tuple[float | None, str]:
    """Pick the forward spot from 1m candles: last close in [T, T+H].

    Accepts NormalizedCandle (timestamp/close) or (timestamp, close) tuples.
    Returns (spot, "") or (None, reason). Never extrapolates.
    """
    t = _as_utc(t_utc)
    h = _as_utc(t_plus_h_utc)
    best_ts: datetime | None = None
    best_close: float | None = None

    for c in candles or []:
        if isinstance(c, tuple):
            ts, close = c
        else:
            ts, close = getattr(c, "timestamp"), getattr(c, "close")
        if ts is None:
            continue
        ts = _as_utc(ts)
        if ts < t or ts > h:
            continue
        try:
            px = float(close)
        except (TypeError, ValueError):
            continue
        if px <= 0 or not px == px:  # non-positive or NaN
            continue
        if best_ts is None or ts >= best_ts:
            best_ts, best_close = ts, px

    if best_close is None:
        return None, "no-candle-covering-horizon"
    return best_close, ""
