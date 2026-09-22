"""
Market Session Model for Indian Index Derivatives (§4).

Provides point-in-time session phase classification, time-of-day metrics,
no-trade window checks, and square-off enforcement for NIFTY, BANKNIFTY, SENSEX.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from typing import Optional

from app.signals.strategies.vortex_snap.types import (
    MarketSessionInfo,
    SessionPhase,
)
from app.signals.strategies.vortex_snap.config import SessionConfig


def parse_time_str(time_str: str) -> time:
    """Parse 'HH:MM' string into datetime.time object."""
    parts = time_str.strip().split(":")
    return time(hour=int(parts[0]), minute=int(parts[1]))


class MarketSessionModel:
    """Evaluates trading session dynamics given a timestamp and configuration."""

    def __init__(self, config: Optional[SessionConfig] = None) -> None:
        self.config = config or SessionConfig()
        self.tz = ZoneInfo(self.config.timezone)
        self.t_open = parse_time_str(self.config.market_open_time)
        self.t_or_end = parse_time_str(self.config.opening_range_end)
        self.t_intra_end = parse_time_str(self.config.normal_intraday_end)
        self.t_square_off = parse_time_str(self.config.forced_square_off_time)
        self.t_close = parse_time_str(self.config.market_close_time)
        self.parsed_no_trade = [
            (parse_time_str(start), parse_time_str(end))
            for start, end in self.config.no_trade_windows
        ]

    def evaluate(self, timestamp_ms: int) -> MarketSessionInfo:
        """Evaluate session state at epoch millisecond timestamp.

        Args:
            timestamp_ms: Epoch milliseconds (UTC).

        Returns:
            MarketSessionInfo snapshot.
        """
        # Convert timestamp to local trading timezone
        dt_utc = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
        dt_local = dt_utc.astimezone(self.tz)
        t_current = dt_local.time()
        weekday = dt_local.weekday()  # Monday=0, Sunday=6

        # Check weekend
        if weekday >= 5:
            return MarketSessionInfo(
                session_phase=SessionPhase.CLOSED,
                minutes_from_open=0.0,
                minutes_to_close=0.0,
                day_of_week=weekday,
                timestamp_ms=timestamp_ms,
                is_trading_allowed=False,
                is_no_trade_window=True,
                is_forced_square_off=False,
            )

        # Minute math relative to market open and market close
        open_dt = dt_local.replace(hour=self.t_open.hour, minute=self.t_open.minute, second=0, microsecond=0)
        close_dt = dt_local.replace(hour=self.t_close.hour, minute=self.t_close.minute, second=0, microsecond=0)

        mins_from_open = max((dt_local - open_dt).total_seconds() / 60.0, 0.0)
        mins_to_close = max((close_dt - dt_local).total_seconds() / 60.0, 0.0)

        # Check configured no-trade windows
        in_no_trade = False
        for start_t, end_t in self.parsed_no_trade:
            if start_t <= t_current < end_t:
                in_no_trade = True
                break

        # Check forced square off
        is_square_off = self.t_square_off <= t_current < self.t_close

        # Determine phase
        if t_current < time(9, 0):
            phase = SessionPhase.CLOSED
            trading_allowed = False
        elif t_current < self.t_open:
            phase = SessionPhase.PRE_OPEN
            trading_allowed = False
        elif t_current < time(9, 20):
            phase = SessionPhase.MARKET_OPEN
            trading_allowed = not in_no_trade
        elif t_current < self.t_or_end:
            phase = SessionPhase.OPENING_RANGE
            trading_allowed = not in_no_trade
        elif t_current < self.t_intra_end:
            phase = SessionPhase.NORMAL_INTRADAY
            trading_allowed = not in_no_trade
        elif t_current < self.t_square_off:
            phase = SessionPhase.LATE_SESSION
            trading_allowed = not in_no_trade
        elif t_current < self.t_close:
            phase = SessionPhase.FORCED_SQUARE_OFF
            trading_allowed = False
        else:
            phase = SessionPhase.CLOSED
            trading_allowed = False

        return MarketSessionInfo(
            session_phase=phase,
            minutes_from_open=round(mins_from_open, 2),
            minutes_to_close=round(mins_to_close, 2),
            day_of_week=weekday,
            timestamp_ms=timestamp_ms,
            is_trading_allowed=trading_allowed and not is_square_off,
            is_no_trade_window=in_no_trade or not trading_allowed,
            is_forced_square_off=is_square_off,
        )
