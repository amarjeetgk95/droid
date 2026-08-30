import pytest
import json
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app
from app.services.central_feed import central_feed
from app.models.contracts import TickEvent, EventPriority


class TestWebSocketFeed:
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
            response = json.loads(websocket.receive_text())
            assert response["type"] == "PONG"
            assert "timestamp" in response

    def test_websocket_subscribe_action(self):
        client = TestClient(app)
        with client.websocket_connect("/api/v1/ws/market-feed") as websocket:
            # Skip welcome msg
            websocket.receive_text()

            # Subscribe to symbol
            websocket.send_text(json.dumps({"action": "SUBSCRIBE", "symbol": "RELIANCE"}))
            response = json.loads(websocket.receive_text())
            assert response["type"] == "SUBSCRIBED"
            assert response["symbol"] == "RELIANCE"
            assert "RELIANCE" in central_feed.get_subscriptions()
