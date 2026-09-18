"""Remaining approved paper-trading fixes (post-consolidation).

Pins the three fixes:

1. RECONCILER LOT DEFAULTS: entry/T1/final reconciliation resolves the lot size
   from the signal's own ``option_contract`` instead of the legacy 75/30/10
   underlying defaults; the defaults survive only as a last-resort fallback.
   Staged-exit quantities and synthetic-record P&L are pinned for a
   non-default (65) NIFTY lot contract.
2. PENDING-ORDER LIFECYCLE:
   a. resting PENDING orders are swept and filled while the market is open via
      the worker's throttled pending sweep (and stay PENDING until price
      crosses), under the service's per-user lock;
   b. the signal engine cancels a PENDING service order instead of leaving a
      ghost resting order behind its own failure result.
3. OFF-DOMAIN POST-FILL ROLLBACK: a pre-fill domain guard rejects an
   index-scale chain mark before any service order is placed; when a bad fill
   still reaches the book, the engine squares the service position off so no
   open position and no fabricated P&L survive (round trip nets ~friction).
"""
from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.models.paper import OrderPayload
from app.quant.costs import calculate_option_costs
from app.services.paper_service import (
    PaperTradingService,
    apply_friction,
    paper_service,
)
from app.signals.audit_ledger import signal_audit_ledger
from app.signals.execution_intent import IntentState, intent_ledger
from app.signals.fill_reconciler import option_fill_reconciler
from app.signals.fsm import SignalInstance, signal_fsm
from app.signals.paper_engine import SignalPaperEngine
from app.signals.position import position_registry
from app.signals.worker import AutomatedSignalWorker
from tests.conftest import seed_chain_mark

SYMBOL = "NSE:NIFTY26SEP24800CE"
TICK = "0.05"
#: A deliberately non-default NIFTY lot (contract truth beats 75/30/10).
CONTRACT_LOT = 65


def _leg_net(entry: float, exit_price: float, qty: int) -> float:
    buy_turnover = round(entry * qty, 2)
    sell_turnover = round(exit_price * qty, 2)
    costs = calculate_option_costs(buy_turnover=buy_turnover, sell_turnover=sell_turnover, num_orders=2)
    return round(round(sell_turnover - buy_turnover, 2) - costs.total_cost, 2)


@pytest.fixture(autouse=True)
def _isolate_paper_remaining_fixes(mock_market_open, monkeypatch, tmp_path):
    """Deterministic market + isolated paper/registry/intent state per test."""
    import importlib

    from app.signals.safety.feed_health_monitor import feed_health_monitor

    _intent_mod = importlib.import_module("app.signals.execution_intent")
    monkeypatch.setattr(_intent_mod, "_INTENT_LEDGER_FILE", tmp_path / "intent_ledger.json")

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

    paper_service.reset_portfolio(capital=1_000_000.0)
    paper_service._user_positions.clear()
    paper_service._user_orders.clear()
    position_registry.clear()
    option_fill_reconciler._records.clear()
    intent_ledger.clear()
    signal_fsm._signals.clear()
    signal_audit_ledger._trades.clear()
    yield
    paper_service.reset_portfolio(capital=1_000_000.0)
    paper_service._user_positions.clear()
    paper_service._user_orders.clear()
    position_registry.clear()
    option_fill_reconciler._records.clear()
    intent_ledger.clear()
    signal_fsm._signals.clear()
    signal_audit_ledger._trades.clear()


def _make_signal(
    signal_id: str,
    *,
    quantity: int = 130,
    lot_size: int = CONTRACT_LOT,
    actual_fill: float | None = None,
) -> SignalInstance:
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
        lots=max(1, quantity // lot_size),
        option_contract={
            "broker_symbol": SYMBOL,
            "strike": 24800.0,
            "option_type": "CE",
            "lot_size": lot_size,
            "tick_size": TICK,
        },
        fsm_state="TRIGGERED",
        actual_fill_price=Decimal(str(actual_fill)) if actual_fill is not None else None,
    )
    signal_fsm.register(sig)
    return sig


def _seed_mark(price: float = 150.0) -> None:
    seed_chain_mark(SYMBOL, price, underlying="NIFTY", strike=24800.0, option_type="CE")


def _patch_service_price(monkeypatch, price: float | None) -> None:
    """Pin the paper service's live quote resolver to one price."""
    async def _resolve(self, symbol, underlying=None):
        return price

    monkeypatch.setattr(PaperTradingService, "_resolve_live_for_symbol", _resolve)
    monkeypatch.setattr(
        paper_service,
        "_resolve_live_for_symbol",
        _resolve.__get__(paper_service, PaperTradingService),
    )


def _patch_service_ltp(monkeypatch, price: float | None) -> None:
    """Pin the paper service's position-LTP resolver (square-off pricing)."""
    async def _ltp(self, pos):
        return price

    monkeypatch.setattr(PaperTradingService, "_resolve_live_ltp", _ltp)
    monkeypatch.setattr(
        paper_service,
        "_resolve_live_ltp",
        _ltp.__get__(paper_service, PaperTradingService),
    )


# ── 1. RECONCILER LOT DEFAULTS ──────────────────────────────────────────


def test_reconcile_entry_uses_contract_lot_size_for_staged_exit():
    """Two-lot 65 contract: T1 = one 65 lot, not the legacy 75 default."""
    sig = _make_signal("SIG-LOT-ENTRY", quantity=130)
    rec = option_fill_reconciler.reconcile_entry(sig, 100.0, 130)

    assert rec is not None
    assert rec.lot_size == CONTRACT_LOT
    assert rec.t1_qty == CONTRACT_LOT
    assert rec.t1_qty != 75
    # Entry holds the full quantity; the 65-lot T1 split is what gets staged.
    assert rec.remaining_qty == 130
    assert rec.t1_qty < rec.remaining_qty


def test_reconcile_t1_exit_synthetic_record_uses_contract_lot_size():
    """No prior entry: the synthetic entry/T1 books the contract lot, not 75."""
    sig = _make_signal("SIG-LOT-T1", actual_fill=100.0)
    rec = option_fill_reconciler.reconcile_t1_exit(sig, 130.0, int(time.time() * 1000))

    assert rec.lot_size == CONTRACT_LOT
    assert rec.intended_qty == CONTRACT_LOT  # 1 contract lot, not the legacy 75
    assert rec.remaining_qty == 0
    assert rec.net_realized_pnl_inr == pytest.approx(_leg_net(100.0, 130.0, CONTRACT_LOT))


def test_reconcile_final_exit_synthetic_record_uses_contract_lot_size():
    """Synthetic final exit: quantity and P&L follow the contract's 65 lot."""
    sig = _make_signal("SIG-LOT-FINAL", actual_fill=100.0)
    rec = option_fill_reconciler.reconcile_final_exit(sig, 120.0, "TARGET_2_HIT")

    expected = _leg_net(100.0, 120.0, CONTRACT_LOT)
    assert rec.lot_size == CONTRACT_LOT
    assert rec.intended_qty == CONTRACT_LOT
    assert rec.is_fully_closed is True
    assert rec.net_realized_pnl_inr == pytest.approx(expected)
    # The legacy 75 default would have booked a different (wrong) quantity.
    assert rec.net_realized_pnl_inr != pytest.approx(_leg_net(100.0, 120.0, 75), abs=0.5)


def test_reconcile_entry_explicit_lot_size_still_wins():
    """An explicitly supplied lot size (legacy callers) keeps precedence."""
    sig = _make_signal("SIG-LOT-EXPLICIT", quantity=130)
    rec = option_fill_reconciler.reconcile_entry(sig, 100.0, 130, 75)
    assert rec is not None
    assert rec.lot_size == 75


@pytest.mark.asyncio
async def test_engine_reconciles_entry_with_contract_lot_size(monkeypatch):
    """execute_signal passes the contract's lot size into reconcile_entry."""
    _seed_mark(150.0)
    _patch_service_price(monkeypatch, 150.0)

    engine = SignalPaperEngine()
    sig = _make_signal("SIG-LOT-ENGINE", quantity=130)

    res = await engine.execute_signal(sig.signal_id, quantity_override=130)

    assert res.success is True
    assert res.lots == 2
    rec = option_fill_reconciler.get_reconciliation(sig.signal_id)
    assert rec is not None
    assert rec.lot_size == CONTRACT_LOT
    assert rec.t1_qty == CONTRACT_LOT
    assert rec.t1_qty != 75  # the hardcoded NIFTY default
    assert rec.remaining_qty == 130
    assert rec.intended_qty == 130


# ── 2a. PENDING ORDERS: SWEEP + FILL ────────────────────────────────────


@pytest.mark.asyncio
async def test_pending_limit_order_stays_pending_until_price_crosses(monkeypatch):
    _patch_service_price(monkeypatch, None)
    order = await paper_service.place_order(
        OrderPayload(
            symbol="NIFTY",
            underlying="NIFTY",
            side="BUY",
            order_type="LIMIT",
            product="INTRADAY",
            quantity=75,
            price=100.0,
        ),
        allow_closed_market=True,
    )
    assert order.status == "PENDING"

    # Market above the buy limit: not touched, still resting.
    assert await paper_service.evaluate_pending_orders("NIFTY", 105.0) == []
    assert order.status == "PENDING"

    # Price crosses the limit: filled at limit-or-better with friction.
    filled = await paper_service.evaluate_pending_orders("NIFTY", 95.0)
    assert len(filled) == 1
    assert filled[0].order_id == order.order_id
    assert filled[0].status == "FILLED"
    assert filled[0].fill_price == pytest.approx(apply_friction(95.0, "BUY"))

    pos = paper_service._positions["NIFTY_INTRADAY"]
    assert pos.is_open is True
    assert pos.quantity == 75
    assert pos.average_price == pytest.approx(filled[0].fill_price)

    # Idempotent: a second sweep cannot double-fill.
    assert await paper_service.evaluate_pending_orders("NIFTY", 95.0) == []
    assert paper_service._positions["NIFTY_INTRADAY"].quantity == 75


@pytest.mark.asyncio
async def test_worker_pending_sweep_fills_crossed_order(monkeypatch):
    _patch_service_price(monkeypatch, None)
    order = await paper_service.place_order(
        OrderPayload(
            symbol="NIFTY",
            underlying="NIFTY",
            side="BUY",
            order_type="LIMIT",
            product="INTRADAY",
            quantity=75,
            price=100.0,
        ),
        allow_closed_market=True,
    )
    assert order.status == "PENDING"

    worker = AutomatedSignalWorker()
    await worker._evaluate_pending_paper_orders({"NIFTY": 95.0})

    assert order.status == "FILLED"
    assert paper_service._positions["NIFTY_INTRADAY"].is_open is True


@pytest.mark.asyncio
async def test_worker_pending_sweep_is_throttled(monkeypatch):
    _patch_service_price(monkeypatch, None)
    order = await paper_service.place_order(
        OrderPayload(
            symbol="NIFTY",
            underlying="NIFTY",
            side="BUY",
            order_type="LIMIT",
            product="INTRADAY",
            quantity=75,
            price=100.0,
        ),
        allow_closed_market=True,
    )

    worker = AutomatedSignalWorker()
    worker._last_pending_sweep_ts = time.time()  # swept moments ago
    await worker._evaluate_pending_paper_orders({"NIFTY": 95.0})

    assert order.status == "PENDING"


@pytest.mark.asyncio
async def test_worker_pending_sweep_resolves_option_symbols_via_service(monkeypatch):
    """An option order with no cached underlying quote resolves via the service."""
    _patch_service_price(monkeypatch, None)
    order = await paper_service.place_order(
        OrderPayload(
            symbol=SYMBOL,
            underlying="NIFTY",
            side="BUY",
            order_type="LIMIT",
            product="INTRADAY",
            quantity=CONTRACT_LOT,
            price=100.0,
        ),
        allow_closed_market=True,
    )
    assert order.status == "PENDING"

    _patch_service_price(monkeypatch, 95.0)  # the chain now quotes below the limit
    worker = AutomatedSignalWorker()
    await worker._evaluate_pending_paper_orders({})

    assert order.status == "FILLED"


# ── 2b. ENGINE PENDING → CANCEL ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_engine_cancels_pending_service_order(monkeypatch):
    """A PENDING service order is cancelled; no ghost resting signal order."""
    _seed_mark(150.0)
    _patch_service_price(monkeypatch, None)
    pending = await paper_service.place_order(
        OrderPayload(
            symbol=SYMBOL,
            underlying="NIFTY",
            side="BUY",
            order_type="LIMIT",
            product="INTRADAY",
            quantity=75,
            price=100.0,
        ),
        allow_closed_market=True,
    )
    assert pending.status == "PENDING"

    engine = SignalPaperEngine()
    sig = _make_signal("SIG-PENDING-CANCEL", quantity=75, lot_size=75)

    with patch.object(paper_service, "place_order", new=AsyncMock(return_value=pending)):
        res = await engine.execute_signal(sig.signal_id, quantity_override=75)

    # Existing failure result shape is preserved...
    assert res.success is False
    assert res.status == "PENDING"
    assert res.order_id == pending.order_id
    assert "resting" in res.message.lower()
    # ...but the resting order was cancelled and the intent is terminal.
    assert pending.status == "CANCELLED"
    assert not any(o.status == "PENDING" for o in paper_service.get_orders())
    intents = intent_ledger.get_by_signal(sig.signal_id)
    assert intents and intents[-1].state == IntentState.REJECTED
    assert position_registry.get_by_signal(sig.signal_id) is None


# ── 3. OFF-DOMAIN PRE-FILL GUARD + POST-FILL ROLLBACK ───────────────────


@pytest.mark.asyncio
async def test_prefill_off_domain_mark_rejected_before_service_dispatch():
    """An index-scale chain mark never reaches paper_service.place_order."""
    _seed_mark(23807.0)  # NIFTY spot leaked into the option mark registry
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-PREFILL-DOMAIN", quantity=75, lot_size=75)

    with patch.object(paper_service, "place_order", new=AsyncMock()) as place_mock:
        res = await engine.execute_signal(sig.signal_id, quantity_override=75)

    assert res.success is False
    assert res.status == "REJECTED"
    assert "OFF_DOMAIN_FILL" in res.message
    assert "premium-domain" in res.message
    assert res.chain_mark_at_fill == pytest.approx(23807.0)
    place_mock.assert_not_awaited()
    assert paper_service.get_orders() == []
    assert [p for p in paper_service._positions.values() if p.is_open] == []
    assert position_registry.get_by_signal(sig.signal_id) is None


@pytest.mark.asyncio
async def test_postfill_off_domain_rolls_back_with_friction_only(monkeypatch):
    """A bad service fill is rolled back: no open position, no fabricated PnL."""
    _seed_mark(150.0)
    bad_live = 23807.0
    _patch_service_price(monkeypatch, bad_live)
    _patch_service_ltp(monkeypatch, bad_live)

    engine = SignalPaperEngine()
    sig = _make_signal("SIG-POSTFILL-DOMAIN", quantity=75, lot_size=75)

    res = await engine.execute_signal(sig.signal_id, quantity_override=75)

    assert res.success is False
    assert res.status == "REJECTED"
    assert "OFF_DOMAIN_FILL" in res.message
    assert res.chain_mark_at_fill == pytest.approx(150.0)

    pos = paper_service._positions[f"{SYMBOL}_INTRADAY"]
    assert pos.is_open is False
    assert pos.quantity == 0
    assert paper_service._realized_pnl == pytest.approx(pos.realized_pnl)

    entry_fill = apply_friction(bad_live, "BUY")
    exit_fill = apply_friction(bad_live, "SELL")
    expected = round((exit_fill - entry_fill) * 75, 2)
    assert pos.realized_pnl == pytest.approx(expected)
    assert expected < 0
    # Round trip is friction-bounded — never the (chain_mark - fill) move.
    assert abs(pos.realized_pnl) <= 0.005 * bad_live * 75

    assert position_registry.get_by_signal(sig.signal_id) is None
    assert signal_audit_ledger.get(sig.signal_id) is None
    intents = intent_ledger.get_by_signal(sig.signal_id)
    assert intents and intents[-1].state == IntentState.REJECTED


@pytest.mark.asyncio
async def test_postfill_band_mismatch_rolls_back_without_fabricated_pnl(monkeypatch):
    """A same-domain fill >3% off the chain mark is rolled back too."""
    _seed_mark(100.0)
    drift_live = 110.0
    _patch_service_price(monkeypatch, drift_live)
    _patch_service_ltp(monkeypatch, drift_live)

    engine = SignalPaperEngine()
    sig = _make_signal("SIG-POSTFILL-BAND", quantity=75, lot_size=75)

    res = await engine.execute_signal(sig.signal_id, quantity_override=75)

    assert res.success is False
    assert res.status == "REJECTED"
    assert "OFF_DOMAIN_FILL" in res.message

    pos = paper_service._positions[f"{SYMBOL}_INTRADAY"]
    assert pos.is_open is False
    assert pos.quantity == 0
    entry_fill = apply_friction(drift_live, "BUY")
    exit_fill = apply_friction(drift_live, "SELL")
    assert pos.realized_pnl == pytest.approx(round((exit_fill - entry_fill) * 75, 2))
    assert pos.realized_pnl < 0
    assert abs(pos.realized_pnl) <= 0.005 * drift_live * 75
