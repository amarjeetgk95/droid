from datetime import datetime
from unittest.mock import patch
import zoneinfo
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.calendar_service import MarketSessionPermission, calendar_service


@pytest.fixture
def client():
    """FastAPI test client."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_market_open():
    """Fixture to mock calendar_service.can_trade_now() as MARKET_OPEN for tests requiring open market."""
    ist = zoneinfo.ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(ist).replace(hour=11, minute=0, second=0)
    mock_perm = MarketSessionPermission(
        allowed=True,
        reason="MARKET_OPEN",
        exchange="NSE",
        session="REGULAR",
        timestamp_ist=now_ist,
        market_open=now_ist.replace(hour=9, minute=15),
        market_close=now_ist.replace(hour=15, minute=30),
    )
    with patch.object(calendar_service, "can_trade_now", return_value=mock_perm):
        yield mock_perm


@pytest.fixture(autouse=True)
def isolate_signals_state(tmp_path, monkeypatch):
    """Ensure test runs write to an isolated temporary state file and do not pollute production state."""
    test_state_file = tmp_path / "test_signals_state.json"
    monkeypatch.setattr("app.signals.signals_persistence.SIGNALS_STATE_FILE", test_state_file)
    from app.signals.fsm import signal_fsm
    from app.signals.audit_ledger import signal_audit_ledger
    with signal_fsm._lock:
        orig_signals = dict(signal_fsm._signals)
    with signal_audit_ledger._lock:
        orig_trades = dict(signal_audit_ledger._trades)
    yield
    with signal_fsm._lock:
        signal_fsm._signals.clear()
        signal_fsm._signals.update(orig_signals)
    with signal_audit_ledger._lock:
        signal_audit_ledger._trades.clear()
        signal_audit_ledger._trades.update(orig_trades)