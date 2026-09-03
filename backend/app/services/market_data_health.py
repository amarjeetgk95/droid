import time
from datetime import datetime, timezone
from typing import Dict, Any
from app.models.crypto import CryptoHealthResponse


class MarketDataHealthTracker:
    """Tracks latency, subsystem health, and stream freshness for BTC & ETH."""

    def __init__(self):
        self.last_events: Dict[str, float] = {}
        self.subsystem_status: Dict[str, str] = {
            "btc_ticker": "LIVE",
            "btc_orderbook": "LIVE",
            "btc_derivatives": "LIVE",
            "eth_ticker": "LIVE",
            "eth_orderbook": "LIVE",
            "eth_derivatives": "LIVE",
            "websocket": "DISCONNECTED",
        }
        self.stale_threshold_sec = 10.0

    def record_event(self, subsystem: str):
        now = time.time()
        self.last_events[subsystem] = now
        self.subsystem_status[subsystem] = "LIVE"

    def record_ws_state(self, state: str):
        self.subsystem_status["websocket"] = state

    def get_health(self) -> CryptoHealthResponse:
        now = time.time()
        latest_event = max(self.last_events.values()) if self.last_events else now
        last_update_ms = max(0, int((now - latest_event) * 1000))

        # Check for stale components
        for key in ["btc_ticker", "btc_orderbook", "btc_derivatives", "eth_ticker", "eth_orderbook", "eth_derivatives"]:
            last_ts = self.last_events.get(key)
            if last_ts and (now - last_ts) > self.stale_threshold_sec:
                self.subsystem_status[key] = "STALE"

        btc_sub = {
            "ticker": self.subsystem_status.get("btc_ticker", "UNKNOWN"),
            "orderbook": self.subsystem_status.get("btc_orderbook", "UNKNOWN"),
            "derivatives": self.subsystem_status.get("btc_derivatives", "UNKNOWN"),
        }
        eth_sub = {
            "ticker": self.subsystem_status.get("eth_ticker", "UNKNOWN"),
            "orderbook": self.subsystem_status.get("eth_orderbook", "UNKNOWN"),
            "derivatives": self.subsystem_status.get("eth_derivatives", "UNKNOWN"),
        }

        all_live = all(v == "LIVE" for v in btc_sub.values()) and all(v == "LIVE" for v in eth_sub.values())
        overall = "HEALTHY" if all_live else ("DEGRADED" if any(v in ("LIVE", "STALE") for v in list(btc_sub.values()) + list(eth_sub.values())) else "OFFLINE")

        return CryptoHealthResponse(
            btc=btc_sub,
            eth=eth_sub,
            websocket=self.subsystem_status.get("websocket", "DISCONNECTED"),
            last_update_ms=last_update_ms,
            overall_status=overall,
        )


market_health_tracker = MarketDataHealthTracker()
