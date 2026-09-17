"""FYERS-only Truth-of-Wall regression tests.

Live market data must come from FYERS API v3 only:
- quotes/history/option-chain parse real FYERS shapes, never fabricate
- auth failure / bad fields -> OFFLINE / [] / None, never synthetic
- IV unsolvable -> greeks None, atm_iv None (no 0.135 / smile formula)
- volatility surface -> percentile/rank/term UNKNOWN, never fabricated
- contract_master bootstrap has no fake strikes, labelled local_calendar_bootstrap
"""
from datetime import datetime, timezone

import pytest

from app.providers.fyers import FyersProvider
from app.providers.registry import get_provider, INDIAN_PROVIDERS
from app.models.market import DataStatus, NormalizedQuote


class _FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp
        self.is_closed = False

    async def get(self, *a, **k):
        return self._resp


def _provider_with(token=None, app_id="APP-100", resp=None):
    # Realistic-length credential for mocked-transport tests: must pass the
    # production placeholder guard (is_usable_access_token) since these tests
    # exercise the live-call path with a stubbed HTTP client.
    if token is None:
        token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9." + "a" * 64 + "." + "b" * 64
    p = FyersProvider(app_id=app_id, secret_key="sec", access_token=token)
    p._http_client = _FakeClient(resp or _FakeResp())
    return p


class TestFyersOnly:
    def test_registry_is_fyers_only(self):
        assert INDIAN_PROVIDERS == ("fyers",)
        assert get_provider().provider_name == "fyers"

    @pytest.mark.asyncio
    async def test_quotes_parse_real_v3_shape(self):
        payload = {
            "s": "ok",
            "d": [
                {"n": "NSE:NIFTY50-INDEX", "v": {
                    "lp": 24812.5, "open_price": 24700.0, "high_price": 24850.0,
                    "low_price": 24680.0, "prev_close_price": 24750.0,
                    "ch": 62.5, "chp": 0.25, "volume": 0,
                }},
                # ltp<=0 must be skipped, never surfaced as LIVE
                {"n": "NSE:NIFTYBANK-INDEX", "v": {"lp": 0.0}},
            ],
        }
        p = _provider_with(resp=_FakeResp(200, payload))
        m = await p._fetch_fyers_quotes(["NIFTY 50", "BANKNIFTY"])
        assert "NIFTY 50" in m
        assert m["NIFTY 50"].ltp == 24812.5
        assert m["NIFTY 50"].provider == "fyers"
        assert "BANKNIFTY" not in m

    @pytest.mark.asyncio
    async def test_quotes_auth_failure_is_offline_not_fake(self):
        p = _provider_with(resp=_FakeResp(200, {"s": "error", "code": 401, "message": "token expired"}))
        q = await p.get_quote("NIFTY 50")
        # No live, no cache yet -> explicit OFFLINE zeros, never demo LTP
        assert q.ltp == 0.0
        assert q.status == DataStatus.OFFLINE
        assert q.provider == "fyers"

    @pytest.mark.asyncio
    async def test_mock_demo_token_never_hits_network(self):
        p = _provider_with(token="mock-demo-token", resp=_FakeResp(200, {"s": "ok", "d": []}))
        m = await p._fetch_fyers_quotes(["NIFTY 50"])
        assert m == {}
        q = await p.get_quote("NIFTY 50")
        assert q.status == DataStatus.OFFLINE

    @pytest.mark.asyncio
    async def test_field_rename_resilience(self):
        # FYERS renames lp -> last_price (unknown field): must skip, not crash, not fake
        payload = {"s": "ok", "d": [{"n": "NSE:NIFTY50-INDEX", "v": {"last_price": 25000.0}}]}
        p = _provider_with(resp=_FakeResp(200, payload))
        m = await p._fetch_fyers_quotes(["NIFTY 50"])
        assert m == {}

    @pytest.mark.asyncio
    async def test_option_chain_failure_is_empty_not_synthetic(self):
        p = _provider_with(token="", resp=_FakeResp(401, {}))
        chain = await p.get_option_chain("NIFTY")
        assert chain == []


class TestNoSyntheticIV:
    @pytest.mark.asyncio
    async def test_unsolvable_iv_yields_none_greeks(self):
        from app.services.options_service import OptionsService
        from app.models.market import NormalizedQuote, NormalizedOptionQuote

        class _MS:
            async def get_quote(self, symbol):
                return NormalizedQuote(
                    symbol=symbol, display_name=symbol,
                    timestamp=datetime.now(timezone.utc),
                    ltp=24800.0, open=24800.0, high=24800.0, low=24800.0,
                    previous_close=24750.0, change=50.0, change_percent=0.2,
                    volume=0, open_interest=None,
                    status=DataStatus.LIVE, provider="fyers",
                )

            async def get_option_chain(self, underlying, expiry=None):
                # Deep-OTM 1-lot premium that cannot solve (below intrinsic floor)
                return [NormalizedOptionQuote(
                    timestamp=datetime.now(timezone.utc), provider="fyers",
                    instrument="X", contract_id="X", underlying=underlying,
                    expiry=expiry or datetime.now(timezone.utc),
                    strike=24800.0, option_type="CE",
                    ltp=0.05, bid=0.05, ask=0.1, volume=0, oi=1000,
                    oi_change=0, change=0.0, change_percent=0.0,
                    previous_close=0.05,
                )]

        svc = OptionsService(market_service=_MS())
        chain = await svc.get_option_chain_matrix("NIFTY")
        assert chain.analytics.atm_iv is None
        assert chain.strikes, "live FYERS strike must be preserved"
        for row in chain.strikes:
            for leg in (row.call, row.put):
                if leg is not None:
                    # Either solved IV or explicit None — never synthetic smile
                    if leg.greeks is not None:
                        assert leg.greeks.iv is not None and leg.greeks.iv > 0

    def test_vol_surface_never_fabricates(self):
        from app.institutional.options_intelligence import vol_surface_engine

        class _G:
            iv = 15.0

        class _Leg:
            greeks = _G()

        class _Row:
            is_atm = True
            call = _Leg()
            put = _Leg()

        class _Analytics:
            atm_iv = 15.0
            iv_skew = 0.5

        class _Chain:
            strikes = [_Row()]
            analytics = _Analytics()

        out = vol_surface_engine.analyze(_Chain())
        assert out["iv_percentile"] is None
        assert out["iv_rank"] is None
        assert out["term_structure"] == "UNKNOWN"
        assert out["iv_change"] is None


class TestContractMasterHonest:
    def test_bootstrap_has_no_fake_strikes(self):
        from app.services.contract_master import ContractMasterService
        from app.models.contracts import ContractType
        fresh = ContractMasterService()
        opts = fresh.search_contracts(contract_type=ContractType.INDEX_OPTION)
        assert opts == [], f"bootstrap must not invent option strikes, found {len(opts)}"
        # Expiry calendar bootstrap exists but labelled local, never fyers
        exps = fresh.get_expiries("NIFTY")
        assert len(exps) > 0
        spot = fresh.get_by_symbol("NIFTY 50")
        assert spot is not None
        assert spot.provider == "local_calendar_bootstrap"


def _gap_day_quote(**overrides):
    """BANKNIFTY gap-up day: prev_close 55794.75 sits below today's range."""
    base = dict(
        symbol="BANKNIFTY",
        display_name="BANKNIFTY",
        timestamp=datetime.now(timezone.utc),
        ltp=56292.45,
        open=56150.0,
        high=56350.0,
        low=56100.0,
        previous_close=55794.75,
        change=497.70,
        change_percent=0.89,
        volume=0,
        open_interest=None,
        status=DataStatus.LIVE,
        provider="fyers",
    )
    base.update(overrides)
    return NormalizedQuote(**base)


class TestTickSanityGapDays:
    def test_gap_up_tick_accepted_prev_close_outside_range(self):
        p = _provider_with(resp=_FakeResp(200, {"s": "ok", "d": []}))
        assert p._quote_passes_sanity("BANKNIFTY", _gap_day_quote()) is True

    def test_gap_down_tick_accepted(self):
        p = _provider_with(resp=_FakeResp(200, {"s": "ok", "d": []}))
        q = _gap_day_quote(ltp=55300.0, open=55400.0, high=55500.0, low=55250.0,
                           previous_close=55794.75, change=-494.75, change_percent=-0.89)
        assert p._quote_passes_sanity("BANKNIFTY", q) is True

    def test_truly_incoherent_tick_still_rejected(self):
        p = _provider_with(resp=_FakeResp(200, {"s": "ok", "d": []}))
        # LTP far above the day's high -> corrupt, must stay rejected
        q = _gap_day_quote(ltp=57000.0)
        assert p._quote_passes_sanity("BANKNIFTY", q) is False

    def test_inverted_range_rejected(self):
        p = _provider_with(resp=_FakeResp(200, {"s": "ok", "d": []}))
        q = _gap_day_quote(low=56350.0, high=56100.0)
        assert p._quote_passes_sanity("BANKNIFTY", q) is False
