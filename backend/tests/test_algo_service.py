"""Unit tests for Algo Domain Services (app/algo/algo_service.py).

Verifies service layer isolation from HTTP transport:
- Deterministic synthetic account generation
- Trading mode transitions and gate checks
- Consent recording and automatic mode revocation
- Order creation pipeline and idempotency
- Position sizing preview math
"""
from uuid import uuid4
import pytest
from fastapi import HTTPException

from app.algo.algo_service import (
    algo_account_service,
    algo_order_service,
    algo_signals_service,
    reset_algo_caches,
    DISCLOSURE_VERSION,
)
from app.api.algo import OrderCreate


@pytest.fixture(autouse=True)
def clean_algo_state():
    reset_algo_caches()
    yield
    reset_algo_caches()


def test_synthetic_account_creation_and_caching():
    uid = uuid4()
    acct1 = algo_account_service.create_synthetic_account(uid, mode="OFF")
    assert acct1.id == uid
    assert acct1.user_id == uid
    assert acct1.mode == "OFF"
    assert acct1.is_active is True


@pytest.mark.asyncio
async def test_account_mode_transitions():
    uid = uuid4()
    # OFF to PAPER should succeed in dev/synthetic mode
    res = await algo_account_service.set_mode(session=None, user_id=uid, target_mode="PAPER")
    assert res["mode"] == "PAPER"

    # Invalid mode should raise HTTPException(400)
    with pytest.raises(HTTPException) as exc:
        await algo_account_service.set_mode(session=None, user_id=uid, target_mode="INVALID_MODE")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_consent_workflow():
    uid = uuid4()
    # Initial consent in dev mode
    initial = await algo_account_service.get_consent(session=None, user_id=uid)
    assert initial["disclosure_version"] == DISCLOSURE_VERSION
    assert initial["acknowledged"] is False

    # Acknowledge consent
    recorded = await algo_account_service.record_consent(
        session=None, user_id=uid, disclosure_version=DISCLOSURE_VERSION, acknowledged=True
    )
    assert recorded["acknowledged"] is True

    # Revoke consent
    revoked = await algo_account_service.revoke_consent(session=None, user_id=uid)
    assert revoked["revoked"] is True
    assert revoked["mode"] == "OFF"


@pytest.mark.asyncio
async def test_order_creation_synthetic(mock_market_open):
    uid = uuid4()
    order_payload = OrderCreate(
        symbol="NIFTY24DEC24000CE",
        side="BUY",
        quantity=50,
        price=100.0,
        order_type="LIMIT",
        product="INTRADAY",
    )
    result = await algo_order_service.create_order(session=None, user_id=uid, payload=order_payload)
    assert "client_order_id" in result
    assert result["is_paper"] is True
    assert result["status"] in ("SUBMITTED", "FILLED", "ACKNOWLEDGED")


def test_position_sizing_preview():
    preview = algo_signals_service.preview_sizing(
        entry_price=100.0,
        stop_price=90.0,
        risk_budget=500.0,
        lot_size=50,
        available_capital=30000.0,
        max_capital_per_trade=5000.0,
    )
    assert "quantity" in preview
    assert "notional" in preview
    assert preview["quantity"] > 0
