from fastapi.testclient import TestClient
from app.main import app

def test_crypto_api_lifecycle():
    client = TestClient(app)
    
    # 1. Test GET /api/v1/crypto/scalp-signals/active
    r = client.get("/api/v1/crypto/scalp-signals/active")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert "signals" in data
    print("[OK] GET /active OK")

    # 2. Test POST /api/v1/crypto/scalp-signals/generate (Validation Rejection)
    # Stop too wide (> 600 pt max envelope for BTC)
    bad_req = {
        "symbol": "BTCUSDT",
        "strategy": "BREAKOUT_MOMENTUM",
        "direction": "LONG",
        "timeframe": "1m",
        "spot_price": 65000.0,
        "trigger": 65100.0,
        "stop_loss": 63500.0, # 1600 pt stop > max allowable 600
        "target_1": 68300.0,  # 2.0R
        "target_2": 71500.0,  # 4.0R
        "confidence": 80.0
    }
    r_bad = client.post("/api/v1/crypto/scalp-signals/generate", json=bad_req)
    assert r_bad.status_code == 400, f"Expected 400 rejection for oversized stop, got {r_bad.status_code}"
    assert "Risk envelope rejection" in r_bad.json()["detail"]
    print("[OK] POST /generate (Oversized stop rejected without clamping) OK")

    # 3. Test POST /api/v1/crypto/scalp-signals/generate (Valid Setup)
    good_req = {
        "symbol": "BTCUSDT",
        "strategy": "EMA_PULLBACK",
        "direction": "LONG",
        "timeframe": "1m",
        "spot_price": 65000.0,
        "trigger": 65050.0,
        "stop_loss": 64800.0, # 250 pt stop (within 100-600)
        "target_1": 65425.0, # 1.5R (375 pt reward)
        "target_2": 65675.0, # 2.5R (625 pt reward)
        "confidence": 82.0,
        "rationale": ["Valid test breakout setup on BTC 1M"]
    }
    r_good = client.post("/api/v1/crypto/scalp-signals/generate", json=good_req)
    assert r_good.status_code == 200, f"Expected 200, got {r_good.status_code}: {r_good.text}"
    gen_data = r_good.json()
    assert gen_data["success"] is True
    signal_id = gen_data["signal_id"]
    print(f"[OK] POST /generate OK -> Signal ID: {signal_id}")

    # 4. Test GET /api/v1/crypto/scalp-signals/active has the newly created signal
    r_active = client.get("/api/v1/crypto/scalp-signals/active")
    assert r_active.status_code == 200
    active_signals = r_active.json()["signals"]
    found = [s for s in active_signals if s["signal_id"] == signal_id]
    assert len(found) == 1, f"Signal {signal_id} should be listed in active signals"
    assert found[0]["fsm_state"] == "ARMED"
    print(f"[OK] GET /active contains signal with FSM state {found[0]['fsm_state']}")

    # 5. Test GET /api/v1/crypto/scalp-signals/deep-dive/{signal_id}
    r_deep = client.get(f"/api/v1/crypto/scalp-signals/deep-dive/{signal_id}")
    assert r_deep.status_code == 200, f"Expected 200, got {r_deep.status_code}"
    deep_data = r_deep.json()
    assert deep_data["signal"]["signal_id"] == signal_id
    assert len(deep_data["fsm_history"]) >= 1
    print(f"[OK] GET /deep-dive/{signal_id} OK (Audit history items: {len(deep_data['fsm_history'])})")

    # 6. Test DELETE /api/v1/crypto/scalp-signals/{signal_id}
    r_del = client.delete(f"/api/v1/crypto/scalp-signals/{signal_id}")
    assert r_del.status_code == 200, f"Expected 200, got {r_del.status_code}"
    del_data = r_del.json()
    assert del_data["status"] == "success"
    print(f"[OK] DELETE /{signal_id} OK")

    # 7. Verify removed from active signals
    r_after = client.get("/api/v1/crypto/scalp-signals/active")
    found_after = [s for s in r_after.json()["signals"] if s["signal_id"] == signal_id]
    assert len(found_after) == 0
    print("[OK] Signal successfully purged from active FSM")

if __name__ == "__main__":
    test_crypto_api_lifecycle()
    print("\n==========================================")
    print("ALL CRYPTO FASTAPI ENDPOINTS VERIFIED 100%")
    print("==========================================")
