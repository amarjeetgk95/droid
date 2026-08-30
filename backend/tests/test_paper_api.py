from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestPaperTradingEndpoints:
    def test_get_portfolio_api(self):
        r = client.get("/api/v1/paper/portfolio")
        assert r.status_code == 200
        body = r.json()
        assert "virtual_capital" in body["data"]
        assert "available_margin" in body["data"]

    def test_place_order_api(self):
        payload = {
            "symbol": "BANKNIFTY52000CE",
            "underlying": "BANKNIFTY",
            "side": "BUY",
            "order_type": "MARKET",
            "product": "INTRADAY",
            "quantity": 25,
            "price": 280.0,
        }
        r = client.post("/api/v1/paper/order", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["status"] == "FILLED"

    def test_get_positions_and_orders_api(self):
        r_pos = client.get("/api/v1/paper/positions")
        assert r_pos.status_code == 200
        assert isinstance(r_pos.json()["data"], list)

        r_ord = client.get("/api/v1/paper/orders")
        assert r_ord.status_code == 200
        assert isinstance(r_ord.json()["data"], list)

    def test_square_off_all_and_reset_api(self):
        r_sq = client.post("/api/v1/paper/square-off-all")
        assert r_sq.status_code == 200

        r_reset = client.post("/api/v1/paper/reset")
        assert r_reset.status_code == 200
        assert r_reset.json()["data"]["virtual_capital"] == 1000000.0
