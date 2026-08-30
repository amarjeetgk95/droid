from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestBacktestEndpoints:
    def test_get_presets_api(self):
        r = client.get("/api/v1/backtest/presets")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) >= 3

    def test_run_backtest_api(self):
        payload = {
            "strategy_id": "short_straddle",
            "underlying": "NIFTY",
            "initial_capital": 500000.0,
            "num_days": 10,
            "stop_loss_pct": 25.0,
            "target_pct": 50.0,
            "slippage_pct": 0.001,
            "include_costs": True,
        }
        r = client.post("/api/v1/backtest/run", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["total_trades"] == 10
        assert "sharpe_ratio" in body["data"]
        assert "equity_curve" in body["data"]

    def test_get_history_api(self):
        r = client.get("/api/v1/backtest/history")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) >= 1
