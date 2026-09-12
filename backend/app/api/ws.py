import asyncio
import json
import random
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.central_feed import central_feed
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
    client_queue = await central_feed.register_client(websocket)

    # Send initial welcome and state message
    welcome_msg = {
        "type": "CONNECTION_ESTABLISHED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "subscriptions": central_feed.get_subscriptions(),
        "telemetry": central_feed.get_telemetry(),
    }
    await websocket.send_text(json.dumps(welcome_msg))

    # Snapshot catch-up: push latest cached market snapshot before live stream.
    # Served via central_feed.get_snapshot() (coordinator-backed, O(1) upstream).
    try:
        snapshot = await central_feed.get_snapshot()
        initial_ticks = snapshot.get("ticks", [])
        if initial_ticks:
            now_iso = datetime.now(timezone.utc).isoformat()
            stamped = []
            for t in initial_ticks:
                tick = dict(t)
                tick.setdefault("timestamp", now_iso)
                stamped.append(tick)
            await websocket.send_text(json.dumps({
                "type": "MARKET_TICKS",
                "timestamp": now_iso,
                "ticks": stamped,
                "snapshot": True,
                "snapshot_source": snapshot.get("source", "unknown"),
            }))
    except Exception as e:
        logger.debug("ws_initial_ticks_snapshot_failed", error=str(e)[:150])

    stop_event = asyncio.Event()

    async def sender_loop():
        """Pulls messages from the client's bounded queue and sends to websocket.

        The queue is bounded (maxsize=50) with drop-oldest backpressure in the
        broadcast worker, so this loop never blocks the hub. A slow client that
        stops draining is evicted by the hub (see SLOW_CONSUMER thresholds).
        Dispatches lightweight heartbeat when idle for 15.0s, eliminating
        concurrent socket write collisions.
        """
        while not stop_event.is_set():
            try:
                try:
                    msg = await asyncio.wait_for(client_queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    if not stop_event.is_set():
                        await websocket.send_text(json.dumps({
                            "type": "HEARTBEAT",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }))
                    continue
                await websocket.send_text(msg)
            except asyncio.CancelledError:
                break
            except Exception:
                break

    sender_task = asyncio.create_task(sender_loop())

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
        sender_task.cancel()
        try:
            await sender_task
        except (asyncio.CancelledError, Exception):
            pass

