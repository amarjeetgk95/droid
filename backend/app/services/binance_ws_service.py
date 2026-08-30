"""Binance WebSocket Market-Data Service.

Implements real-time market data via Binance public WebSocket streams
with automatic reconnection. REST is used only for initial snapshot /
historical candles. No trading permissions required.

Spot vs Futures routing (per task requirement):
  - spot    -> wss://data-stream.binance.vision (fallback stream.binance.com:9443)
  - futures -> wss://fstream.binance.com (USD-M perpetual futures)

Streams (public, no API key):
  - <symbol>@ticker        -> 24hr rolling ticker
  - <symbol>@kline_<interval> -> candlestick
  - <symbol>@depth         -> order book diff
  - <symbol>@depth@100ms   -> order book throttled
  - !ticker@arr            -> all tickers array (optional)

Reference:
  Spot:   https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
  Futures:https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams
"""

import asyncio
import json
import random
from datetime import datetime, timezone
from typing import Literal, Set, Dict, Any, Callable
import structlog

logger = structlog.get_logger()

BinanceMarket = Literal["spot", "futures"]

# Public WebSocket endpoints (no authentication)
SPOT_WS_COMBINED_URL = "wss://data-stream.binance.vision/stream"
SPOT_WS_FALLBACK_COMBINED_URL = "wss://stream.binance.com:9443/stream"
FUTURES_WS_COMBINED_URL = "wss://fstream.binance.com/stream"
FUTURES_WS_FALLBACK_COMBINED_URL = "wss://fstream.binance.com/stream"

# For single-stream ws (alternative)
SPOT_WS_BASE = "wss://data-stream.binance.vision/ws"
FUTURES_WS_BASE = "wss://fstream.binance.com/ws"

DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT",
]

def get_binance_ws_url(market: BinanceMarket, combined: bool = True) -> str:
    """Return the correct Binance WebSocket URL for the selected market.

    This is the verification point for task requirement: correct stream per market.
    """
    if market == "futures":
        return FUTURES_WS_COMBINED_URL if combined else FUTURES_WS_BASE
    # default spot
    return SPOT_WS_COMBINED_URL if combined else SPOT_WS_BASE


def build_combined_stream_url(market: BinanceMarket, streams: list[str]) -> str:
    """Build combined stream URL: wss://.../stream?streams=btcusdt@ticker/btcusdt@kline_1m"""
    base = get_binance_ws_url(market, combined=True)
    query = "/".join(s.lower() for s in streams)
    return f"{base}?streams={query}"


def build_ticker_streams(symbols: list[str]) -> list[str]:
    return [f"{s.lower()}@ticker" for s in symbols]


def build_kline_streams(symbol: str, interval: str) -> list[str]:
    return [f"{symbol.lower()}@kline_{interval}"]


def build_depth_streams(symbol: str, update_speed: str = "100ms") -> list[str]:
    # Use 100ms throttled depth for lower bandwidth; or plain @depth
    if update_speed:
        return [f"{symbol.lower()}@depth@{update_speed}"]
    return [f"{symbol.lower()}@depth"]


def build_markprice_streams(symbol: str, interval: str = "1s") -> list[str]:
    # Futures markPrice stream @1s includes fundingRate (r) and nextFundingTime (T)
    return [f"{symbol.lower()}@markPrice@{interval}"]


def build_markprice_arr_stream(interval: str = "1s") -> str:
    return f"!markPrice@arr@{interval}"


class BinanceWebSocketManager:
    """Manages persistent Binance WebSocket connections with auto-reconnect.

    One upstream connection per market, broadcasting parsed events to registered
    async callbacks / WebSocket clients. Implements exponential backoff with jitter.
    """

    def __init__(self):
        self._tasks: Dict[str, asyncio.Task | None] = {}
        self._running: Dict[str, bool] = {}
        self._reconnect_counts: Dict[str, int] = {"spot": 0, "futures": 0}
        self._subscribers: Dict[str, Set[Callable[[dict], Any]]] = {"spot": set(), "futures": set()}
        self._lock = asyncio.Lock()

        # Telemetry
        self.started_at: datetime | None = None
        self.last_event_at: datetime | None = None
        self.total_events: int = 0

    async def start(self, market: BinanceMarket = "spot", symbols: list[str] | None = None) -> None:
        """Start background loop for market. Safe to call multiple times."""
        symbols = symbols or DEFAULT_SYMBOLS
        if self._running.get(market):
            return
        self._running[market] = True
        self.started_at = datetime.now(timezone.utc)
        self._tasks[market] = asyncio.create_task(self._run_loop(market, symbols))
        logger.info("binance_ws_started", market=market, symbols=symbols)

    async def stop(self, market: BinanceMarket | None = None) -> None:
        """Stop one or all markets."""
        markets = [market] if market else ["spot", "futures"]
        for m in markets:
            self._running[m] = False
            task = self._tasks.get(m)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                self._tasks[m] = None
            logger.info("binance_ws_stopped", market=m)

    def subscribe(self, market: BinanceMarket, callback: Callable[[dict], Any]) -> None:
        self._subscribers[market].add(callback)

    def unsubscribe(self, market: BinanceMarket, callback: Callable[[dict], Any]) -> None:
        self._subscribers[market].discard(callback)

    async def _run_loop(self, market: BinanceMarket, symbols: list[str]) -> None:
        """Persistent connect-loop with exponential backoff."""
        backoff = 1.0
        max_backoff = 30.0

        streams = build_ticker_streams(symbols)
        url = build_combined_stream_url(market, streams)

        while self._running.get(market):
            try:
                await self._connect_and_consume(market, url, streams)
                # Normal close -> reset backoff
                backoff = 1.0
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("binance_ws_connection_failed", market=market, error=str(e), backoff=backoff)
                self._reconnect_counts[market] += 1

            # Backoff before reconnect
            jitter = random.uniform(0, 0.5)
            delay = min(max_backoff, backoff + jitter)
            logger.info("binance_ws_reconnect_scheduled", market=market, delay=delay, reconnect_count=self._reconnect_counts[market])
            await asyncio.sleep(delay)
            backoff = min(max_backoff, backoff * 1.5 + jitter)
            # Rebuild URL in case symbols changed (future: dynamic resub)
            url = build_combined_stream_url(market, streams)

    async def _connect_and_consume(self, market: BinanceMarket, url: str, streams: list[str]) -> None:
        import websockets

        # Use Binance combined stream endpoint - no api key / no auth
        fallback_used = False
        connect_urls = [url]
        # Add fallback mirror for spot
        if market == "spot":
            fallback_query = "/".join(s.lower() for s in streams)
            connect_urls.append(f"{SPOT_WS_FALLBACK_COMBINED_URL}?streams={fallback_query}")

        last_exc = None
        for attempt_url in connect_urls:
            try:
                logger.info("binance_ws_connecting", market=market, url=attempt_url)
                async with websockets.connect(
                    attempt_url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    max_queue=None,
                ) as ws:
                    logger.info("binance_ws_connected", market=market, url=attempt_url)
                    # Reset reconnect backoff on success
                    self._reconnect_counts[market] = max(0, self._reconnect_counts[market] - 1) if self._reconnect_counts[market] > 0 else 0
                    async for raw_msg in ws:
                        if not self._running.get(market):
                            return
                        try:
                            payload = json.loads(raw_msg)
                            # Combined stream wraps: {"stream":"btcusdt@ticker","data":{...}}
                            # Single array stream !ticker@arr gives list
                            event = None
                            stream_name = None
                            if isinstance(payload, dict) and "stream" in payload and "data" in payload:
                                stream_name = payload["stream"]
                                event = payload["data"]
                            elif isinstance(payload, dict) and "e" in payload:
                                event = payload
                            elif isinstance(payload, list):
                                # !ticker@arr
                                for ev in payload:
                                    await self._handle_event(market, ev, None)
                                continue
                            else:
                                # Unknown format, try to handle as event
                                event = payload

                            if event is not None:
                                await self._handle_event(market, event, stream_name)
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            logger.warning("binance_ws_event_handle_error", market=market, error=str(e))
                            continue
                # If we exit context normally, reconnect
                return
            except Exception as e:
                last_exc = e
                logger.warning("binance_ws_connect_failed", market=market, url=attempt_url, error=str(e))
                if attempt_url != connect_urls[-1]:
                    continue
                else:
                    raise last_exc

    async def _handle_event(self, market: BinanceMarket, event: dict, stream_name: str | None) -> None:
        """Normalize and broadcast event to subscribers."""
        # Tag with market for downstream routing
        wrapped = {
            "market": market,
            "stream": stream_name,
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.last_event_at = datetime.now(timezone.utc)
        self.total_events += 1

        # Broadcast to subscribers
        for cb in list(self._subscribers[market]):
            try:
                result = cb(wrapped)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning("binance_ws_subscriber_error", market=market, error=str(e))

    def get_telemetry(self) -> dict:
        return {
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
            "total_events": self.total_events,
            "reconnect_counts": dict(self._reconnect_counts),
            "running_markets": [k for k, v in self._running.items() if v],
            "subscriber_counts": {k: len(v) for k, v in self._subscribers.items()},
            "spot_ws_url": get_binance_ws_url("spot"),
            "futures_ws_url": get_binance_ws_url("futures"),
        }


# Global singleton
binance_ws_manager = BinanceWebSocketManager()


# Helper to parse ticker events into normalized tick for central feed (optional)
def parse_ticker_to_tick_event(event: dict, market: BinanceMarket) -> dict | None:
    """Convert Binance 24hrTicker event to normalized tick dict.

    Spot ticker fields (per docs): s, c, P, p, h, l, v, q, o etc.
    Futures similar. No API key needed.
    """
    try:
        # event type check
        if event.get("e") not in ("24hrTicker", "24hrMiniTicker", "ticker"):
            # Sometimes combined stream may still be ticker but without e? fallback to c field
            if "c" not in event or "s" not in event:
                return None
        symbol = event.get("s") or event.get("symbol")
        if not symbol:
            return None
        price = float(event.get("c") or event.get("lastPrice") or 0)
        open_price = float(event.get("o") or event.get("openPrice") or price)
        high = float(event.get("h") or event.get("highPrice") or price)
        low = float(event.get("l") or event.get("lowPrice") or price)
        volume = float(event.get("v") or event.get("volume") or 0)
        # quote volume not needed for tick
        change_pct = float(event.get("P") or event.get("priceChangePercent") or 0)
        # Binance event time
        event_time_ms = event.get("E") or event.get("eventTime") or None
        ts = datetime.now(timezone.utc)
        if event_time_ms:
            try:
                ts = datetime.fromtimestamp(int(event_time_ms) / 1000.0, tz=timezone.utc)
            except Exception:
                pass

        return {
            "symbol": symbol,
            "price": price,
            "open": open_price,
            "high": high,
            "low": low,
            "volume": volume,
            "change_percent": change_pct,
            "timestamp": ts.isoformat(),
            "provider": f"binance_{market}",
            "raw": event,
        }
    except Exception:
        return None
