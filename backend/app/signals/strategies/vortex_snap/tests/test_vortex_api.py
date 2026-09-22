"""
Unit and integration tests for VORTEX-SNAP API router endpoints (§43–§47).
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestVortexApi:
    def test_status_endpoint(self, client):
        resp = client.get("/api/v1/strategies/vortex-snap/status")
        assert resp.status_code == 200
        payload = resp.json()
        assert "data" in payload
        data = payload["data"]
        assert data["strategy"] == "VORTEX_SNAP"
        assert data["status"] == "ONLINE"
        assert "session" in data
        assert "ml_validator" in data
        assert "config" in data

    def test_microstructure_hud_endpoint(self, client, monkeypatch):
        # The live HUD path is strict by default and refuses anything that fails
        # provenance. This test verifies the *payload contract*, so it opts into
        # the synthetic fixture explicitly via the documented local-dev override
        # rather than depending on a real 1m dataset being present.
        monkeypatch.setenv("VORTEX_SNAP_REQUIRE_REAL_DATA", "false")
        resp = client.get("/api/v1/strategies/vortex-snap/microstructure/SENSEX?bars=60")
        assert resp.status_code == 200
        payload = resp.json()
        assert "data" in payload
        data = payload["data"]
        assert data["symbol"] == "SENSEX"
        assert "data_source" in data
        src = data["data_source"]
        assert src["type"] in ("parquet", "synthetic")
        # is_simulated covers provenance failure, not merely synthetic generation:
        # a generated series persisted as parquet must not advertise itself as real.
        assert src["is_simulated"] == (src["type"] == "synthetic" or not src["provenance_verified"])
        assert "compression" in data
        assert "directional_pressure" in data
        assert "translation_ratio" in data
        assert "absorption" in data
        assert "liquidity_vacuum" in data
        assert "snap_energy" in data
        assert "market_regime" in data
        assert "structural_levels" in data
        assert "fsm_state" in data

    def test_backtest_endpoint(self, client):
        req_body = {
            "symbol": "SENSEX",
            "ablation_stage": "STAGE_A",
            "slippage_stress": 1.0,
            "execution_lag": 0,
            "initial_capital": 1000000.0,
            "max_bars": 300,
        }
        resp = client.post("/api/v1/strategies/vortex-snap/backtest", json=req_body)
        assert resp.status_code == 200
        payload = resp.json()
        assert "data" in payload
        data = payload["data"]
        assert data["symbol"] == "SENSEX"
        assert "data_source" in data
        assert "metrics" in data
        assert "equity_curve" in data
        assert "exit_breakdown" in data
        assert "recent_trades" in data
        metrics = data["metrics"]
        assert "win_rate_pct" in metrics
        assert "annualized_sharpe" in metrics

    def test_ablation_matrix_endpoint(self, client):
        resp = client.get("/api/v1/strategies/vortex-snap/ablation?symbol=SENSEX&sample_bars=400")
        assert resp.status_code == 200
        payload = resp.json()
        assert "data" in payload
        data = payload["data"]
        assert "data_source" in data
        assert "stages" in data
        assert len(data["stages"]) == 9  # 9 stages: A through I
        assert "primary_hypothesis_supported" in data
        assert "F" in [r["stage"] for r in data["stages"]]

    def test_strict_real_data_mode_rejects_synthetic_fallback(self, client, monkeypatch):
        import app.api.vortex as vortex_api
        from app.signals.strategies.vortex_snap.config import VortexSnapConfig
        strict_cfg = VortexSnapConfig()
        strict_cfg.data.require_real_data = True
        monkeypatch.setattr(vortex_api, "_config", strict_cfg)
        def boom_load(*a, **k):
            raise FileNotFoundError("forced missing parquet for test")
        monkeypatch.setattr(vortex_api._data_loader, "load_parquet", boom_load)
        resp = client.get("/api/v1/strategies/vortex-snap/microstructure/NIFTY?bars=60")
        assert resp.status_code == 503
        detail = resp.json().get("detail", "")
        assert "Real market data required" in detail

    def test_experiments_list_endpoint(self, client):
        resp = client.get("/api/v1/strategies/vortex-snap/experiments")
        assert resp.status_code == 200
        payload = resp.json()
        assert "data" in payload
        assert isinstance(payload["data"], list)
