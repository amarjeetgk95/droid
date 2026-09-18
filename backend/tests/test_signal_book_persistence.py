"""Signal paper book persistence + single-shard control (approved decisions A-C).

Pins:
  A. `/api/v1/signals/paper-wallet` controls the ANONYMOUS signal book (the one
     shard the automated signal engine trades), never the authenticated user's
     per-user shard.
  B. Anon signal fills persist to paper_* tables under the reserved system user
     while memory stays on the anon aliases (`_positions` / `_orders`).
  C. `fsm.sweep_expired` branch 2 leaves a prior-day CONFIRMED/TARGET_1_HIT
     signal retryable while a paper leg is still open, so a failed EOD close
     cannot strand a terminal FSM with a ghost position.

Runtime artifacts (intent ledger, signals state) are isolated to tmp_path via
this module and the shared conftest.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.security import SIGNAL_BOOK_USER_ID
from app.models.database import PaperOrderDB, PaperPositionDB
from app.models.paper import OrderPayload, VirtualPosition
from app.repositories.paper_repository import PaperTradingRepository
from app.services.paper_service import ANON_KEY, paper_service
from app.signals.fsm import SignalInstance, signal_fsm

SYMBOL = "NSE:NIFTY26SEP24800CE"


class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, obj):
        return obj


class _FakeSessionCtx:
    """Mirrors async_sessionmaker's callable returning an async CM."""

    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _install_fake_factory(monkeypatch, session) -> None:
    def factory():
        return _FakeSessionCtx(session)

    monkeypatch.setattr("app.core.database.get_async_session_factory", lambda: factory)


@pytest.fixture(autouse=True)
def _isolate_signal_book_state(monkeypatch, tmp_path):
    """Reset/restore the anon signal book and keep runtime artifacts in tmp."""
    import importlib

    _intent_mod = importlib.import_module("app.signals.execution_intent")
    monkeypatch.setattr(_intent_mod, "_INTENT_LEDGER_FILE", tmp_path / "intent_ledger.json")

    saved = {
        "positions": dict(paper_service._positions),
        "orders": list(paper_service._orders),
        "capital": paper_service._initial_capital,
        "realized": paper_service._realized_pnl,
        "idem": dict(paper_service._idempotency.get(ANON_KEY, {})),
        "user_positions": {k: dict(v) for k, v in paper_service._user_positions.items()},
        "user_orders": {k: list(v) for k, v in paper_service._user_orders.items()},
        "capitals": dict(paper_service._capitals),
        "realized_by_user": dict(paper_service._realized_by_user),
    }
    paper_service._positions.clear()
    paper_service._orders.clear()
    paper_service._initial_capital = 1000000.0
    paper_service._realized_pnl = 0.0
    paper_service._idempotency.pop(ANON_KEY, None)
    paper_service._user_positions.clear()
    paper_service._user_orders.clear()
    paper_service._capitals.clear()
    paper_service._realized_by_user.clear()
    paper_service._last_mtm_persist.clear()
    try:
        yield
    finally:
        paper_service._positions.clear()
        paper_service._positions.update(saved["positions"])
        paper_service._orders.clear()
        paper_service._orders.extend(saved["orders"])
        paper_service._initial_capital = saved["capital"]
        paper_service._realized_pnl = saved["realized"]
        paper_service._idempotency.pop(ANON_KEY, None)
        if saved["idem"]:
            paper_service._idempotency[ANON_KEY] = saved["idem"]
        paper_service._user_positions.clear()
        paper_service._user_positions.update(saved["user_positions"])
        paper_service._user_orders.clear()
        paper_service._user_orders.update(saved["user_orders"])
        paper_service._capitals.clear()
        paper_service._capitals.update(saved["capitals"])
        paper_service._realized_by_user.clear()
        paper_service._realized_by_user.update(saved["realized_by_user"])
        paper_service._last_mtm_persist.clear()


# ── A. endpoint scope ─────────────────────────────────────────────────────


def test_signals_paper_wallet_controls_anon_book(client: TestClient):
    res = client.post("/api/v1/signals/paper-wallet", json={"capital": 500000.0})
    assert res.status_code == 200
    assert res.json()["capital"] == 500000.0

    # The ANON shard moved; per-user shards did not.
    assert paper_service._initial_capital == 500000.0
    assert paper_service._capitals == {}
    assert paper_service._user_positions == {}
    assert paper_service._user_orders == {}

    summary = asyncio.run(paper_service.get_portfolio_summary())
    assert summary.virtual_capital == 500000.0


# ── B. persistence boundary ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anon_fill_persists_under_system_user(monkeypatch, mock_market_open, paper_fills_from_marks):
    from tests.conftest import seed_chain_mark

    seed_chain_mark(SYMBOL, 150.0, underlying="NIFTY", strike=24800.0, option_type="CE")

    calls: list[tuple[str, object]] = []

    async def fake_save_order(session, user_id, order):
        calls.append(("save_order", user_id))
        return None

    async def fake_upsert_position(session, user_id, position):
        calls.append(("upsert_position", user_id))
        return None

    async def fake_update_portfolio(session, user_id, **kwargs):
        calls.append(("update_portfolio", user_id))
        return None

    monkeypatch.setattr(PaperTradingRepository, "save_order", staticmethod(fake_save_order))
    monkeypatch.setattr(PaperTradingRepository, "upsert_position", staticmethod(fake_upsert_position))
    monkeypatch.setattr(PaperTradingRepository, "update_portfolio", staticmethod(fake_update_portfolio))
    _install_fake_factory(monkeypatch, _FakeSession())

    order = await paper_service.place_order(
        OrderPayload(
            symbol=SYMBOL, underlying="NIFTY", side="BUY", order_type="MARKET",
            product="INTRADAY", quantity=75, price=150.0,
        )
    )

    assert order.status == "FILLED"
    assert [c[0] for c in calls] == ["save_order", "upsert_position", "update_portfolio"]
    assert all(c[1] == SIGNAL_BOOK_USER_ID for c in calls)

    # Memory stays on the anon aliases; per-user shards untouched.
    assert f"{SYMBOL}_INTRADAY" in paper_service._positions
    assert paper_service._user_positions == {}
    assert paper_service._user_orders == {}


# ── B. hydration ──────────────────────────────────────────────────────────


def _position_row(position_id: str) -> PaperPositionDB:
    return PaperPositionDB(
        position_id=position_id,
        user_id=SIGNAL_BOOK_USER_ID,
        symbol=SYMBOL,
        underlying="NIFTY",
        instrument_type="OPTION_BUY",
        side="BUY",
        product="INTRADAY",
        quantity=75,
        average_price=150.0,
        ltp=155.0,
        unrealized_pnl=375.0,
        realized_pnl=0.0,
        used_margin=11250.0,
        is_open=True,
    )


def _order_row(order_id: str) -> PaperOrderDB:
    return PaperOrderDB(
        order_id=order_id,
        user_id=SIGNAL_BOOK_USER_ID,
        symbol=SYMBOL,
        underlying="NIFTY",
        side="BUY",
        order_type="MARKET",
        product="INTRADAY",
        quantity=75,
        price=150.0,
        status="FILLED",
        fill_price=150.11,
        timestamp=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_hydrate_anon_loads_system_user_rows(monkeypatch):
    async def fake_get_positions(session, user_id):
        assert user_id == SIGNAL_BOOK_USER_ID
        return [_position_row(f"{SYMBOL}_INTRADAY")]

    async def fake_get_or_create_portfolio(session, user_id):
        assert user_id == SIGNAL_BOOK_USER_ID
        return SimpleNamespace(realized_pnl=123.0, virtual_capital=500000.0)

    async def fake_get_orders(session, user_id, limit=50, offset=0):
        assert user_id == SIGNAL_BOOK_USER_ID
        return [_order_row("ORD-SB-1")]

    monkeypatch.setattr(PaperTradingRepository, "get_positions", staticmethod(fake_get_positions))
    monkeypatch.setattr(PaperTradingRepository, "get_or_create_portfolio", staticmethod(fake_get_or_create_portfolio))
    monkeypatch.setattr(PaperTradingRepository, "get_orders", staticmethod(fake_get_orders))
    _install_fake_factory(monkeypatch, _FakeSession())

    loaded = await paper_service.hydrate_anon()

    assert loaded == 1
    assert paper_service._positions[f"{SYMBOL}_INTRADAY"].quantity == 75
    assert paper_service._orders and paper_service._orders[0].order_id == "ORD-SB-1"
    assert paper_service._initial_capital == 500000.0
    assert paper_service._realized_pnl == 123.0
    assert paper_service._user_positions == {}


@pytest.mark.asyncio
async def test_hydrate_anon_never_overwrites_live_shard(monkeypatch):
    paper_service._positions["LIVE_INTRADAY"] = VirtualPosition(
        position_id="LIVE_INTRADAY",
        symbol=SYMBOL,
        underlying="NIFTY",
        instrument_type="OPTION_BUY",
        side="BUY",
        product="INTRADAY",
        quantity=75,
        average_price=150.0,
        ltp=150.0,
        unrealized_pnl=0.0,
    )

    async def _boom(*args, **kwargs):
        raise AssertionError("repo must not be touched when the shard is live")

    monkeypatch.setattr(PaperTradingRepository, "get_positions", staticmethod(_boom))
    _install_fake_factory(monkeypatch, _FakeSession())

    assert await paper_service.hydrate_anon() == 0
    assert list(paper_service._positions) == ["LIVE_INTRADAY"]


@pytest.mark.asyncio
async def test_hydrate_anon_without_db_is_a_noop():
    # conftest pins app.core.database.get_async_session_factory to None.
    assert await paper_service.hydrate_anon() == 0


# ── C. fsm sweep retryability ─────────────────────────────────────────────


def _prior_day_signal(signal_id: str, *, with_paper_order: bool) -> SignalInstance:
    now_ms = int(time.time() * 1000)
    sig = SignalInstance(
        signal_id=signal_id,
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800.0"),
        entry_min=Decimal("24795.0"),
        entry_max=Decimal("24805.0"),
        trigger=Decimal("24800.0"),
        stop_loss=Decimal("24720.0"),
        target_1=Decimal("24920.0"),
        target_2=Decimal("25000.0"),
        risk_points=Decimal("80.0"),
        risk_reward_t1=1.5,
        risk_reward_t2=2.5,
        confidence=85.0,
        fsm_state="CONFIRMED",
        actual_fill_price=Decimal("150.0"),
        entry_price=Decimal("150.0"),
        intended_qty=Decimal("75"),
        remaining_qty=Decimal("75"),
        created_at_utc=now_ms - int(2 * 86400 * 1000),
        option_contract={
            "broker_symbol": SYMBOL, "strike": 24800.0,
            "option_type": "CE", "lot_size": 75,
        },
    )
    if with_paper_order:
        sig.paper_order = {"order_id": "ORD-FSM-1", "quantity": 75, "status": "FILLED", "side": "BUY"}
    return sig


def test_prior_day_confirmed_with_open_paper_leg_stays_retryable():
    sig = _prior_day_signal("SIG-FSM-OPEN-1", with_paper_order=True)
    signal_fsm.register(sig)

    signal_fsm.sweep_expired()

    updated = signal_fsm.get(sig.signal_id)
    assert updated.fsm_state == "CONFIRMED"
    assert all(h.to_state != "CLOSED" for h in updated.state_history)


def test_prior_day_confirmed_without_paper_leg_closes():
    sig = _prior_day_signal("SIG-FSM-OPEN-2", with_paper_order=False)
    signal_fsm.register(sig)

    signal_fsm.sweep_expired()

    updated = signal_fsm.get(sig.signal_id)
    assert updated.fsm_state == "CLOSED"
    assert any(
        h.to_state == "CLOSED" and h.reason_code == "EOD_SESSION_SQUARE_OFF"
        for h in updated.state_history
    )
