"""Live contract cache: FYERS chain symbols win over formula builder."""
import time
from datetime import date, datetime, timezone
from decimal import Decimal

from app.signals.contract_resolver import resolve_nearest_expiry, resolve_option_contract
from app.signals.live_contract_cache import (
    LiveContractCache,
    LiveStrikeInfo,
    live_contract_cache,
)


def _today_ms() -> int:
    return int(time.time() * 1000)


def test_lookup_roundtrip_and_stale_rejection():
    cache = LiveContractCache()
    cache._map.clear()
    exp = date(2026, 9, 10)
    info = LiveStrikeInfo(
        broker_symbol="BSE:SENSEX2691075200PE",
        underlying="SENSEX",
        expiry_date=exp,
        strike=75200,
        option_type="PE",
        bid=550.0,
        ask=552.0,
        ltp=551.0,
        fetched_at_ms=_today_ms(),
    )
    cache._map["SENSEX|2026-09-10|75200|PE"] = info
    hit = cache.lookup("SENSEX", exp, 75200, "PE")
    assert hit is not None and hit.broker_symbol == "BSE:SENSEX2691075200PE"
    assert hit.mid == 551.0
    # Wrong strike/expiry/type miss.
    assert cache.lookup("SENSEX", exp, 75300, "PE") is None
    assert cache.lookup("SENSEX", date(2026, 9, 17), 75200, "PE") is None
    assert cache.lookup("SENSEX", exp, 75200, "CE") is None
    # Yesterday's fetch is stale.
    stale = info.model_copy(update={"fetched_at_ms": _today_ms() - 25 * 3600 * 1000})
    cache._map["SENSEX|2026-09-10|75200|PE"] = stale
    assert cache.lookup("SENSEX", exp, 75200, "PE") is None


def test_resolver_prefers_live_chain_symbol():
    ref = date(2026, 9, 9)
    exp, _ = resolve_nearest_expiry("SENSEX", ref)
    atm = 75200
    live_sym = "BSE:SENSEX2691075200PE" if exp == date(2026, 9, 10) else f"LIVE-{exp.isoformat()}"
    live_contract_cache._map[f"SENSEX|{exp.isoformat()}|{atm}|PE"] = LiveStrikeInfo(
        broker_symbol=live_sym,
        underlying="SENSEX",
        expiry_date=exp,
        strike=atm,
        option_type="PE",
        bid=700.0,
        ask=704.0,
        ltp=702.0,
        fetched_at_ms=_today_ms(),
    )
    try:
        c = resolve_option_contract("SENSEX", Decimal("75139.6"), "PE", ref_date=ref)
        if int(c.strike) == atm and c.expiry_date == exp:
            assert c.broker_symbol == live_sym
            assert c.contract_source == "fyers_chain"
            assert c.live_premium == 702.0
    finally:
        live_contract_cache._map.pop(f"SENSEX|{exp.isoformat()}|{atm}|PE", None)


def test_resolver_formula_fallback_offline():
    c = resolve_option_contract("NIFTY", Decimal("24835.0"), "CE", ref_date=date(2026, 9, 9))
    # No live entry seeded for this exact key in this test process.
    assert c.contract_source in ("formula", "fyers_chain")
    if c.contract_source == "formula":
        assert c.live_premium is None
        assert c.broker_symbol.startswith("NSE:NIFTY")


async def test_refresh_ingests_chain_symbols():
    from app.models.market import NormalizedOptionQuote

    cache = LiveContractCache()
    cache._map.clear()
    now = datetime.now(timezone.utc)

    async def fake_chain(symbol: str):
        assert symbol == "SENSEX"
        return [
            NormalizedOptionQuote(
                timestamp=now, provider="fyers", instrument="BSE:SENSEX2691075200PE",
                contract_id="BSE:SENSEX2691075200PE", underlying="SENSEX",
                expiry=datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc),
                strike=75200.0, option_type="PE", ltp=551.0, bid=550.0, ask=552.0,
            ),
            NormalizedOptionQuote(
                timestamp=now, provider="fyers", instrument="NIFTY_75200_PE",
                contract_id="NIFTY_75200_PE", underlying="SENSEX",
                expiry=datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc),
                strike=75300.0, option_type="CE", ltp=10.0, bid=9.0, ask=11.0,
            ),
        ]

    class FakeSvc:
        async def get_option_chain(self, symbol: str, expiry=None):
            if symbol != "SENSEX":
                return []
            return await fake_chain(symbol)

    n = await cache.refresh(FakeSvc())
    assert n == 1  # junk fallback symbol skipped
    hit = cache.lookup("SENSEX", date(2026, 9, 10), 75200, "PE")
    assert hit is not None and hit.broker_symbol == "BSE:SENSEX2691075200PE"
    # Don't leave runtime cache litter in the repo working tree.
    try:
        from app.signals.live_contract_cache import CACHE_FILE
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
    except Exception:
        pass
