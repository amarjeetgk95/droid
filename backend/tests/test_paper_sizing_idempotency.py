"""Phase 2b-2: premium-domain option sizing + stable intent idempotency.

Pins the two behavior fixes on the signal -> paper execution seam:

1. OPTION SIZING: option legs size through the canonical option-buyer resolver
   using the same broker mark that prices the fill and a premium-domain stop
   (delta-gamma projection), instead of the old premium-entry + spot-stop mix
   whose index-scale ``risk_points`` collapsed to 0 lots and was papered over
   by a forced ``max(1, lots)``. Overrides (quantity/lots) and the wallet
   margin downsize / INSUFFICIENT_FUNDS gates keep their behavior.
2. IDEMPOTENCY: the execution intent key excludes the estimated fill price, so
   a retry after the quote moves maps to the same client_order_id. A duplicate
   FILLED intent replays the original fill (same order id / fill price, no
   second order, no second position); a non-filled in-flight intent keeps the
   historical DUPLICATE_ORDER rejection.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.paper_service import PaperTradingService, paper_service
from app.signals.contract_resolver import (
    calculate_option_buyer_sizing,
    calculate_position_sizing,
    resolve_sizing_for_contract,
)
from app.signals.execution_intent import (
    ExecutionIntent,
    IntentState,
    intent_ledger,
    make_execution_intent_id,
    make_fyers_order_tag,
)
from app.signals.fill_reconciler import option_fill_reconciler
from app.signals.fsm import SignalInstance, signal_fsm
from app.signals.paper_engine import SignalPaperEngine
from app.signals.portfolio_greeks import portfolio_greeks_ledger
from app.signals.position import position_registry
from tests.conftest import seed_chain_mark

CE_SYMBOL = "NSE:NIFTY26SEP24800CE"
TICK = "0.05"
PREMIUM = 150.0
#: 0.5 delta on an 80-point spot stop => 40 premium points of risk per share.
GREEKS = {"delta": 0.5, "gamma": 0.0}
EXPECTED_PREMIUM_STOP = PREMIUM - 40.0


@pytest.fixture(autouse=True)
def _isolate_engine_state(mock_market_open, paper_fills_from_marks, monkeypatch, tmp_path):
    """Deterministic, isolated market + paper + intent-ledger state per test."""
    import importlib

    from app.signals.safety.feed_health_monitor import feed_health_monitor

    # Keep the intent ledger's on-disk persistence out of the repo root.
    _intent_mod = importlib.import_module("app.signals.execution_intent")
    monkeypatch.setattr(_intent_mod, "_INTENT_LEDGER_FILE", tmp_path / "intent_ledger.json")

    # An offline test process has no broker feed, so the real monitor reports
    # DOWN. Pin a healthy feed so these tests exercise the execution path.
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

    # MTM reads (get_portfolio_summary) must resolve from the seeded marks, not
    # from an ambient broker chain, so wallet affordability is deterministic.
    async def _resolve_ltp_from_marks(self, pos):
        from app.signals.option_marks import option_mark_registry

        mark = option_mark_registry.get_usable(pos.symbol, allow_model=False)
        if mark is None or mark.price is None:
            return None
        return float(mark.price)

    monkeypatch.setattr(PaperTradingService, "_resolve_live_ltp", _resolve_ltp_from_marks)
    monkeypatch.setattr(
        paper_service,
        "_resolve_live_ltp",
        _resolve_ltp_from_marks.__get__(paper_service, PaperTradingService),
    )

    paper_service.reset_portfolio(capital=1_000_000.0)
    paper_service._user_positions.clear()
    paper_service._user_orders.clear()
    position_registry.clear()
    portfolio_greeks_ledger.clear()
    option_fill_reconciler._records.clear()
    intent_ledger.clear()
    signal_fsm._signals.clear()
    yield
    paper_service.reset_portfolio(capital=1_000_000.0)
    paper_service._user_positions.clear()
    paper_service._user_orders.clear()
    position_registry.clear()
    portfolio_greeks_ledger.clear()
    option_fill_reconciler._records.clear()
    intent_ledger.clear()
    signal_fsm._signals.clear()


def _make_signal(
    signal_id: str,
    *,
    stop_loss: Decimal = Decimal("24720"),
    greeks: dict | None = None,
    fsm_state: str = "TRIGGERED",
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
        stop_loss=stop_loss,
        target_1=Decimal("24920"),
        target_2=Decimal("25000"),
        risk_points=abs(Decimal("24800") - stop_loss),
        risk_reward_t1=1.5,
        risk_reward_t2=2.5,
        confidence=85.0,
        greeks=greeks,
        option_contract={
            "broker_symbol": CE_SYMBOL,
            "strike": 24800.0,
            "option_type": "CE",
            "lot_size": 75,
            "tick_size": TICK,
        },
        fsm_state=fsm_state,
    )
    signal_fsm.register(sig)
    return sig


def _seed(price: float = PREMIUM) -> None:
    seed_chain_mark(CE_SYMBOL, price, underlying="NIFTY", strike=24800.0, option_type="CE")


# ── 1. OPTION SIZING ─────────────────────────────────────────────────


def test_option_buyer_resolver_math_pins():
    """The expected 6-lot / 450-qty baseline really is what the resolver says."""
    expected = calculate_option_buyer_sizing(
        available_capital=1_000_000.0,
        risk_percent=2.0,
        option_entry_premium=PREMIUM,
        option_stop_premium=EXPECTED_PREMIUM_STOP,
        lot_size=75,
    )
    assert expected["lots"] == 6
    assert expected["quantity"] == 450


@pytest.mark.asyncio
async def test_option_sizing_matches_resolver_and_is_not_forced_one_lot():
    """Computed lots come from option-buyer sizing on the seeded chain mark."""
    _seed()
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-SIZE-OPT-1", greeks=GREEKS)

    expected = resolve_sizing_for_contract(
        sig.option_contract,
        available_capital=1_000_000.0,
        risk_percent=2.0,
        option_entry_premium=PREMIUM,
        option_stop_premium=EXPECTED_PREMIUM_STOP,
    )
    assert expected["sizing_basis"] == "OPTION_PREMIUM"
    assert expected["lots"] == 6

    res = await engine.execute_signal(sig.signal_id)

    assert res.success is True
    assert res.lots == expected["lots"] == 6
    assert res.quantity == expected["quantity"] == 450
    assert res.order_id

    pos = paper_service._positions[f"{CE_SYMBOL}_INTRADAY"]
    assert pos.is_open is True
    assert pos.quantity == 450


@pytest.mark.asyncio
async def test_option_sizing_premium_domain_not_premium_entry_spot_stop():
    """Regression pin: the old premium-entry/spot-stop mix yields 0 lots."""
    _seed()
    sig = _make_signal("SIG-SIZE-OPT-2", greeks=GREEKS)

    wrong_domain = calculate_position_sizing(
        available_capital=1_000_000.0,
        risk_percent=2.0,
        entry_price=PREMIUM,
        stop_loss=float(sig.stop_loss),  # 24,720 index level
        lot_size=75,
    )
    assert wrong_domain["lots"] == 0
    assert wrong_domain["allowed"] is False

    engine = SignalPaperEngine()
    res = await engine.execute_signal(sig.signal_id)
    assert res.success is True
    assert res.lots == 6  # not the forced-1-lot floor of the old path


@pytest.mark.asyncio
async def test_quantity_override_precedence_unchanged():
    """Explicit quantity beats computed premium sizing (450 -> 225)."""
    _seed()
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-SIZE-QTY", greeks=GREEKS)

    res = await engine.execute_signal(sig.signal_id, quantity_override=225)
    assert res.success is True
    assert res.quantity == 225
    assert res.lots == 3
    assert paper_service._positions[f"{CE_SYMBOL}_INTRADAY"].quantity == 225


@pytest.mark.asyncio
async def test_lots_override_precedence_unchanged():
    """Explicit lots beat computed premium sizing and expand to lot-size qty."""
    _seed()
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-SIZE-LOTS", greeks=GREEKS)

    res = await engine.execute_signal(sig.signal_id, lots_override=3)
    assert res.success is True
    assert res.lots == 3
    assert res.quantity == 225
    assert paper_service._positions[f"{CE_SYMBOL}_INTRADAY"].quantity == 225


@pytest.mark.asyncio
async def test_wallet_margin_downsize_still_applies():
    """An oversized request steps down to the largest lot count the wallet fits."""
    paper_service.reset_portfolio(capital=100_000.0)
    _seed()
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-SIZE-DOWNSIZE", greeks=GREEKS)

    # 20 lots * 75 * ~150.25 est fill = ~225k required vs a 100k wallet.
    res = await engine.execute_signal(sig.signal_id, lots_override=20)

    assert res.success is True
    assert res.lots == 8
    assert res.quantity == 600
    assert "downsized" in res.message
    assert paper_service._positions[f"{CE_SYMBOL}_INTRADAY"].quantity == 600


@pytest.mark.asyncio
async def test_low_capital_option_sizing_rejects_instead_of_forcing_one_lot():
    """When the resolver refuses the smallest lot the engine rejects; no 1-lot fill."""
    paper_service.reset_portfolio(capital=5_000.0)
    _seed()
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-SIZE-NOCAP", greeks=GREEKS)

    res = await engine.execute_signal(sig.signal_id)

    assert res.success is False
    assert res.status == "REJECTED"
    assert res.lots == 0
    assert res.quantity == 0
    assert "SIZING_REJECTED" in res.message
    assert paper_service.get_orders() == []
    assert position_registry.get_by_signal(sig.signal_id) is None


@pytest.mark.asyncio
async def test_insufficient_funds_rejection_still_applies():
    """The engine's own margin gate still rejects a fixed qty the wallet can't cover."""
    paper_service.reset_portfolio(capital=5_000.0)
    _seed()
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-SIZE-FUNDS", greeks=GREEKS)

    res = await engine.execute_signal(sig.signal_id, quantity_override=75)

    assert res.success is False
    assert res.status == "REJECTED"
    assert "INSUFFICIENT_FUNDS" in res.message
    assert paper_service.get_orders() == []


# ── 2. STABLE INTENT KEY ─────────────────────────────────────────────


def test_intent_key_is_stable_across_fill_price_moves():
    """Same logical action + same qty => same id/tag regardless of price_tick."""
    kwargs = dict(
        signal_id="sig-idem-key",
        signal_version=1,
        action="BUY_CE",
        position_id="",
        trigger_version=1,
        side="BUY",
        symbol=CE_SYMBOL,
        quantity=450,
    )
    id_low = make_execution_intent_id(**kwargs, price_tick="150.25")
    id_high = make_execution_intent_id(**kwargs, price_tick="161.75")

    assert id_low == id_high
    assert len(id_low) == 32
    assert make_fyers_order_tag(id_low) == make_fyers_order_tag(id_high)
    assert make_fyers_order_tag(id_low).startswith("DRD_")

    # Quantity remains part of the identity: a different size is a new intent.
    assert make_execution_intent_id(**{**kwargs, "quantity": 375}, price_tick="150.25") != id_low


# ── 3. DUPLICATE REPLAY / REJECTION ──────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_across_quote_move_replays_original_fill():
    """Retry after the mark moves: one order, one position, original fill replayed."""
    _seed(150.0)
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-IDEM-REPLAY", greeks=GREEKS)

    first = await engine.execute_signal(sig.signal_id)
    assert first.success is True
    assert first.lots == 6

    # The quote moves before the retry — the old price-in-hash key changed here.
    _seed(160.0)

    second = await engine.execute_signal(sig.signal_id)

    assert second.success is True
    assert second.status == "FILLED"
    assert second.order_id == first.order_id
    assert second.fill_price == pytest.approx(first.fill_price)
    assert second.quantity == first.quantity
    assert "DUPLICATE_REPLAY" in second.message

    fills = [
        o
        for o in paper_service.get_orders()
        if o.status == "FILLED" and o.side == "BUY" and o.symbol == CE_SYMBOL
    ]
    assert len(fills) == 1
    assert fills[0].order_id == first.order_id

    open_positions = [p for p in paper_service._positions.values() if p.is_open]
    assert len(open_positions) == 1
    assert open_positions[0].quantity == first.quantity
    assert position_registry.get_by_signal(sig.signal_id) is not None


@pytest.mark.asyncio
async def test_duplicate_when_prior_intent_not_filled_keeps_rejection():
    """A SUBMITTED (in-flight) intent keeps the historical DUPLICATE_ORDER reject."""
    _seed()
    engine = SignalPaperEngine()
    sig = _make_signal("SIG-IDEM-INFLIGHT", greeks=GREEKS)

    intent_id = make_execution_intent_id(
        signal_id=sig.signal_id,
        signal_version=1,
        action="BUY_CE",
        position_id="",
        trigger_version=1,
        side="BUY",
        symbol=CE_SYMBOL,
        quantity=75,
    )
    intent_ledger.register(
        ExecutionIntent(
            execution_intent_id=intent_id,
            signal_id=sig.signal_id,
            signal_version=1,
            action="BUY_CE",
            state=IntentState.SUBMITTED,
            broker_client_order_id=make_fyers_order_tag(intent_id),
            instrument_symbol=CE_SYMBOL,
            side="BUY",
            intended_quantity=75,
        )
    )

    res = await engine.execute_signal(sig.signal_id, quantity_override=75)

    assert res.success is False
    assert res.status == "REJECTED"
    assert "DUPLICATE_ORDER" in res.message
    assert paper_service.get_orders() == []
    assert position_registry.get_by_signal(sig.signal_id) is None
