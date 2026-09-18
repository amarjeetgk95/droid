"""Golden regression tests for the Phase 2a paper-trading consolidation.

These pin the intended behavior of the signal->paper execution seam BEFORE and
AFTER the consolidation refactor:

1. One friction primitive: the engine's pre-trade estimate/guard and the paper
   service's fill both use ``paper_service.apply_friction`` (spread + slippage),
   so a published chain mark produces exactly one fill price on both sides.
2. Wallet invariant: an executed option entry locks ``fill_price * quantity``.
3. Close-once: a settled signal never places a second exit order nor re-books
   settlement; a second close is an explicit no-op.
4. Settlement gate: a non-FILLED exit order must NOT book settlement, must NOT
   close the registered Position, and must leave the paper position + FSM alone.
5. Position lifecycle: a successful full close closes/removes the registered
   Position and drops it from the portfolio Greeks ledger (idempotently).
6. Shard characterization (documented current behavior): signal trades carry no
   session/user_id, so they land in the anonymous shard of
   ``PaperTradingService``. Pinned as-is pending the multi-user product call.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.models.paper import VirtualOrder
from app.services.paper_service import (
    PaperTradingService,
    apply_friction,
    paper_service,
)
from app.signals.audit_ledger import signal_audit_ledger
from app.signals.execution_intent import intent_ledger
from app.signals.fill_reconciler import option_fill_reconciler
from app.signals.fsm import SignalInstance, signal_fsm
from app.signals.paper_engine import SignalPaperEngine
from app.signals.portfolio_greeks import portfolio_greeks_ledger
from app.signals.position import PositionState, position_registry
from app.signals.safety.decimal_types import normalize_price_to_tick
from tests.conftest import seed_chain_mark

CE_SYMBOL = "NSE:NIFTY26SEP24800CE"
TICK = "0.05"
ENTRY_MARK = 150.0
EXIT_MARK = 200.0


@pytest.fixture(autouse=True)
def _isolate_paper_state(mock_market_open, monkeypatch, tmp_path):
    """Deterministic, isolated market + paper + registry state per test."""
    import importlib

    from app.signals.safety.feed_health_monitor import feed_health_monitor

    # Keep the intent ledger's on-disk persistence out of the repo root.
    _intent_mod = importlib.import_module("app.signals.execution_intent")
    monkeypatch.setattr(_intent_mod, "_INTENT_LEDGER_FILE", tmp_path / "intent_ledger.json")

    # An offline test process has no broker feed, so the real monitor reports
    # DOWN and auto-activates the global kill switch (guard check 1). Pin a
    # healthy feed so these tests exercise the execution path instead of the
    # environment's broker connectivity.
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
    paper_service.reset_portfolio()
    paper_service._user_positions.clear()
    paper_service._user_orders.clear()
    position_registry.clear()
    portfolio_greeks_ledger.clear()
    option_fill_reconciler._records.clear()
    intent_ledger.clear()
    signal_fsm._signals.clear()
    signal_audit_ledger._trades.clear()
    yield
    paper_service.reset_portfolio()
    paper_service._user_positions.clear()
    paper_service._user_orders.clear()
    position_registry.clear()
    portfolio_greeks_ledger.clear()
    option_fill_reconciler._records.clear()
    intent_ledger.clear()
    signal_fsm._signals.clear()
    signal_audit_ledger._trades.clear()


def _make_signal(signal_id: str, quantity: int = 75) -> SignalInstance:
    sig = SignalInstance(
        signal_id=signal_id,
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24795"),
        entry_max=Decimal("24805"),
        trigger=Decimal("24800"),
        stop_loss=Decimal("24720"),
        target_1=Decimal("24920"),
        target_2=Decimal("25000"),
        risk_points=Decimal("80"),
        risk_reward_t1=1.5,
        risk_reward_t2=2.5,
        confidence=85.0,
        lots=max(1, quantity // 75),
        option_contract={
            "broker_symbol": CE_SYMBOL,
            "strike": 24800.0,
            "option_type": "CE",
            "lot_size": 75,
            "tick_size": TICK,
        },
        fsm_state="TRIGGERED",
    )
    signal_fsm.register(sig)
    return sig


async def _enter(engine: SignalPaperEngine, signal_id: str, quantity: int = 75):
    return await engine.execute_signal(signal_id, quantity_override=quantity)


def test_shared_friction_primitive_matches_service_fill_math():
    """The service's fill math is byte-identical to the shared primitive."""
    for price in (150.0, 0.05, 24800.0, 56816.69):
        for side in ("BUY", "SELL"):
            assert PaperTradingService._apply_friction(price, side) == apply_friction(price, side)


@pytest.mark.asyncio
async def test_entry_engine_fill_equals_service_fill_on_shared_friction(paper_fills_from_marks):
    """Same signal + same published chain mark => one shared fill number."""
    seed_chain_mark(CE_SYMBOL, ENTRY_MARK, underlying="NIFTY", strike=24800.0, option_type="CE")
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-GOLD-ENTRY-1")

    res = await _enter(engine, sig.signal_id)

    expected = apply_friction(ENTRY_MARK, "BUY")
    assert res.success is True
    assert res.fill_price == pytest.approx(expected)

    fills = [o for o in paper_service.get_orders() if o.status == "FILLED" and o.side == "BUY"]
    assert len(fills) == 1
    assert fills[0].fill_price == pytest.approx(expected)
    assert res.order_id == fills[0].order_id

    # The engine's pre-trade estimate carried into the payload is the SAME
    # 15 bps friction (tick-snapped for the guard), not the old 5 bps inline
    # `base_price * 1.0005` number the service never used.
    expected_estimate = float(normalize_price_to_tick(Decimal(str(expected)), TICK))
    assert sig.paper_order is not None
    assert sig.paper_order["price"] == pytest.approx(expected_estimate)
    assert sig.paper_order["price"] != pytest.approx(150.10)  # old 5 bps tick-snapped


@pytest.mark.asyncio
async def test_entry_wallet_invariant_used_margin_equals_fill_times_qty(paper_fills_from_marks):
    """After execute, locked margin == fill_price * quantity."""
    seed_chain_mark(CE_SYMBOL, ENTRY_MARK, underlying="NIFTY", strike=24800.0, option_type="CE")
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-GOLD-MARGIN-1")

    res = await _enter(engine, sig.signal_id, quantity=75)
    assert res.success is True

    pos = paper_service._positions[f"{CE_SYMBOL}_INTRADAY"]
    assert pos.is_open is True
    assert pos.quantity == 75
    assert pos.used_margin == pytest.approx(round(res.fill_price * 75, 2), abs=0.01)
    assert pos.used_margin == pytest.approx(round(pos.average_price * pos.quantity, 2), abs=0.01)


@pytest.mark.asyncio
async def test_close_once_single_exit_and_single_settlement(paper_fills_from_marks):
    """Two close calls => exactly one exit order and one settlement history row."""
    seed_chain_mark(CE_SYMBOL, ENTRY_MARK, underlying="NIFTY", strike=24800.0, option_type="CE")
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-GOLD-CLOSE-ONCE-1")
    assert (await _enter(engine, sig.signal_id)).success is True

    seed_chain_mark(CE_SYMBOL, EXIT_MARK, underlying="NIFTY", strike=24800.0, option_type="CE")
    rec1 = await engine.close_signal_position(
        sig.signal_id, exit_price=EXIT_MARK, reason="TARGET_2_HIT", allow_closed_market=True
    )
    assert rec1 is not None
    assert rec1.status == "WON"

    sells = [o for o in paper_service.get_orders() if o.side == "SELL"]
    assert len(sells) == 1 and sells[0].status == "FILLED"

    # Second close: settled row short-circuits — no second exit, no rewrite.
    rec2 = await engine.close_signal_position(
        sig.signal_id, exit_price=210.0, reason="TARGET_2_HIT", allow_closed_market=True
    )
    assert rec2 is not None
    assert getattr(rec2, "signal_id", None) == sig.signal_id

    assert len([o for o in paper_service.get_orders() if o.side == "SELL"]) == 1
    final = signal_audit_ledger.get(sig.signal_id)
    assert final.exit_price == pytest.approx(EXIT_MARK)
    won_events = [e for e in final.state_history if e.to_state == "WON"]
    assert len(won_events) == 1


@pytest.mark.asyncio
async def test_close_with_unfilled_exit_books_nothing(paper_fills_from_marks):
    """A non-FILLED exit must not settle the trade nor mark anything closed."""
    seed_chain_mark(CE_SYMBOL, ENTRY_MARK, underlying="NIFTY", strike=24800.0, option_type="CE")
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-GOLD-UNFILLED-1")
    assert (await _enter(engine, sig.signal_id)).success is True

    rejected = VirtualOrder(
        order_id="ORD-EXIT-REJECTED",
        timestamp="2026-01-01T00:00:00+00:00",
        symbol=CE_SYMBOL,
        underlying="NIFTY",
        side="SELL",
        order_type="MARKET",
        product="INTRADAY",
        quantity=75,
        price=EXIT_MARK,
        status="REJECTED",
        rejection_reason="MARKET_QUOTE_UNAVAILABLE: Live market quote unavailable to fill market order",
    )
    with patch.object(paper_service, "place_order", new=AsyncMock(return_value=rejected)):
        close_res = await engine.close_signal_position(
            sig.signal_id, exit_price=EXIT_MARK, reason="TARGET_2_HIT", allow_closed_market=True
        )

    # Explicit failure result, preserving the service rejection vocabulary.
    assert close_res is not None
    assert close_res.success is False
    assert close_res.status == "REJECTED"
    assert "MARKET_QUOTE_UNAVAILABLE" in close_res.message
    assert close_res.order_id == "ORD-EXIT-REJECTED"

    # No settlement booked, virtual position still open, FSM untouched.
    rec = signal_audit_ledger.get(sig.signal_id)
    assert rec.status == "EXECUTED"
    assert rec.exit_price is None
    assert signal_fsm.get(sig.signal_id).fsm_state == "CONFIRMED"
    assert paper_service._positions[f"{CE_SYMBOL}_INTRADAY"].is_open is True

    # Registry Position remains open (not marked CLOSED) and greeks kept.
    reg_pos = position_registry.get(sig.position_id)
    assert reg_pos is not None
    assert reg_pos.position_state != PositionState.CLOSED
    assert portfolio_greeks_ledger.get_summary().total_open_positions == 1


@pytest.mark.asyncio
async def test_successful_close_closes_registry_position_and_greeks(paper_fills_from_marks):
    """A filled full close transitions the registered Position out of OPEN."""
    seed_chain_mark(CE_SYMBOL, ENTRY_MARK, underlying="NIFTY", strike=24800.0, option_type="CE")
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-GOLD-REGISTRY-1")
    assert (await _enter(engine, sig.signal_id)).success is True

    reg_pos = position_registry.get(sig.position_id)
    assert reg_pos is not None
    assert reg_pos.position_state == PositionState.OPEN
    assert portfolio_greeks_ledger.get_summary().total_open_positions == 1

    seed_chain_mark(CE_SYMBOL, EXIT_MARK, underlying="NIFTY", strike=24800.0, option_type="CE")
    rec = await engine.close_signal_position(
        sig.signal_id, exit_price=EXIT_MARK, reason="TARGET_2_HIT", allow_closed_market=True
    )
    assert rec is not None and rec.status == "WON"

    assert reg_pos.position_state == PositionState.CLOSED
    assert reg_pos.closed_at_utc is not None
    assert portfolio_greeks_ledger.get_summary().total_open_positions == 0

    # Idempotent: a second close neither raises nor resurrects greeks exposure.
    rec2 = await engine.close_signal_position(
        sig.signal_id, exit_price=EXIT_MARK, reason="TARGET_2_HIT", allow_closed_market=True
    )
    assert rec2 is not None
    assert reg_pos.position_state == PositionState.CLOSED
    assert portfolio_greeks_ledger.get_summary().total_open_positions == 0


@pytest.mark.asyncio
async def test_signal_fill_lands_in_anon_shard(paper_fills_from_marks):
    """Characterization: signal fills use the anonymous shard today.

    The engine calls ``paper_service.place_order`` without session/user_id, so
    the position/order land in the legacy anonymous shard (``_positions`` /
    ``_orders`` aliases), not in a per-user shard. Pinned as current behavior
    pending the multi-user signal-sharding product decision.
    """
    seed_chain_mark(CE_SYMBOL, ENTRY_MARK, underlying="NIFTY", strike=24800.0, option_type="CE")
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-GOLD-SHARD-1")
    assert (await _enter(engine, sig.signal_id)).success is True

    assert f"{CE_SYMBOL}_INTRADAY" in paper_service._positions
    assert any(o.symbol == CE_SYMBOL and o.status == "FILLED" for o in paper_service._orders)
    assert paper_service._user_positions == {}
    assert paper_service._user_orders == {}
