import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_api_calculate_greeks(client):
    payload = {
        "spot": 24900.0,
        "strike": 24900.0,
        "dte_days": 5.0,
        "volatility": 0.15,
        "option_type": "CE",
    }
    resp = client.post("/api/v1/options-intelligence/greeks", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert 0.45 < data["delta"] < 0.55
    assert data["theta_hour"] < 0
    assert data["is_atm"] is True


def test_api_solve_iv(client):
    payload = {
        "market_price": 185.0,
        "spot": 24900.0,
        "strike": 24900.0,
        "dte_days": 5.0,
        "option_type": "CE",
    }
    resp = client.post("/api/v1/options-intelligence/solve-iv", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "implied_volatility" in data
    assert 0.05 < data["implied_volatility"] < 0.50


def test_api_simulate_path(client):
    payload = {
        "underlying": "NIFTY",
        "spot": 24900.0,
        "strike": 24900.0,
        "option_type": "CE",
        "dte_days": 4.0,
        "iv": 0.15,
        "target_spot": 24980.0,
        "stop_spot": 24860.0,
        "quantity": 75,
    }
    resp = client.post("/api/v1/options-intelligence/simulate-path", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "fast_target" in data
    assert "slow_target" in data
    assert "sideways" in data
    assert "is_economically_viable" in data


def test_api_select_contract(client):
    payload = {
        "underlying": "NIFTY",
        "spot_price": 24920.0,
        "direction": "LONG_CALL",
        "expected_move_points": 70.0,
        "stop_loss_points": 25.0,
        "current_iv": 0.15,
    }
    resp = client.post("/api/v1/options-intelligence/select-contract", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["underlying"] == "NIFTY"
    assert data["selected_strike_type"] in ("ITM_1", "ATM", "OTM_1")
    assert len(data["all_candidates"]) == 3


def test_api_expected_move(client):
    payload = {
        "underlying": "BANKNIFTY",
        "spot": 53200.0,
        "direction": "BULLISH",
        "horizon": "INTRADAY",
        "current_iv": 0.17,
    }
    resp = client.post("/api/v1/options-intelligence/expected-move", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["underlying"] == "BANKNIFTY"
    assert data["expected_move_points"] > 0
    assert "is_fast_enough_for_option" in data


def test_api_portfolio_greeks_summary(client):
    resp = client.get("/api/v1/options-intelligence/portfolio-greeks/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_delta" in data
    assert "total_gamma" in data
    assert "total_theta_day" in data


def test_api_financial_research_context(client):
    resp = client.get("/api/v1/options-intelligence/financial-research/NIFTY?horizon=INTRADAY&direction=BULLISH")
    assert resp.status_code == 200
    data = resp.json()
    assert data["underlying"] == "NIFTY"
    assert "contradiction_analysis" in data
    assert "research_assessment" in data
    assert "ai_impact" in data


def test_api_financial_research_synthesize(client):
    payload = {
        "underlying": "BANKNIFTY",
        "horizon": "INTRADAY",
        "direction": "BULLISH",
    }
    resp = client.post("/api/v1/options-intelligence/financial-research/synthesize", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["underlying"] == "BANKNIFTY"
    assert data["research_status"] == "COMPLETE"
    assert len(data["supporting_evidence"]) > 0
    assert data["contradiction_analysis"]["counter_weight_score"] >= 0.0


def test_api_greeks_rejects_invalid_payload(client):
    bad_payload = {
        "spot": -1.0,
        "strike": 100.0,
        "dte_days": 1.0,
        "volatility": 0.2,
        "option_type": "CE",
    }
    resp = client.post("/api/v1/options-intelligence/greeks", json=bad_payload)
    assert resp.status_code == 422


def test_api_select_contract_rejects_bad_spot(client):
    bad_payload = {
        "underlying": "NIFTY",
        "spot_price": 0.0,
        "direction": "LONG_CALL",
    }
    resp = client.post("/api/v1/options-intelligence/select-contract", json=bad_payload)
    assert resp.status_code == 422
