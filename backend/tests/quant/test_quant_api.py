"""API Tests for Quantitative Engine Endpoints (Tier 4).

Tests:
- GET /api/v1/quant/datasets
- POST /api/v1/quant/options-simulate
- POST /api/v1/quant/g0-baseline
- POST /api/v1/quant/analogues
"""

import pytest
from fastapi.testclient import TestClient

import app.api.quant as quant_api
from app.main import app
from app.quant.data.dataset_manager import DatasetManager
from scripts.fetch_fyers_history import generate_synthetic_history


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def provisioned_dataset(tmp_path, monkeypatch):
    """Provision a SENSEX 1m dataset for the endpoints under test.

    These endpoints require a 1m dataset and return 404 without one. They
    previously passed only because a synthetic fixture happened to sit in
    ``data/raw/sensex`` — generated data inside the real-data tree. Each test now
    provisions its own dataset in a temp root and points the API at it, so the
    suite never depends on undisclosed data on disk and never writes into
    ``data/raw``.
    """
    # 60 sessions: enough that /analogues resampled to 15m has >= 1001 bars for the
    # hard-coded bar_index of 1000 in that test.
    frame = generate_synthetic_history(symbol="BSE:SENSEX-INDEX", days=60, base_price=80000.0)
    DatasetManager(base_dir=tmp_path).save_dataset(
        frame, instrument="sensex", timeframe="1m", source="synthetic_fixture"
    )
    monkeypatch.setattr(quant_api, "DatasetManager", lambda *args, **kwargs: DatasetManager(tmp_path))
    return tmp_path


class TestQuantAPI:

    def test_list_datasets(self, client):
        response = client.get("/api/v1/quant/datasets")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "meta" in data
        assert data["meta"]["provider"] == "droid_quant_engine"

        datasets = data["data"]
        assert isinstance(datasets, list)
        symbols = [d["symbol"] for d in datasets]
        assert "SENSEX" in symbols

    def test_options_simulate(self, client):
        payload = {
            "symbol": "SENSEX",
            "direction": 1,
            "spot_entry": 80000.0,
            "spot_exit": 80400.0,
            "bars_held": 4,
            "days_to_expiry": 3.0,
        }
        response = client.post("/api/v1/quant/options-simulate", json=payload)
        assert response.status_code == 200
        body = response.json()
        trade = body["data"]

        assert trade["strike"] == 80000.0
        assert trade["option_type"] == "CE"
        assert trade["options_gross_pnl_pts"] > 0.0
        assert trade["total_statutory_cost_rupees"] > 0.0
        assert trade["delta_at_entry"] > 0.40

    def test_options_spread_simulate(self, client):
        payload = {
            "symbol": "SENSEX",
            "direction": "LONG",
            "spot_entry": 80000.0,
            "spot_exit": 80300.0,
            "holding_bars": 4,
            "bar_minutes": 15,
            "iv": 0.14,
            "dte_entry": 4.0,
            "strike_width": 300.0,
            "lot_size": 10,
            "contracts": 1,
            "stress_multiplier": 1.0,
        }
        response = client.post("/api/v1/quant/options-spread-simulate", json=payload)
        assert response.status_code == 200
        body = response.json()
        data = body["data"]

        assert data["spread_name"] == "Bull Call Spread"
        assert data["net_entry"] > 0.0
        assert data["net_entry"] < data["legs"]["long_leg"]["premium_entry"]
        assert data["theta_decay_reduction_pct"] >= 40.0
        assert data["costs"]["brokerage"] == 80.0
        assert data["costs"]["total_cost"] > 80.0

    def test_g0_baseline_run(self, client):
        payload = {
            "symbol": "sensex",
            "timeframe": "15m",
            "strategy_key": "S1",
            "trend_aligned": True,
            "k_tp": 2.0,
            "k_sl": 1.0,
        }
        response = client.post("/api/v1/quant/g0-baseline", json=payload)
        assert response.status_code == 200
        res = response.json()["data"]

        assert "metrics" in res
        assert "sample_trades" in res
        assert "gate_g0_verdict" in res["metrics"]
        assert res["metrics"]["total_trades"] > 0

    def test_historical_analogues_query(self, client):
        payload = {
            "symbol": "sensex",
            "timeframe": "15m",
            "bar_index": 1000,
            "direction": 1,
            "k_neighbors": 5,
        }
        response = client.post("/api/v1/quant/analogues", json=payload)
        assert response.status_code == 200
        data = response.json()["data"]

        assert "analogue_context" in data
        assert "top_neighbors" in data

    def test_strategy_matrix(self, client):
        payload = {
            "symbol": "sensex",
            "timeframe": "15m",
            "k_tp": 2.5,
            "k_sl": 1.0,
            "t_max_bars": 12,
            "trend_aligned": True,
            "stress_multiplier": 1.0,
        }
        response = client.post("/api/v1/quant/strategy-matrix", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        data = body["data"]

        # Provenance validation
        assert "provenance" in data
        prov = data["provenance"]
        assert prov["source_symbol"] == "SENSEX"
        assert prov["source_timeframe"] == "1m"
        assert prov["analysis_timeframe"] == "15m"
        assert prov["source_bars"] > 0
        assert prov["analysis_bars"] > 0
        assert "data_quality_score" in prov

        # Matrix validation
        assert "matrix" in data
        matrix = data["matrix"]
        assert len(matrix) == 12

        expected_keys = ["S1", "S2", "S3", "S4", "S5", "S6-A", "S6-F", "S7", "S8", "S4+S8", "S1+S3", "ALL"]
        actual_keys = [row["strategy_key"] for row in matrix]
        assert actual_keys == expected_keys

        for row in matrix:
            assert "strategy_key" in row
            assert "strategy_name" in row
            assert "total_trades" in row
            assert isinstance(row["total_trades"], int)
            assert "win_rate" in row
            assert "gross_expectancy_pct" in row
            assert "net_expectancy_pct" in row
            assert "profit_factor" in row
            assert "max_drawdown_pct" in row
            assert "annualized_sharpe" in row
            assert "deflated_sharpe_ratio" in row
            assert "gate_g0_verdict" in row
            assert row["gate_g0_verdict"] in ("PASSED", "FAILED", "INCONCLUSIVE")
            assert "verdict_reasons" in row
            assert isinstance(row["verdict_reasons"], list)

    def test_s6_trials_api(self, client):
        response = client.get("/api/v1/quant/s6/trials")
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        data = body["data"]
        assert "trial_count" in data
        assert "trials" in data
        assert isinstance(data["trials"], list)

    def test_s6_run_api(self, client):
        response = client.post("/api/v1/quant/s6/run", json={"instrument": "SENSEX", "track": "S6A_T1"})
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        data = body["data"]
        assert "provenance" in data
        assert data["provenance"]["instrument"] == "SENSEX"
        assert "matrix" in data
        assert "S6A_T1" in data["matrix"]
        track_data = data["matrix"]["S6A_T1"]
        assert "compression_episodes" in track_data
        assert "raw_breakouts" in track_data
        assert "gate_g0_verdict" in track_data

    def test_g0_baseline_confluence(self, client):
        payload = {
            "symbol": "sensex",
            "timeframe": "15m",
            "strategy_key": "S4+S8",
            "trend_aligned": True,
            "k_tp": 2.0,
            "k_sl": 1.0,
        }
        response = client.post("/api/v1/quant/g0-baseline", json=payload)
        assert response.status_code == 200
        res = response.json()["data"]
        assert res["metrics"]["gate_g0_verdict"] in ("PASSED", "FAILED", "INCONCLUSIVE")
        for t in res["sample_trades"]:
            assert t["strategy_id"].startswith("CONF_S4_S8")

    def test_g0_baseline_s8(self, client):
        payload = {
            "symbol": "sensex",
            "timeframe": "15m",
            "strategy_key": "S8",
            "trend_aligned": True,
            "k_tp": 2.0,
            "k_sl": 1.0,
        }
        response = client.post("/api/v1/quant/g0-baseline", json=payload)
        assert response.status_code == 200
        res = response.json()["data"]
        assert "metrics" in res
        assert res["metrics"]["gate_g0_verdict"] in ("PASSED", "FAILED", "INCONCLUSIVE")
        # All S8 trades must carry the S8 strategy id prefix.
        for t in res["sample_trades"]:
            assert t["strategy_id"].startswith("S8_IV")

    def test_g2_robustness_api(self, client):
        payload = {
            "symbol": "sensex",
            "timeframe": "15m",
            "strategy_key": "S1",
            "k_tp": 2.0,
            "k_sl": 1.0,
        }
        response = client.post("/api/v1/quant/g2-robustness", json=payload)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["strategy_key"] == "S1"
        assert data["gate_g2_verdict"] in ("PASSED", "FAILED", "INCONCLUSIVE")
        assert len(data["stress_curve"]) == 4
        assert [p["stress_multiplier"] for p in data["stress_curve"]] == [1.0, 1.25, 1.5, 2.0]
        assert data["sensitivity_total"] == 3
        assert "verdict_reasons" in data

    def test_strategy_matrix_export_api(self, client):
        payload = {
            "symbol": "sensex",
            "timeframe": "15m",
            "k_tp": 2.5,
            "k_sl": 1.0,
            "t_max_bars": 12,
            "trend_aligned": True,
            "stress_multiplier": 1.0,
        }
        response = client.post("/api/v1/quant/strategy-matrix-export", json=payload)
        assert response.status_code == 200
        data = response.json()["data"]
        assert "csv" in data
        assert "S8" in data["csv"]
        assert data["csv"].splitlines()[0].startswith("strategy_key,")
        assert data["filename"].endswith(".csv")

    def test_g0_trades_export_api(self, client):
        payload = {
            "symbol": "sensex",
            "timeframe": "15m",
            "strategy_key": "S1",
            "trend_aligned": True,
        }
        response = client.post("/api/v1/quant/g0-trades-export", json=payload)
        assert response.status_code == 200
        data = response.json()["data"]
        assert "csv" in data
        assert "metrics" in data
        assert data["csv"].splitlines()[0].startswith("entry_time,")

