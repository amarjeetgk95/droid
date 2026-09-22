"""Live 1-minute candle aggregation from FYERS HSM websocket ticks.

Source-of-truth contract
------------------------
The FYERS HSM v1-5 data socket (``app.providers.fyers_ws``) is the primary
market-data source. Ticks are validated by the data-quality engine and then
ingested through :class:`app.services.central_feed.CentralMarketDataFeed`.
This module folds those ticks into **closed** 1-minute OHLCV candles for live
microstructure consumers (VORTEX-SNAP HUD, live scanners).

Honesty guarantees:
- Candles exist only when real ticks arrived. There is no generator and no
  fill-forward of prices: a missing feed yields ``NO_DATA``, never a price.
- A bar is only "closed" when a tick from a later minute arrives. The
  in-progress minute is exposed separately as ``partial`` metadata and is
  never returned as a finished candle.
- Every status carries the tick age so callers can render STALE instead of
  pretending the value is fresh.
- Volume is aggregated from broker cumulative counters when monotonic; when
  the counter resets (new session) the sampled value is used. If the broker
  sends no volume (index ticks), the bar carries 0 and ``volume_available``
  is False — 0 is a measured zero, not an estimate.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

import structlog

from app.models.contracts import TickEvent
from app.signals.strategies.vortex_snap.types import Candle

logger = structlog.get_logger(__name__)

#: Canonical aliases so HUD symbol requests ("NIFTY") match feed symbols
#: ("NIFTY 50"). Keys are upper-cased request symbols.
SYMBOL_ALIASES: Dict[str, str] = {
    "NIFTY": "NIFTY 50",
    "NIFTY50": "NIFTY 50",
    "NIFTY 50": "NIFTY 50",
    "BANKNIFTY": "BANKNIFTY",
    "BANK NIFTY": "BANKNIFTY",
    "SENSEX": "SENSEX",
    "BSE:SENSEX": "SENSEX",
    "FINNIFTY": "FINNIFTY",
    "INDIA VIX": "INDIA VIX",
}


def canonical_symbol(symbol: str) -> str:
    """Map a request symbol to the canonical feed symbol."""
    key = (symbol or "").strip().upper()
    return SYMBOL_ALIASES.get(key, key)


class LiveCandleAggregator:
    """Builds closed 1m candles from live ticks. Synchronous and lock-free.

    Fed directly from the event loop inside ``central_feed.ingest_tick`` — all
    operations are O(1) dict/deque work.
    """

    MAX_BARS = 600
    LIVE_AGE_S = 15.0
    STALE_AGE_S = 120.0

    def __init__(self, max_bars: int = MAX_BARS) -> None:
        self.max_bars = max_bars
        self._bars: Dict[str, Deque[Candle]] = {}
        self._partial: Dict[str, Dict[str, Any]] = {}
        self._last_tick_at: Dict[str, datetime] = {}
        self.total_ticks: int = 0
        self.total_bars_closed: int = 0

    # ------------------------------------------------------------------
    # Ingestion (hot path)
    # ------------------------------------------------------------------
    @staticmethod
    def _aware_utc(ts: datetime) -> datetime:
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)

    @staticmethod
    def _minute_start(ts: datetime) -> datetime:
        return ts.replace(second=0, microsecond=0)

    @staticmethod
    def _minute_start_ms(ts: datetime) -> int:
        return int(ts.replace(second=0, microsecond=0).timestamp() * 1000)

    def on_tick(self, tick: TickEvent) -> bool:
        """Fold a validated tick into the current 1m bucket.

        Returns True when a candle was closed by this tick. Never raises into
        the feed ingestion path.
        """
        try:
            price = float(tick.ltp)
            if price <= 0:
                return False
            ts = self._aware_utc(tick.timestamp)
            key = canonical_symbol(tick.symbol)
            minute = self._minute_start(ts)

            # Freshness: only move forward; late replays must not age the feed.
            prev_seen = self._last_tick_at.get(key)
            if prev_seen is None or ts > prev_seen:
                self._last_tick_at[key] = ts

            self.total_ticks += 1

            state = self._partial.get(key)
            closed = False

            if state is None:
                self._partial[key] = self._new_bucket(minute, price, tick)
                return False

            if minute > state["minute"]:
                # Roll: close the completed bucket, start the new one.
                self._close_bucket(key, state)
                closed = True
                self._partial[key] = self._new_bucket(minute, price, tick)
                return closed

            if minute < state["minute"]:
                # Out-of-order tick for an already-closed minute: ignore for bar
                # construction (never rewrite history).
                return False

            # Same minute: extend the bucket.
            if price > state["high"]:
                state["high"] = price
            if price < state["low"]:
                state["low"] = price
            state["close"] = price
            state["ticks"] += 1
            self._add_volume(state, tick)
            return False
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("live_candle_on_tick_failed", symbol=getattr(tick, "symbol", "?"), error=str(exc)[:150])
            return False

    def _new_bucket(self, minute: datetime, price: float, tick: TickEvent) -> Dict[str, Any]:
        state: Dict[str, Any] = {
            "minute": minute,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": 0.0,
            "ticks": 1,
        }
        self._add_volume(state, tick)
        return state

    def _add_volume(self, state: Dict[str, Any], tick: TickEvent) -> None:
        try:
            cum = int(tick.volume or 0)
        except (TypeError, ValueError):
            return
        key_vol = state.get("last_cum")
        if cum <= 0:
            return
        if key_vol is None:
            # First cumulative sample: the increment is unknown, so we record
            # nothing rather than inventing a delta.
            delta = 0
        elif cum >= key_vol:
            delta = cum - key_vol
        else:
            # Counter reset (new session): treat the sample as the new baseline.
            delta = cum
        state["volume"] = float(state.get("volume", 0.0)) + float(max(0, delta))
        state["last_cum"] = cum

    def _close_bucket(self, key: str, state: Dict[str, Any]) -> None:
        candle = Candle(
            timestamp=self._minute_start_ms(state["minute"]),
            open=round(float(state["open"]), 4),
            high=round(float(state["high"]), 4),
            low=round(float(state["low"]), 4),
            close=round(float(state["close"]), 4),
            volume=round(float(state["volume"]), 2),
        )
        bucket = self._bars.setdefault(key, deque(maxlen=self.max_bars))
        bucket.append(candle)
        self.total_bars_closed += 1

    # ------------------------------------------------------------------
    # Read side
    # ------------------------------------------------------------------
    def get_candles(self, symbol: str, count: int = 120) -> Tuple[List[Candle], Dict[str, Any]]:
        """Return the last ``count`` closed 1m candles plus an honest status dict."""
        key = canonical_symbol(symbol)
        bars: List[Candle] = list(self._bars.get(key, ()))[-max(0, int(count)):] if count else []
        return bars, self.status(symbol)

    def status(self, symbol: str) -> Dict[str, Any]:
        """Feed status for a symbol: LIVE / STALE / DOWN / NO_DATA + age + partial progress."""
        key = canonical_symbol(symbol)
        now = datetime.now(timezone.utc)
        last_at = self._last_tick_at.get(key)
        age_s: Optional[float] = (now - last_at).total_seconds() if last_at else None

        if last_at is None:
            feed_status = "NO_DATA"
        elif age_s is not None and age_s <= self.LIVE_AGE_S:
            feed_status = "LIVE"
        elif age_s is not None and age_s <= self.STALE_AGE_S:
            feed_status = "STALE"
        else:
            feed_status = "DOWN"

        bars: List[Candle] = list(self._bars.get(key, ()))
        last_closed = bars[-1] if bars else None
        partial = self._partial.get(key)
        volume_available = any(b.volume > 0 for b in bars[-30:])

        return {
            "symbol": key,
            "request_symbol": (symbol or "").strip().upper(),
            "status": feed_status,
            "age_s": round(age_s, 2) if age_s is not None else None,
            "bars": len(bars),
            "last_candle_timestamp_ms": last_closed.timestamp if last_closed else None,
            "last_candle_close": last_closed.close if last_closed else None,
            "partial_minute_timestamp_ms": self._minute_start_ms(partial["minute"]) if partial else None,
            "partial_ticks": int(partial["ticks"]) if partial else 0,
            "partial_close": round(float(partial["close"]), 4) if partial else None,
            "volume_available": volume_available,
            "provider": "fyers_hsm_ws",
        }

    def reset(self) -> None:
        """Clear all state (e.g. process restart / explicit test hook)."""
        self._bars.clear()
        self._partial.clear()
        self._last_tick_at.clear()


#: Process-wide singleton fed by ``central_feed.ingest_tick``.
live_candles = LiveCandleAggregator()
