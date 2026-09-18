import pytest
import json
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app
from app.services.central_feed import central_feed
from app.models.contracts import TickEvent, EventPriority


class TestWebSocketFeed:
    @staticmethod
    def _receive_until(websocket, expected_type, max_frames=6):
        """Drain frames until the expected type arrives.

        The server may push an unsolicited snapshot `MARKET_TICKS` catch-up
        frame before command replies, so tests must not assume frame order.
        """
        for _ in range(max_frames):
            response = json.loads(websocket.receive_text())
            if response["type"] == expected_type:
                return response
        raise AssertionError(f"{expected_type} not received within {max_frames} frames")

    def test_websocket_connect_and_welcome(self):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/ws/market-feed") as websocket:
            data = websocket.receive_text()
            msg = json.loads(data)
            assert msg["type"] == "CONNECTION_ESTABLISHED"
            assert "subscriptions" in msg
            assert "telemetry" in msg

    def test_websocket_ping_pong(self):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/ws/market-feed") as websocket:
            # Skip welcome msg
            websocket.receive_text()

            # Send PING
            websocket.send_text(json.dumps({"action": "PING"}))
            response = self._receive_until(websocket, "PONG")
            assert "timestamp" in response

    def test_websocket_subscribe_action(self):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/ws/market-feed") as websocket:
            # Skip welcome msg
            websocket.receive_text()

            # Subscribe to symbol
            websocket.send_text(json.dumps({"action": "SUBSCRIBE", "symbol": "RELIANCE"}))
            response = self._receive_until(websocket, "SUBSCRIBED")
            assert response["symbol"] == "RELIANCE"
            assert "RELIANCE" in central_feed.get_subscriptions()
