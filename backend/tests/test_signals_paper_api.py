import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.institutional.telegram_notifications import SignalEvent
from app.institutional.telegram_templates import format_signal_state, _format_ist_timestamp
from app.services.paper_service import paper_service
from tests.conftest import seed_chain_mark


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_paper(mock_market_open, monkeypatch):
    paper_service.reset_portfolio()
    # A test process has no broker feed, so the real monitor reports DOWN and the
    # execution guard rejects with check=10_FEED_HEALTH — a machine-dependent
    # failure. Pin a healthy feed so these tests exercise the paper-execution
    # path they are actually about (same pattern as
    # tests/test_paper_sizing_idempotency.py).
    from app.signals.safety.feed_health_monitor import feed_health_monitor

    monkeypatch.setattr(
        feed_health_monitor,
        "get_telemetry",
        lambda *a, **k: {
            "status": "LIVE",
            "is_healthy_for_trading": True,
            "market_session": {"is_open": True, "reason": "MARKET_OPEN"},
            "spot_feed": {"tick_age_seconds": 0.0},
        },
    )


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

    def test_generate_signal_with_paper_execution(self, client, mock_market_feed, paper_fills_from_marks):
        # Fail-closed policy: a fill requires a broker quote for the exact
        # contract, so publish the one this setup resolves to before generating.
        from app.signals.contract_resolver import resolve_option_contract

        _contract = resolve_option_contract("NIFTY", 24915.0, "CE", strike_offset=0)
        seed_chain_mark(
            _contract.broker_symbol, 150.0,
            underlying="NIFTY", strike=float(_contract.strike or 0), option_type="CE",
        )
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
            "allow_closed_market": True,
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

    def test_execute_signal_paper_endpoint(self, client, mock_market_feed, paper_fills_from_marks):
        # 1. Create a signal first
        gen_res = client.post("/api/v1/signals/generate", json={
            "instrument_id": "BANKNIFTY",
            "candle_timeframe": "5M",
            "direction": "BEARISH",
            "status": "CONFIRMED",
            # PUT trigger must sit below spot and clear the ATR-based minimum
            # gap gate (former 57750 vs 57800 was only 50pts -> TRIGGER_TOO_CLOSE).
            "trigger_level": 57700.0,
            "current_price": 57800.0,
            "execute_paper": False,
            "notify_telegram": False,
            "allow_closed_market": True,
        })
        assert gen_res.status_code == 200
        gen_signal = gen_res.json()["signal"]
        sig_id = gen_signal["signal_id"]

        # Fail-closed policy: execution needs a real broker quote for the
        # resolved contract. Publish one before the 1-click execute.
        _opt = gen_signal["option_contract"]
        seed_chain_mark(
            _opt["broker_symbol"], 250.0,
            underlying="BANKNIFTY", strike=float(_opt.get("strike") or 0), option_type="PE",
        )

        # 2. Call 1-click execute paper endpoint
        exec_res = client.post(f"/api/v1/signals/{sig_id}/execute-paper", json={"quantity": 30})
        assert exec_res.status_code == 200
        exec_data = exec_res.json()
        assert exec_data["success"] is True
        # Long options are ALWAYS bought — the engine action for a PUT is BUY.
        assert exec_data["side"] == "BUY_PE"
        assert exec_data["paper_order"]["quantity"] == 30
        assert exec_data["paper_order"]["underlying"] == "BANKNIFTY"

        # The execute response's paper_order block is a synthesized display view
        # (api/signals.py derives its side from direction, LONG_PUT -> "SELL").
        # The authoritative filled order persisted on the signal is what proves
        # a PUT paper order is a BUY, never a SELL.
        paper_order = client.get(f"/api/v1/signals/{sig_id}").json()["paper_order"]
        assert paper_order["side"] == "BUY"
        assert paper_order["quantity"] == 30
        assert paper_order["underlying"] == "BANKNIFTY"
