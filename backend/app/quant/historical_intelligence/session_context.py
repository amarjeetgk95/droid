"""
Session Context Engine — §7
Generates session-aware metadata: session phases, opening range, gap %, distances from PDH/PDL/PDC.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from app.quant.historical_intelligence.models import SessionPhase, CandleData


IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


@dataclass(slots=True)
class SessionContextData:
    session_phase: SessionPhase
    minutes_since_open: int
    gap_pct: float
    dist_from_day_high_pct: float
    dist_from_day_low_pct: float
    dist_from_pdc_pct: float
    session_high: float
    session_low: float
    previous_day_close: float | None = None
    previous_day_high: float | None = None
    previous_day_low: float | None = None


def get_session_phase(timestamp_utc_ms: int, is_crypto: bool = False) -> SessionPhase:
    """Classify the intraday session phase per Indian F&O trading schedule or 24x7 crypto."""
    if is_crypto:
        return SessionPhase.PERPETUAL

    dt = datetime.fromtimestamp(timestamp_utc_ms / 1000.0, tz=IST_TIMEZONE)
    hour = dt.hour
    minute = dt.minute
    time_minutes = hour * 60 + minute

    # Indian Market: 09:15 to 15:30 IST (555 to 930 minutes)
    if time_minutes < 555:
        return SessionPhase.PRE_MARKET
    elif 555 <= time_minutes < 585:        # 09:15 - 09:45
        return SessionPhase.MARKET_OPEN
    elif 585 <= time_minutes < 690:        # 09:45 - 11:30
        return SessionPhase.EARLY_SESSION
    elif 690 <= time_minutes < 810:        # 11:30 - 13:30
        return SessionPhase.MID_SESSION
    elif 810 <= time_minutes < 900:        # 13:30 - 15:00
        return SessionPhase.AFTERNOON
    elif 900 <= time_minutes <= 930:       # 15:00 - 15:30
        return SessionPhase.CLOSING_PHASE
    else:
        return SessionPhase.POST_MARKET


def compute_session_context(
    candles_today: list[CandleData],
    current_idx: int,
    pdc: float | None = None,
    pdh: float | None = None,
    pdl: float | None = None,
    is_crypto: bool = False,
) -> SessionContextData:
    """Computes session-aware structural context for a specific candle index."""
    current_candle = candles_today[current_idx]
    phase = get_session_phase(current_candle.timestamp_utc, is_crypto=is_crypto)

    # Session High/Low up to current index (no future leakage)
    history_today = candles_today[: current_idx + 1]
    session_high = max(c.high for c in history_today)
    session_low = min(c.low for c in history_today)
    curr_price = current_candle.close

    # Distance metrics
    dist_high = ((curr_price - session_high) / session_high) * 100.0 if session_high > 0 else 0.0
    dist_low = ((curr_price - session_low) / session_low) * 100.0 if session_low > 0 else 0.0

    gap_pct = 0.0
    dist_pdc = 0.0
    if pdc and pdc > 0:
        day_open = candles_today[0].open
        gap_pct = ((day_open - pdc) / pdc) * 100.0
        dist_pdc = ((curr_price - pdc) / pdc) * 100.0

    # Minutes since 09:15
    dt = datetime.fromtimestamp(current_candle.timestamp_utc / 1000.0, tz=IST_TIMEZONE)
    mins = max(0, (dt.hour * 60 + dt.minute) - 555)

    return SessionContextData(
        session_phase=phase,
        minutes_since_open=mins,
        gap_pct=round(gap_pct, 2),
        dist_from_day_high_pct=round(dist_high, 2),
        dist_from_day_low_pct=round(dist_low, 2),
        dist_from_pdc_pct=round(dist_pdc, 2),
        session_high=session_high,
        session_low=session_low,
        previous_day_close=pdc,
        previous_day_high=pdh,
        previous_day_low=pdl,
    )
