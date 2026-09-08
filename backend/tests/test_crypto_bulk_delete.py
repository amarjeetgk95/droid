"""Crypto ledger bulk-delete + datewise clear coverage."""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.crypto_scalp.models_execution import (
    CryptoScalpExecutionRecord,
    CryptoScalpPositionState,
    CryptoScalpExitEventType,
    SignalDirection,
)
from app.crypto_scalp.persistence import save_executions_local, restore_executions_local


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolate_crypto_state(tmp_path, monkeypatch):
    execs_file = tmp_path / "test_crypto_scalp_executions_state.json"
    events_file = tmp_path / "test_crypto_scalp_events_state.json"
    monkeypatch.setattr("app.crypto_scalp.persistence.CRYPTO_SCALP_EXECUTIONS_FILE", execs_file)
    monkeypatch.setattr("app.crypto_scalp.persistence.CRYPTO_SCALP_EVENTS_FILE", events_file)
    yield


def _make_record(trade_id: str, symbol: str, state: CryptoScalpPositionState, net_pnl_usd: float, created_at_utc: int | None = None) -> CryptoScalpExecutionRecord:
    return CryptoScalpExecutionRecord(
        trade_id=trade_id,
        signal_id=f"s_{trade_id}",
        symbol=symbol,
        asset="BTC" if "BTC" in symbol else "ETH",
        direction=SignalDirection.LONG,
        strategy="VWAP_BOUNCE",
        strategy_name="VWAP Rejection Scalp",
        position_state=state,
        signal_price=90_000.0,
        entry_fill_price=90_000.0,
        initial_stop_price=89_500.0,
        current_stop_price=90_000.0,
        target_1_price=90_750.0,
        target_2_price=91_250.0,
        exit_price=91_250.0 if state == CryptoScalpPositionState.CLOSED else None,
        exit_reason=CryptoScalpExitEventType.T2_HIT if state == CryptoScalpPositionState.CLOSED else None,
        quantity_initial=0.2,
        quantity_remaining=0.0,
        initial_risk_usd=100.0,
        net_pnl_usd=net_pnl_usd,
        r_multiple=2.0 if net_pnl_usd > 0 else -1.0,
        duration_seconds=600,
        created_at_utc=created_at_utc or int(time.time() * 1000),
    )


class TestCryptoBulkDelete:
    def test_bulk_delete_needs_selector(self, client):
        r = client.post("/api/v1/crypto/scalp-signals/ledger/bulk", json={})
        assert r.status_code == 400
        assert "Nothing selected" in r.json()["detail"]

    def test_bulk_delete_all_needs_confirm(self, client):
        r = client.post("/api/v1/crypto/scalp-signals/ledger/bulk", json={"delete_all": True})
        assert r.status_code == 400
        assert "confirm_all" in r.json()["detail"]

    def test_bulk_delete_by_ids(self, client):
        recs = [_make_record("tid_1", "BTCUSDT", CryptoScalpPositionState.CLOSED, 150.0), _make_record("tid_2", "ETHUSDT", CryptoScalpPositionState.CLOSED, -80.0)]
        save_executions_local(recs)
        try:
            r = client.post("/api/v1/crypto/scalp-signals/ledger/bulk", json={"trade_ids": ["tid_1", "tid_2"]})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["status"] == "success"
            assert body["deleted_count"] == 2
            assert set(body["trade_ids"]) == {"tid_1", "tid_2"}
            remaining = restore_executions_local()
            assert all(r.trade_id not in ("tid_1", "tid_2") for r in remaining)
        finally:
            save_executions_local([])

    def test_bulk_delete_datewise(self, client):
        old_ms = int(time.time() * 1000) - 10 * 24 * 3600 * 1000
        fresh_ms = int(time.time() * 1000)
        recs = [
            _make_record("tid_old", "BTCUSDT", CryptoScalpPositionState.CLOSED, 100.0, created_at_utc=old_ms),
            _make_record("tid_fresh", "BTCUSDT", CryptoScalpPositionState.CLOSED, 50.0, created_at_utc=fresh_ms),
        ]
        save_executions_local(recs)
        try:
            cutoff = fresh_ms - 24 * 3600 * 1000
            r = client.post("/api/v1/crypto/scalp-signals/ledger/bulk", json={"before_ms": cutoff})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["deleted_count"] == 1
            assert body["trade_ids"] == ["tid_old"]
            remaining = restore_executions_local()
            assert any(r.trade_id == "tid_fresh" for r in remaining)
            assert all(r.trade_id != "tid_old" for r in remaining)
        finally:
            save_executions_local([])

    def test_bulk_delete_by_symbol_filter(self, client):
        recs = [
            _make_record("tid_btc", "BTCUSDT", CryptoScalpPositionState.CLOSED, 100.0),
            _make_record("tid_eth", "ETHUSDT", CryptoScalpPositionState.CLOSED, 50.0),
        ]
        save_executions_local(recs)
        try:
            r = client.post("/api/v1/crypto/scalp-signals/ledger/bulk", json={"symbol": "BTCUSDT"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["deleted_count"] == 1
            assert body["trade_ids"] == ["tid_btc"]
            remaining = restore_executions_local()
            assert any(r.trade_id == "tid_eth" for r in remaining)
        finally:
            save_executions_local([])

    def test_bulk_delete_by_outcome_profit(self, client):
        recs = [
            _make_record("tid_win", "BTCUSDT", CryptoScalpPositionState.CLOSED, 200.0),
            _make_record("tid_loss", "BTCUSDT", CryptoScalpPositionState.CLOSED, -100.0),
            _make_record("tid_active", "BTCUSDT", CryptoScalpPositionState.ACTIVE, 0.0),
        ]
        save_executions_local(recs)
        try:
            r = client.post("/api/v1/crypto/scalp-signals/ledger/bulk", json={"outcome": "PROFIT"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["deleted_count"] == 1
            assert body["trade_ids"] == ["tid_win"]
        finally:
            save_executions_local([])

    def test_bulk_delete_by_outcome_loss(self, client):
        recs = [
            _make_record("tid_win", "BTCUSDT", CryptoScalpPositionState.CLOSED, 200.0),
            _make_record("tid_loss", "BTCUSDT", CryptoScalpPositionState.CLOSED, -100.0),
        ]
        save_executions_local(recs)
        try:
            r = client.post("/api/v1/crypto/scalp-signals/ledger/bulk", json={"outcome": "LOSS"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["deleted_count"] == 1
            assert body["trade_ids"] == ["tid_loss"]
        finally:
            save_executions_local([])

    def test_bulk_delete_cap_500(self, client):
        recs = [_make_record(f"tid_{i}", "BTCUSDT", CryptoScalpPositionState.CLOSED, 10.0) for i in range(10)]
        save_executions_local(recs)
        try:
            r = client.post("/api/v1/crypto/scalp-signals/ledger/bulk", json={"symbol": "BTCUSDT"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["deleted_count"] == 10
            assert len(body["trade_ids"]) == 10
            remaining = restore_executions_local()
            assert len(remaining) == 0
        finally:
            save_executions_local([])
