import re
from datetime import datetime, timezone
from unittest.mock import patch
import zoneinfo
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.calendar_service import MarketSessionPermission, calendar_service


#: Deterministic pinned feed levels. Chosen so every hard-coded index price in
#: the signal tests (NIFTY 24800-24940) sits inside both the 5% manual-quote
#: drift corridor and the 0.5% execution slippage policy.
PINNED_FEED: dict[str, float] = {
    "NIFTY 50": 24870.0,
    "BANKNIFTY": 57780.0,
    "SENSEX": 81000.0,
}

#: Matches a Fyers option contract symbol, e.g. NSE:NIFTY24DEC24850CE.
OPTION_SYMBOL_RE = re.compile(r"\d(CE|PE)$")

_PINNED_ALIASES: dict[str, str] = {
    "NIFTY": "NIFTY 50",
    "NIFTY50": "NIFTY 50",
    "BANKNIFTY": "BANKNIFTY",
    "SENSEX": "SENSEX",
    "BSESENSEX": "SENSEX",
}


def seed_chain_mark(
    broker_symbol: str,
    price: float,
    underlying: str = "NIFTY",
    strike: float | None = None,
    option_type: str = "CE",
) -> "object":
    """Publish a real (FYERS-chain) mark for `broker_symbol`.

    The signal stack now fails closed: nothing fills, marks or exits without a
    broker-sourced price, so a test that wants the happy path must publish the
    quote the broker would have returned. Use this instead of asserting against
    a Black-76 estimate.
    """
    from app.signals.option_marks import OptionMark, option_mark_registry

    mark = OptionMark(
        broker_symbol=broker_symbol,
        underlying=underlying,
        strike=float(strike or 0.0),
        option_type=option_type,
        ltp=round(float(price), 2),
        source="CHAIN_LTP",
        note="test chain mark",
    )
    option_mark_registry.put(mark)
    return mark


def chain_contract(
    broker_symbol: str,
    strike: float,
    option_type: str = "CE",
    lot_size: int = 75,
    premium: float = 150.0,
) -> dict:
    """Contract dict shaped exactly as the resolver emits it when the live
    FYERS chain answered: provenance plus the broker's own mid."""
    return {
        "broker_symbol": broker_symbol,
        "strike": strike,
        "option_type": option_type,
        "lot_size": lot_size,
        "contract_source": "fyers_chain",
        "live_premium": float(premium),
    }


@pytest.fixture
def paper_fills_from_marks(monkeypatch):
    """Price paper fills from the chain marks the test published.

    In production ``paper_service._resolve_live_ltp`` consults the FYERS option
    chain for a contract symbol. A unit test has no broker, so without this the
    fill depends on whatever ambient chain state happens to be cached in the
    process — which makes the outcome depend on test ordering. Wiring the
    service to the mark registry makes the fill deterministic and matches the
    real contract: the broker quote is the fill.
    """
    from app.services.paper_service import PaperTradingService, paper_service
    from app.signals.option_marks import option_mark_registry

    async def _resolve_from_marks(self, symbol, underlying=None):
        mark = option_mark_registry.get_usable(symbol, allow_model=False)
        if mark is None or mark.price is None:
            return None
        return float(mark.price)

    monkeypatch.setattr(PaperTradingService, "_resolve_live_for_symbol", _resolve_from_marks)
    monkeypatch.setattr(paper_service, "_resolve_live_for_symbol", _resolve_from_marks.__get__(paper_service, PaperTradingService))
    yield


@pytest.fixture(autouse=True)
def isolate_option_marks():
    """Keep published chain marks from leaking across tests."""
    from app.signals.option_marks import option_mark_registry

    option_mark_registry.clear()
    yield
    option_mark_registry.clear()


@pytest.fixture
def client():
    """FastAPI test client."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_market_feed(monkeypatch):
    """Pin the market-data feed to deterministic LIVE quotes.

    Both safety guards on the generate path compare the caller's price against
    the *live* LTP: >5% drift is rejected with 400, and a fill >0.5% off the
    expected entry keeps execution at CONFIRMED instead of EXECUTED. With no
    pinned feed those guards measure the ambient provider, so a test that
    hard-codes NIFTY 24915 passes on the day NIFTY trades there and fails on
    any other day - a green suite that says nothing about correctness.

    Pinning the feed makes the guards themselves testable and the suite
    deterministic with the market closed and the local snapshot stale.
    """
    from app.models.market import DataStatus, NormalizedQuote
    from app.services.market_service import MarketService

    async def _pinned_get_quote(self, symbol: str) -> NormalizedQuote:
        key = str(symbol or "").upper().replace(" ", "")

        # This feed pins INDEX levels only. A contract symbol like
        # NSE:NIFTY24DEC24850CE must NOT be answered here: the substring alias
        # match below would return the NIFTY index level for it, and the paper
        # service would then "fill" a ₹150 option at ~24,870 — an index price
        # booked on an option leg. Refusing forces fail-closed: no live quote
        # means the MARKET order is REJECTED (tests publish chain marks via
        # seed_chain_mark + paper_fills_from_marks for the happy path).
        if OPTION_SYMBOL_RE.search(key):
            raise ValueError(f"Invalid or unsupported symbol: {symbol}")

        resolved = _PINNED_ALIASES.get(key)
        if resolved is None:
            for alias, name in _PINNED_ALIASES.items():
                if alias in key:
                    resolved = name
                    break
        if resolved is None:
            raise ValueError(f"Invalid or unsupported symbol: {symbol}")

        ltp = PINNED_FEED[resolved]
        return NormalizedQuote(
            symbol=resolved,
            display_name=resolved,
            timestamp=datetime.now(timezone.utc),
            ltp=ltp,
            open=ltp,
            high=ltp,
            low=ltp,
            previous_close=ltp,
            change=0.0,
            change_percent=0.0,
            volume=0,
            status=DataStatus.LIVE,
            provider="fyers",
        )

    monkeypatch.setattr(MarketService, "get_quote", _pinned_get_quote)
    yield PINNED_FEED


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
    """Ensure test runs write to an isolated temporary state file and do not pollute production state or database."""
    test_state_file = tmp_path / "test_signals_state.json"
    monkeypatch.setattr("app.signals.signals_persistence.SIGNALS_STATE_FILE", test_state_file)
    # The cold-start snapshot path is CWD-relative (settings.snapshot_file_path),
    # so a test run started from backend/ writes `backend/market_snapshot.json`
    # and the NEXT run's app lifespan warms from it. Because the app polls the
    # real FYERS feed when a token is present, that file can carry live-looking
    # prices (e.g. NIFTY 23346.4) straight into the degraded-path tests — which
    # then report a fabricated price with the feed "down". Point the snapshot
    # service at tmp so the suite neither reads nor writes repo state.
    from app.services.snapshot_service import snapshot_service

    monkeypatch.setattr(snapshot_service, "snapshot_path", tmp_path / "market_snapshot.json")
    from app.services.market_data_coordinator import market_data_coordinator

    market_data_coordinator._cache.clear()
    # The market-data coordinator memoizes provider answers process-wide and is
    # also warmed by the dashboard startup prewarm. A value cached by an earlier
    # test (or by the prewarm running against a live FYERS token) then gets
    # served to every later test, which is how "the feed is down" assertions
    # end up seeing real prices. Start each test from an empty cache.
    monkeypatch.setattr("app.core.database.get_async_session_factory", lambda: None)
    monkeypatch.setattr("app.signals.signals_persistence.get_async_session_factory", lambda: None)
    # The suite must stay hermetic: never let the FYERS HSM socket start from a
    # test's app lifespan / ensure_provider_stream() and feed the real broker
    # snapshots into the global central_feed (that would make OFFLINE/degraded
    # assertions depend on the machine's .fyers_token and the wall clock).
    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "fyers_ws_enabled", False, raising=False)
    from app.signals.fsm import signal_fsm
    from app.signals.audit_ledger import signal_audit_ledger
    from app.core import broker_runtime
    from app.algo.algo_service import reset_algo_caches

    # Isolate fail-closed safety state so a stale token / degraded feed in the
    # environment (e.g. an expired backend/.fyers_token) cannot block execution
    # across the whole suite.
    import importlib
    _sv_mod = importlib.import_module("app.signals.safety.sequence_validator")
    _fhm_mod = importlib.import_module("app.signals.safety.feed_health_monitor")
    _sw_persist = importlib.import_module("app.swing.persistence")
    from app.signals.safety.feed_circuit import feed_circuit

    monkeypatch.setattr(_sv_mod, "_SEQ_STATE_FILE", tmp_path / "sequence_state.json")
    # Swing state files are CWD-relative: isolate them to tmp so tests never
    # overwrite the real swing_state.json, and reset the scanner's cached last
    # scan (test_swing_api seeds the state file and reads the fallback path).
    monkeypatch.setattr(_sw_persist, "SWING_STATE_FILE", tmp_path / "swing_state.json")
    monkeypatch.setattr(_sw_persist, "SWING_CANDLES_CACHE_FILE", tmp_path / "swing_candles_cache.json")
    from app.swing.scanner import swing_scanner
    swing_scanner._last_scan_result = None
    swing_scanner._candle_cache.clear()
    swing_scanner._disk_cache.clear()

    feed_circuit._states.clear()
    monkeypatch.setattr(_fhm_mod, "_TELEMETRY_CACHE", {"ts_ns": 0, "payload": None})
    monkeypatch.setattr(_fhm_mod, "_last_raw", None)
    monkeypatch.setattr(_fhm_mod, "_stable_status", None)
    monkeypatch.setattr(_fhm_mod, "_stable_count", 0)

    broker_runtime.reset()
    reset_algo_caches()
    with signal_fsm._lock:
        orig_signals = dict(signal_fsm._signals)
    with signal_audit_ledger._lock:
        orig_trades = dict(signal_audit_ledger._trades)
    yield
    broker_runtime.reset()
    reset_algo_caches()
    feed_circuit._states.clear()
    with signal_fsm._lock:
        signal_fsm._signals.clear()
        signal_fsm._signals.update(orig_signals)
    with signal_audit_ledger._lock:
        signal_audit_ledger._trades.clear()
        signal_audit_ledger._trades.update(orig_trades)