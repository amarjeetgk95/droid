"""Truth-of-Wall backfill pin: settlement gaps are permanent.

When candles are missing for a settlement window, the row stays unsettled
forever — it is never "reconstructed" from neighboring candles, interpolated,
or bridged across a session close. This file pins that contract so a future
"make the dashboards look complete" change trips a test before it ships.

Honest gaps are the product.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ml.sessions import classify_window, resolve_forward_spot
from app.ml.settlement import plan_row


UTC = timezone.utc


def _row(t: datetime, horizon: int = 15, atr: float = 20.0) -> dict:
    return {"symbol": "NIFTY", "timestamp": t, "horizon_minutes": horizon, "atr_at_t": atr}


def _candles(closes: list[float], start: datetime) -> list[tuple[datetime, float]]:
    """1m (timestamp, close) tuples — the format resolve_forward_spot accepts."""
    return [(start + timedelta(minutes=i), c) for i, c in enumerate(closes)]


# The settlement contract is: LAST REAL CLOSE inside [T, T+H], else None.
# A candle at t+5m for a T+15 window is genuine traded data — using it is
# honest. The fabrication risks being pinned here are: reading candles from
# OUTSIDE the window (backfill/bridging), interpolating between real prints,
# averaging/blending, or coercing invalid prices into numbers.
class TestResolveForwardSpotNeverReconstructs:
    T = datetime(2026, 9, 14, 9, 30, tzinfo=UTC)

    def test_empty_history_is_none(self):
        spot, reason = resolve_forward_spot([], self.T, self.T + timedelta(minutes=15))
        assert spot is None
        assert reason == "no-candle-covering-horizon"

    def test_no_candle_inside_window_is_none_not_backfilled(self):
        # Only candles from BEFORE T exist (history backfill temptation):
        # they must never be pulled forward to manufacture a settlement.
        candles = _candles([25000.0, 25001.0], self.T - timedelta(minutes=3))
        spot, reason = resolve_forward_spot(candles, self.T, self.T + timedelta(minutes=15))
        assert spot is None
        assert reason

    def test_candles_after_horizon_never_extrapolated(self):
        # Only candles AFTER T+H exist (future data — would also be leakage):
        # never used.
        candles = _candles([25100.0, 25101.0], self.T + timedelta(minutes=16))
        spot, reason = resolve_forward_spot(candles, self.T, self.T + timedelta(minutes=15))
        assert spot is None
        assert reason

    def test_pre_window_candle_ignored_when_in_window_exists(self):
        # Mixed: a pre-window print must not displace the real in-window close.
        pre = _candles([24000.0], self.T - timedelta(minutes=1))
        inside = _candles([25000.0], self.T + timedelta(minutes=5))
        spot, _ = resolve_forward_spot(pre + inside, self.T, self.T + timedelta(minutes=15))
        assert spot == 25000.0

    def test_invalid_prices_skipped_never_coerced(self):
        # NaN and non-positive closes are dropped, not "fixed" into a number.
        candles = [
            (self.T + timedelta(minutes=1), float("nan")),
            (self.T + timedelta(minutes=2), 0.0),
            (self.T + timedelta(minutes=3), -25000.0),
        ]
        spot, reason = resolve_forward_spot(candles, self.T, self.T + timedelta(minutes=15))
        assert spot is None
        assert reason

    def test_last_real_close_wins_no_averaging(self):
        # Multiple real closes → the LAST one, never a mean/blend.
        candles = _candles([25000.0, 25010.0, 25020.0], self.T + timedelta(minutes=1))
        spot, _ = resolve_forward_spot(candles, self.T, self.T + timedelta(minutes=15))
        assert spot == 25020.0


class TestPlanRowSkipsArePermanent:
    def test_unsettleable_window_is_skip_not_label(self):
        # A window that cannot settle (after close / crossing the session) is
        # SKIPPED — the row stays unsettled, no outcome label is invented.
        t = datetime(2026, 9, 11, 15, 20, tzinfo=UTC)  # Friday, after NSE close in IST
        decision = plan_row(_row(t), [], now_utc=t + timedelta(hours=2))
        assert decision["action"] == "skip"
        assert decision["reason"]

    def test_missing_atr_is_skip(self):
        t = datetime(2026, 9, 14, 9, 30, tzinfo=UTC)
        decision = plan_row(
            {"symbol": "NIFTY", "timestamp": t, "horizon_minutes": 15, "atr_at_t": 0.0},
            [],
            now_utc=t + timedelta(hours=1),
        )
        assert decision["action"] == "skip"
        assert decision["reason"] == "missing-atr-at-t"

    def test_horizon_not_elapsed_is_wait_not_settle(self):
        # Not yet due: WAIT (retried later) — never an early/premature label.
        t = datetime.now(UTC) - timedelta(minutes=5)
        decision = plan_row(_row(t, horizon=15), [], now_utc=datetime.now(UTC))
        assert decision["action"] == "wait"
        assert decision["reason"] == "horizon-not-elapsed"
