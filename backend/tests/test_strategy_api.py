"""Strategy Engine API tests.

Regression focus:
- `template_id` must actually select the structure (the endpoint used to return
  a bull call spread for every template).
- Strikes land on the instrument's real strike grid, with that instrument's own
  lot size — never a hardcoded 50-point/75-lot assumption.
- Legs this engine cannot price honestly are rejected (422) or reported with a
  limitation; an unknown `side`/`option_type` must never be silently coerced
  into the opposite trade.
- Unbounded tails report null bounds instead of a sampled-grid number that
  hides an uncapped loss.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.strategy import TEMPLATES
from app.main import app
from app.signals.contract_resolver import INDEX_CONTRACT_CONFIGS

client = TestClient(app)

NIFTY_STEP = float(INDEX_CONTRACT_CONFIGS["NIFTY"]["strike_interval"])
NIFTY_LOT = int(INDEX_CONTRACT_CONFIGS["NIFTY"]["lot_size"])
BANKNIFTY_STEP = float(INDEX_CONTRACT_CONFIGS["BANKNIFTY"]["strike_interval"])
BANKNIFTY_LOT = int(INDEX_CONTRACT_CONFIGS["BANKNIFTY"]["lot_size"])


def _build(template_id: str, symbol: str = "NIFTY"):
    return client.post(f"/api/v1/strategy/build-template?template_id={template_id}&symbol={symbol}")


def _atm(spot: float, step: float) -> float:
    return round(spot / step) * step


class TestTemplateCatalogue:
    def test_get_templates_api(self):
        r = client.get("/api/v1/strategy/templates")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) >= 8

    def test_every_listed_template_is_buildable(self, mock_market_feed):
        """Catalogue and builder map cannot drift apart."""
        for row in TEMPLATES:
            r = _build(row["id"])
            assert r.status_code == 200, f"{row['id']} -> {r.status_code}: {r.text[:200]}"
            data = r.json()["data"]
            assert data["template_id"] == row["id"]
            assert data["template_name"] == row["name"]

    def test_unknown_template_id_is_rejected(self, mock_market_feed):
        r = _build("invented_structure")
        assert r.status_code == 422
        assert "Unknown template_id" in r.json()["detail"]

    def test_unsupported_underlying_is_rejected(self, mock_market_feed):
        r = _build("bull_call_spread", "FINNIFTY")
        assert r.status_code == 422


class TestBuildTemplate:
    def test_build_template_api(self, mock_market_feed):
        """Builds off the LIVE spot, on the instrument's own strike grid."""
        spot = mock_market_feed["NIFTY 50"]
        r = _build("bull_call_spread")
        assert r.status_code == 200
        body = r.json()
        data = body["data"]
        assert data["spot_price"] == spot
        assert data["legs"][0]["strike"] == _atm(spot, NIFTY_STEP)
        assert data["legs"][0]["side"] == "BUY"
        assert data["legs"][1]["side"] == "SELL"
        assert data["legs"][1]["strike"] > data["legs"][0]["strike"]
        assert (data["legs"][1]["strike"] - data["legs"][0]["strike"]) % NIFTY_STEP == 0
        assert data["legs"][0]["lot_size"] == NIFTY_LOT
        assert data["premium_source"] == "ESTIMATED"
        assert "premium_note" in data
        assert data["expiry"]
        assert data["payoff_curve"]
        assert data["defined_risk"] is True
        assert data["max_profit"] > 0
        assert data["max_loss"] < 0
        assert data["risk_reward"] > 0

    def test_build_template_fails_closed_without_live_spot(self):
        """Truth-of-Wall: a dead feed must 503 — never a strategy on a hardcoded price."""
        with patch(
            "app.services.market_service.MarketService.get_quote",
            side_effect=RuntimeError("feed down"),
        ):
            r = _build("bull_call_spread")
        assert r.status_code == 503
        assert "no live" in str(r.json().get("detail", "")).lower()

    def test_template_id_selects_the_structure(self, mock_market_feed):
        """The headline regression: picking a template must not return a bull call spread."""
        short_straddle = _build("short_straddle").json()["data"]
        assert [leg["side"] for leg in short_straddle["legs"]] == ["SELL", "SELL"]
        assert {leg["option_type"] for leg in short_straddle["legs"]} == {"CE", "PE"}
        assert short_straddle["defined_risk"] is False
        assert short_straddle["max_loss"] is None  # naked call side is uncapped

        iron_condor = _build("iron_condor").json()["data"]
        assert [leg["side"] for leg in iron_condor["legs"]] == ["BUY", "SELL", "SELL", "BUY"]
        strikes = [leg["strike"] for leg in iron_condor["legs"]]
        assert strikes == sorted(strikes)
        assert iron_condor["defined_risk"] is True
        assert iron_condor["max_loss"] is not None

        ratio = _build("ratio_spread").json()["data"]
        sells = [leg for leg in ratio["legs"] if leg["side"] == "SELL"]
        assert sells and sells[0]["quantity"] == 2
        assert ratio["defined_risk"] is False  # net short call is uncapped above

    def test_strikes_and_lots_follow_the_instrument(self, mock_market_feed):
        spot = mock_market_feed["BANKNIFTY"]
        data = _build("iron_butterfly", "BANKNIFTY").json()["data"]
        atm = data["legs"][0]["strike"] + (data["legs"][1]["strike"] - data["legs"][0]["strike"])
        assert atm == _atm(spot, BANKNIFTY_STEP)
        for leg in data["legs"]:
            assert leg["lot_size"] == BANKNIFTY_LOT
            assert abs(leg["strike"] - atm) % BANKNIFTY_STEP == 0

    def test_calendar_spread_reports_no_invented_payoff(self, mock_market_feed):
        """Cross-expiry P&L is not an expiry-intrinsic curve — say so."""
        data = _build("calendar_spread").json()["data"]
        assert data["payoff_model"] == "UNMODELLED"
        assert data["payoff_curve"] == []
        assert data["max_profit"] is None
        assert data["max_loss"] is None
        assert data["risk_reward"] is None
        assert "limitation" in data
        expiries = {leg["expiry"] for leg in data["legs"]}
        assert len(expiries) == 2
        assert data["far_expiry"] in expiries


class TestPayoffEndpoint:
    def test_calculate_payoff_custom_api(self):
        payload = {
            "underlying": "NIFTY",
            "spot_price": 25000.0,
            "expiry": "2026-09-03",
            "legs": [
                {
                    "id": "leg1",
                    "option_type": "CE",
                    "side": "BUY",
                    "strike": 25000.0,
                    "quantity": 1,
                    "price": 140.0,
                    "iv": 0.15,
                    "expiry": "2026-09-03",
                    "lot_size": 75,
                }
            ],
        }
        r = client.post("/api/v1/strategy/payoff", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["underlying"] == "NIFTY"
        assert len(body["data"]["payoff_curve"]) > 0
        at_strike = next(p for p in body["data"]["payoff_curve"] if p["spot"] == 25000.0)
        assert at_strike["pnl"] == pytest.approx(-140.0 * 75)

    def test_legs_without_lot_size_use_the_underlying_lot(self):
        """A leg that omits lot_size must price at BANKNIFTY's lot (30), not 75."""
        payload = {
            "underlying": "BANKNIFTY",
            "spot_price": 57800.0,
            "legs": [
                {"option_type": "CE", "side": "BUY", "strike": 57800.0, "quantity": 1, "price": 300.0},
            ],
        }
        data = client.post("/api/v1/strategy/payoff", json=payload).json()["data"]
        assert data["default_lot_size"] == BANKNIFTY_LOT
        at_strike = next(p for p in data["payoff_curve"] if p["spot"] == 57800.0)
        assert at_strike["pnl"] == pytest.approx(-300.0 * BANKNIFTY_LOT)

    @pytest.mark.parametrize(
        "leg",
        [
            {"option_type": "C", "side": "BUY", "strike": 25000.0, "quantity": 1, "price": 100.0},
            {"option_type": "CE", "side": "buy", "strike": 25000.0, "quantity": 1, "price": 100.0},
            {"option_type": "CE", "side": "BUY", "strike": 25000.0, "quantity": 0, "price": 100.0},
            {"option_type": "CE", "side": "BUY", "strike": 0.0, "quantity": 1, "price": 100.0},
        ],
    )
    def test_unpriceable_legs_are_rejected(self, leg):
        """Unknown side/type used to be silently read as SELL/PE — an inverted payoff."""
        r = client.post(
            "/api/v1/strategy/payoff",
            json={"underlying": "NIFTY", "spot_price": 25000.0, "legs": [leg]},
        )
        assert r.status_code == 422

    def test_naked_short_call_reports_uncapped_loss(self):
        payload = {
            "underlying": "NIFTY",
            "spot_price": 25000.0,
            "legs": [
                {"option_type": "CE", "side": "SELL", "strike": 25050.0, "quantity": 1, "price": 120.0},
            ],
        }
        data = client.post("/api/v1/strategy/payoff", json=payload).json()["data"]
        assert data["defined_risk"] is False
        assert data["max_loss"] is None
        assert data["max_profit"] is not None
        assert data["risk_reward"] is None

    def test_defined_risk_spread_bounds_are_exact(self):
        payload = {
            "underlying": "NIFTY",
            "spot_price": 25000.0,
            "legs": [
                {"option_type": "CE", "side": "BUY", "strike": 25000.0, "quantity": 1, "price": 150.0},
                {"option_type": "CE", "side": "SELL", "strike": 25200.0, "quantity": 1, "price": 60.0},
            ],
        }
        data = client.post("/api/v1/strategy/payoff", json=payload).json()["data"]
        assert data["defined_risk"] is True
        assert data["max_profit"] == pytest.approx((200.0 - 90.0) * NIFTY_LOT)
        assert data["max_loss"] == pytest.approx(-90.0 * NIFTY_LOT)
        assert data["risk_reward"] == pytest.approx(110.0 / 90.0, abs=0.01)

    def test_mixed_expiries_carry_a_limitation(self):
        payload = {
            "underlying": "NIFTY",
            "spot_price": 25000.0,
            "legs": [
                {"option_type": "CE", "side": "SELL", "strike": 25000.0, "quantity": 1, "price": 150.0, "expiry": "2026-09-03"},
                {"option_type": "CE", "side": "BUY", "strike": 25000.0, "quantity": 1, "price": 190.0, "expiry": "2026-09-10"},
            ],
        }
        data = client.post("/api/v1/strategy/payoff", json=payload).json()["data"]
        assert "limitation" in data


class TestScanner:
    def test_scanner_api(self):
        """Truth-of-Wall: no fabricated recommendations — honest empty result
        with the limitation stated until real chain analytics are wired in."""
        r = client.get("/api/v1/strategy/scanner?min_pop=20.0")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["scans"] == []
        assert body["data"]["count"] == 0
        assert "not yet wired" in body["data"]["limitation"]
