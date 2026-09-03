import asyncio
import json
import random
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.central_feed import central_feed
from app.services.binance_ws_service import (
    get_binance_ws_url,
    build_combined_stream_url,
    build_ticker_streams,
    DEFAULT_SYMBOLS,
    parse_ticker_to_tick_event,
    binance_ws_manager,
)
import structlog

logger = structlog.get_logger()
router = APIRouter(tags=["websocket"])


@router.websocket("/api/v1/ws/market-feed")
async def websocket_market_feed(websocket: WebSocket):
    """Central real-time WebSocket market data feed.

    LIFECYCLE CONTRACT (frontend subscribe-only):
      - Connect:    register this client socket ONLY (central_feed).
      - Disconnect: unregister this client socket ONLY + cancel this
        connection's own feed task. NEVER stops/restarts the backend-owned
        FYERS stream or Telegram services — those live in lifespan.
      - Closing the browser/dashboard tab therefore cannot affect FYERS or
        Telegram. Dashboard is fully independent of their lifecycle.
    """
    await websocket.accept()
    await central_feed.register_client(websocket)

    # Send initial welcome and state message
    welcome_msg = {
        "type": "CONNECTION_ESTABLISHED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "subscriptions": central_feed.get_subscriptions(),
        "telemetry": central_feed.get_telemetry(),
    }
    await websocket.send_text(json.dumps(welcome_msg))

    # Push initial current prices as MARKET_TICKS so frontend gets immediate live data
    try:
        from app.services.market_service import MarketService
        _svc = MarketService()
        cards = await _svc.get_index_cards()
        if cards:
            now_iso = datetime.now(timezone.utc).isoformat()
            initial_ticks = []
            for c in cards:
                if c.ltp is not None and c.ltp > 0:
                    initial_ticks.append({
                        "timestamp": now_iso,
                        "symbol": c.symbol,
                        "instrument_token": c.symbol,
                        "ltp": float(c.ltp),
                        "open": float(c.open) if c.open else float(c.ltp),
                        "high": float(c.high) if c.high else float(c.ltp),
                        "low": float(c.low) if c.low else float(c.ltp),
                        "close": float(c.previous_close) if c.previous_close else float(c.ltp),
                        "volume": int(c.volume) if c.volume else 0,
                        "open_interest": c.open_interest,
                        "provider": c.provider,
                    })
            if initial_ticks:
                await websocket.send_text(json.dumps({
                    "type": "MARKET_TICKS",
                    "timestamp": now_iso,
                    "ticks": initial_ticks,
                }))
    except Exception as e:
        logger.debug("ws_initial_ticks_snapshot_failed", error=str(e)[:150])

    stop_event = asyncio.Event()

    async def periodic_feed_loop():
        """Periodically broadcast fresh ticks or heartbeats to keep the feed realtime & alive."""
        from app.services.market_service import MarketService
        service = MarketService()
        while not stop_event.is_set():
            try:
                await asyncio.sleep(1.0)
                if stop_event.is_set():
                    break
                now = datetime.now(timezone.utc)
                last_b = central_feed.last_broadcast_at
                # If central_feed has not broadcasted in 0.9s, push latest quotes as ticks
                is_quiet = (last_b is None) or ((now - last_b).total_seconds() > 0.9)
                if is_quiet:
                    fresh_cards = await service.get_index_cards()
                    now_iso = now.isoformat()
                    ticks_payload = []
                    for c in fresh_cards:
                        if c.ltp is not None and c.ltp > 0:
                            ticks_payload.append({
                                "timestamp": now_iso,
                                "symbol": c.symbol,
                                "instrument_token": c.symbol,
                                "ltp": float(c.ltp),
                                "open": float(c.open) if c.open else float(c.ltp),
                                "high": float(c.high) if c.high else float(c.ltp),
                                "low": float(c.low) if c.low else float(c.ltp),
                                "close": float(c.previous_close) if c.previous_close else float(c.ltp),
                                "volume": int(c.volume) if c.volume else 0,
                                "open_interest": c.open_interest,
                                "provider": c.provider,
                            })
                    if ticks_payload:
                        await websocket.send_text(json.dumps({
                            "type": "MARKET_TICKS",
                            "timestamp": now_iso,
                            "ticks": ticks_payload,
                        }))
                    else:
                        await websocket.send_text(json.dumps({
                            "type": "HEARTBEAT",
                            "timestamp": now_iso,
                        }))
            except Exception:
                break

    feed_task = asyncio.create_task(periodic_feed_loop())

    try:
        while True:
            # Keep connection open and handle incoming client commands (e.g. subscribe / ping)
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action")
                if action == "PING":
                    await websocket.send_text(json.dumps({
                        "type": "PONG",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
                elif action == "SUBSCRIBE":
                    symbol = msg.get("symbol")
                    if symbol:
                        central_feed.add_subscription(symbol)
                        await websocket.send_text(json.dumps({
                            "type": "SUBSCRIBED",
                            "symbol": symbol,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await central_feed.unregister_client(websocket)
    except Exception as e:
        logger.warning("ws_connection_error", error=str(e))
        await central_feed.unregister_client(websocket)
    finally:
        stop_event.set()
        feed_task.cancel()
        try:
            await feed_task
        except asyncio.CancelledError:
            pass


@router.websocket("/api/v1/ws/crypto")
async def websocket_crypto_feed(websocket: WebSocket):
    """Binance live market-data WebSocket proxy (Spot & Futures).

    - Uses Binance **public** market-data WebSocket streams (no trading permissions).
    - Keeps REST only for initial snapshot / historical candles (served via /api/v1/crypto/*).
    - Auto-reconnects to Binance if disconnected (exponential backoff with jitter).
    - Selects correct Binance stream per market: spot -> data-stream.binance.vision,
      futures -> fstream.binance.com (verified via get_binance_ws_url).
    - Pushes live ticker / kline / depth events to frontend without page refresh.
    """
    await websocket.accept()

    # Query params: market=spot|futures, symbols=BTCUSDT,ETHUSDT,...
    params = websocket.query_params
    market = params.get("market", "spot").lower()
    if market not in ("spot", "futures"):
        market = "spot"

    symbols_param = params.get("symbols", "")
    from app.models.crypto import ALLOWED_CRYPTO_SYMBOLS
    if symbols_param:
        req_syms = [s.strip().upper() for s in symbols_param.split(",") if s.strip()]
        req_syms = [s if (s.endswith("USDT") or s.endswith("BTC")) else f"{s}USDT" for s in req_syms]
        symbols = [s for s in req_syms if s in ALLOWED_CRYPTO_SYMBOLS]
        if not symbols:
            symbols = ["BTCUSDT", "ETHUSDT"]
    else:
        symbols = ["BTCUSDT", "ETHUSDT"]

    interval = params.get("interval", "1m")  # for kline stream if requested
    streams_param = params.get("streams", "ticker")  # comma: ticker,kline,depth
    requested_streams = [s.strip().lower() for s in streams_param.split(",") if s.strip()]

    # Build Binance stream names based on request (depth, kline, funding/markPrice realtime)
    binance_streams: list[str] = []
    if "ticker" in requested_streams:
        binance_streams.extend(build_ticker_streams(symbols))
    # Depth, kline, funding are typically for a single selected symbol (first in list)
    primary_symbol = symbols[0] if symbols else "BTCUSDT"
    if "kline" in requested_streams:
        binance_streams.append(f"{primary_symbol.lower()}@kline_{interval}")
    if "depth" in requested_streams:
        binance_streams.append(f"{primary_symbol.lower()}@depth@100ms")
    # Funding rate realtime via markPrice@1s (futures only)
    if "funding" in requested_streams or "markprice" in requested_streams:
        from app.services.binance_ws_service import build_markprice_streams
        binance_streams.extend(build_markprice_streams(primary_symbol, "1s"))
    # If market is futures and ticker requested, also include funding by default for derivatives card
    if market == "futures" and "depth" in requested_streams and "funding" not in requested_streams and "markprice" not in requested_streams:
        from app.services.binance_ws_service import build_markprice_streams as _bms
        binance_streams.extend(_bms(primary_symbol, "1s"))

    # Verify correct stream URL per market (task requirement)
    combined_url = build_combined_stream_url(market, binance_streams)
    spot_url = get_binance_ws_url("spot")
    futures_url = get_binance_ws_url("futures")
    verified_url = get_binance_ws_url(market)  # type: ignore

    welcome = {
        "type": "CONNECTION_ESTABLISHED",
        "market": market,
        "verified_ws_url": verified_url,
        "combined_url": combined_url,
        "symbols": symbols,
        "streams": binance_streams,
        "spot_ws_url": spot_url,
        "futures_ws_url": futures_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": "Binance public market-data stream (no auth required)",
    }
    await websocket.send_text(json.dumps(welcome))

    # State for handling SUBSCRIBE / MARKET_SWITCH from client
    active_market = market
    active_streams = binance_streams
    active_symbols = symbols
    active_url = combined_url

    # Use shared manager for ticker broadcasting + per-connection proxy for other streams.
    # For simplicity, proxy directly via websockets with auto-reconnect per connection.

    stop_event = asyncio.Event()
    binance_task: asyncio.Task | None = None

    async def binance_proxy_loop():
        backoff = 1.0
        max_backoff = 30.0
        while not stop_event.is_set():
            try:
                import websockets
                logger.info("crypto_ws_proxy_connecting", market=active_market, url=active_url)
                async with websockets.connect(
                    active_url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    max_queue=None,
                ) as binance_ws:
                    logger.info("crypto_ws_proxy_connected", market=active_market)
                    backoff = 1.0
                    # Send subscribed confirmation
                    try:
                        await websocket.send_text(json.dumps({
                            "type": "BINANCE_CONNECTED",
                            "market": active_market,
                            "streams": active_streams,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }))
                    except Exception:
                        pass

                    async for raw in binance_ws:
                        if stop_event.is_set():
                            return
                        try:
                            payload = json.loads(raw)
                            # Normalize combined stream envelope
                            if isinstance(payload, dict) and "stream" in payload and "data" in payload:
                                stream = payload["stream"]
                                data = payload["data"]
                            elif isinstance(payload, list):
                                # All tickers array - forward as batch
                                await websocket.send_text(json.dumps({
                                    "type": "BINANCE_TICKERS_BATCH",
                                    "market": active_market,
                                    "data": payload,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }))
                                continue
                            else:
                                stream = active_streams[0] if active_streams else ""
                                data = payload

                            # Determine event type
                            event_type = data.get("e", "")
                            # Enrich and forward with typed wrappers for frontend instant update
                            if event_type == "24hrTicker" or ("c" in data and "s" in data):
                                parsed = parse_ticker_to_tick_event(data, active_market)  # type: ignore
                                await websocket.send_text(json.dumps({
                                    "type": "BINANCE_TICKER",
                                    "market": active_market,
                                    "symbol": data.get("s"),
                                    "stream": stream,
                                    "price": parsed["price"] if parsed else float(data.get("c", 0)),
                                    "data": data,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }))
                            elif event_type == "kline":
                                k = data.get("k", {})
                                await websocket.send_text(json.dumps({
                                    "type": "BINANCE_KLINE",
                                    "market": active_market,
                                    "symbol": k.get("s") or data.get("s"),
                                    "stream": stream,
                                    "data": data,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }))
                            elif event_type == "depthUpdate":
                                await websocket.send_text(json.dumps({
                                    "type": "BINANCE_DEPTH",
                                    "market": active_market,
                                    "symbol": data.get("s"),
                                    "stream": stream,
                                    "data": data,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }))
                            elif event_type == "markPriceUpdate" or "markPrice" in stream:
                                # Realtime funding rate + markPrice (futures)
                                await websocket.send_text(json.dumps({
                                    "type": "BINANCE_MARK_PRICE",
                                    "market": active_market,
                                    "symbol": data.get("s"),
                                    "stream": stream,
                                    "markPrice": data.get("p"),
                                    "indexPrice": data.get("i"),
                                    "fundingRate": data.get("r"),
                                    "nextFundingTime": data.get("T"),
                                    "data": data,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }))
                            else:
                                # Generic forward
                                await websocket.send_text(json.dumps({
                                    "type": "BINANCE_EVENT",
                                    "market": active_market,
                                    "stream": stream,
                                    "data": data,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }))
                        except Exception as e:
                            logger.debug("crypto_ws_forward_error", error=str(e))
                            continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("crypto_ws_proxy_error", market=active_market, error=str(e))
                if stop_event.is_set():
                    break
                jitter = random.uniform(0, 0.5)
                delay = min(max_backoff, backoff * 1.5 + jitter)
                try:
                    await websocket.send_text(json.dumps({
                        "type": "BINANCE_RECONNECTING",
                        "market": active_market,
                        "delay_seconds": round(delay, 2),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
                except Exception:
                    pass
                await asyncio.sleep(delay)
                backoff = delay

    binance_task = asyncio.create_task(binance_proxy_loop())

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action")
                if action == "PING":
                    await websocket.send_text(json.dumps({
                        "type": "PONG",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
                elif action == "SUBSCRIBE":
                    # Dynamic resubscribe: client can change symbol/market/streams on the fly
                    new_market = msg.get("market", active_market).lower()
                    if new_market not in ("spot", "futures"):
                        new_market = active_market
                    new_symbols = msg.get("symbols") or msg.get("symbol")
                    if isinstance(new_symbols, str):
                        new_symbols = [new_symbols]
                    if new_symbols:
                        new_symbols = [s.upper() if s.upper().endswith("USDT") else f"{s.upper()}USDT" for s in new_symbols]
                    else:
                        new_symbols = active_symbols

                    new_interval = msg.get("interval", interval)
                    new_streams_req = msg.get("streams") or requested_streams
                    if isinstance(new_streams_req, str):
                        new_streams_req = [s.strip() for s in new_streams_req.split(",")]

                    new_bStreams: list[str] = []
                    if "ticker" in new_streams_req:
                        new_bStreams.extend(build_ticker_streams(new_symbols))  # type: ignore
                    primary = new_symbols[0] if new_symbols else "BTCUSDT"  # type: ignore
                    if "kline" in new_streams_req:
                        new_bStreams.append(f"{primary.lower()}@kline_{new_interval}")
                    if "depth" in new_streams_req:
                        new_bStreams.append(f"{primary.lower()}@depth@100ms")
                    if "funding" in new_streams_req or "markprice" in new_streams_req:
                        from app.services.binance_ws_service import build_markprice_streams as _bms2
                        new_bStreams.extend(_bms2(primary, "1s"))  # type: ignore
                    # Auto-include funding realtime when futures depth is subscribed (derivatives card)
                    if new_market == "futures" and "depth" in new_streams_req and "funding" not in new_streams_req and "markprice" not in new_streams_req:
                        from app.services.binance_ws_service import build_markprice_streams as _bms3
                        new_bStreams.extend(_bms3(primary, "1s"))  # type: ignore
                    if not new_bStreams:
                        new_bStreams = build_ticker_streams(new_symbols)  # type: ignore

                    new_url = build_combined_stream_url(new_market, new_bStreams)  # type: ignore

                    active_market = new_market  # type: ignore
                    active_symbols = new_symbols  # type: ignore
                    active_streams = new_bStreams
                    active_url = new_url

                    # Restart proxy loop with new URL
                    if binance_task:
                        binance_task.cancel()
                        try:
                            await binance_task
                        except asyncio.CancelledError:
                            pass
                    stop_event.clear()
                    binance_task = asyncio.create_task(binance_proxy_loop())

                    await websocket.send_text(json.dumps({
                        "type": "SUBSCRIBED",
                        "market": active_market,
                        "symbols": active_symbols,
                        "streams": active_streams,
                        "combined_url": active_url,
                        "verified_ws_url": get_binance_ws_url(active_market),  # type: ignore
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
                elif action == "UNSUBSCRIBE":
                    # No-op, keep connection but client can filter locally
                    await websocket.send_text(json.dumps({
                        "type": "UNSUBSCRIBED",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("crypto_ws_error", error=str(e))
    finally:
        stop_event.set()
        if binance_task:
            binance_task.cancel()
            try:
                await binance_task
            except asyncio.CancelledError:
                pass
