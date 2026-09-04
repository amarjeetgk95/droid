import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.institutional.telegram_notifications import SignalEvent
from app.institutional.telegram_templates import format_signal_state, _format_ist_timestamp
from app.services.paper_service import paper_service


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_paper(mock_market_open):
    paper_service.reset_portfolio()


class TestSignalsPaperIntegration:

    def test_telegram_template_timestamp_and_paper_receipt(self):
        ev = SignalEvent(
            event_type="SIGNAL_CONFIRMED",
            signal_id="sig-test-123",
            instrument="NIFTY",
            candle_timeframe="5M",
            setup_type="BREAKOUT",
            direction="BULLISH",
            status="CONFIRMED",
            trigger_level=24920.0,
            current_price=24915.0,
            entry_low=24920.0,
            entry_high=24935.0,
            stop_loss=24880.0,
            target_low=24980.0,
            target_high=25040.0,
            confidence=85.0,
            paper_order_id="ORD-TEST99",
            paper_fill_price=24920.0,
            paper_filled_qty=75,
            paper_status="FILLED",
            paper_side="BUY",
            created_at_utc=1772605200000,
        )
        rendered = format_signal_state(ev)
        assert "NIFTY 5M BREAKOUT CONFIRMED" in rendered
        assert "📅" in rendered
        assert "IST" in rendered
        assert "🎯 Entry: 24,920–24,935" in rendered
        assert "🛑 Stop Loss: 24,880" in rendered
        assert "🏁 Target: 24,980–25,040" in rendered
        assert "⚡ Paper Trade: FILLED (BUY 75 Qty @ ₹24,920)" in rendered
        assert "📋 Order ID: ORD-TEST99" in rendered

    def test_generate_signal_with_paper_execution(self, client):
        payload = {
            "instrument_id": "NIFTY",
            "candle_timeframe": "5M",
            "direction": "BULLISH",
            "status": "CONFIRMED",
            "trigger_level": 24940.0,
            "current_price": 24915.0,
            "confidence": 88.0,
            "execute_paper": True,
            "notify_telegram": False,
        }
        res = client.post("/api/v1/signals/generate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "signal" in data
        assert data["signal"]["instrument_id"] == "NIFTY"
        assert data["signal"]["direction"] == "BULLISH"
        assert "created_at_utc" in data["signal"]
        
        # Verify paper order execution
        assert "paper_order" in data
        po = data["paper_order"]
        assert po is not None
        assert po["status"] == "FILLED"
        assert po["side"] == "BUY"
        assert po["quantity"] == 75
        assert po["underlying"] == "NIFTY"

    def test_execute_signal_paper_endpoint(self, client):
        # 1. Create a signal first
        gen_res = client.post("/api/v1/signals/generate", json={
            "instrument_id": "BANKNIFTY",
            "candle_timeframe": "5M",
            "direction": "BEARISH",
            "status": "CONFIRMED",
            "trigger_level": 52100.0,
            "current_price": 52150.0,
            "execute_paper": False,
            "notify_telegram": False,
        })
        assert gen_res.status_code == 200
        sig_id = gen_res.json()["signal"]["signal_id"]

        # 2. Call 1-click execute paper endpoint
        exec_res = client.post(f"/api/v1/signals/{sig_id}/execute-paper", json={"quantity": 30})
        assert exec_res.status_code == 200
        exec_data = exec_res.json()
        assert exec_data["success"] is True
        assert exec_data["paper_order"]["side"] == "SELL"
        assert exec_data["paper_order"]["quantity"] == 30
        assert exec_data["paper_order"]["underlying"] == "BANKNIFTY"
