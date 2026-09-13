"""
API endpoint integration tests for Swing Trading router (v5.0).
"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.swing.models import SwingSetup, SetupScoreBreakdown
from app.swing.persistence import save_swing_state


@pytest.mark.asyncio
async def test_swing_api_universe():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/swing/universe")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert body["data"]["total_count"] >= 50
        assert "Banking" in body["data"]["sectors"]
        assert "IT" in body["data"]["sectors"]


@pytest.mark.asyncio
async def test_swing_api_setups_and_positions_lifecycle():
    # Setup test fixture in state
    test_setup = SwingSetup(
        setup_id="test-setup-999",
        symbol="RELIANCE",
        sector="Energy",
        strategy="VCP_BREAKOUT",
        score=SetupScoreBreakdown(total=88.0),
        entry_zone_min=2990.0,
        entry_zone_max=3020.0,
        trigger_price=3000.0,
        max_chase_price=3030.0,
        stop_price=2940.0,
        structural_stop=2940.0,
        atr_floor=2950.0,
        target_1=3090.0,
        target_2=3180.0,
        risk_per_share=60.0,
        risk_pct=2.0,
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        signal_state="READY",
    )
    save_swing_state(setups=[test_setup], open_positions=[], closed_positions=[])

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Fetch setups
            resp_setups = await client.get("/api/v1/swing/setups?min_score=80")
            assert resp_setups.status_code == 200
            setups_data = resp_setups.json()["data"]
            assert setups_data["count"] >= 1
            assert any(s["symbol"] == "RELIANCE" for s in setups_data["setups"])

            # 2. Enter position
            enter_payload = {"setup_id": "test-setup-999", "fill_price": 3000.0, "quantity": 10}
            resp_enter = await client.post("/api/v1/swing/positions/enter", json=enter_payload)
            assert resp_enter.status_code == 200
            pos_data = resp_enter.json()["data"]
            pos_id = pos_data["position_id"]
            assert pos_data["symbol"] == "RELIANCE"
            assert pos_data["status"] == "OPEN"

            # 3. Check open positions
            resp_pos = await client.get("/api/v1/swing/positions")
            assert resp_pos.status_code == 200
            open_list = resp_pos.json()["data"]["open_positions"]
            assert len(open_list) == 1
            assert open_list[0]["position_id"] == pos_id

            # 4. Generate AI Copilot thesis prompt
            resp_thesis = await client.post("/api/v1/swing/thesis", json={"setup_id": "test-setup-999"})
            assert resp_thesis.status_code == 200
            thesis_data = resp_thesis.json()["data"]
            assert "structured_prompt" in thesis_data
            assert "RELIANCE" in thesis_data["structured_prompt"]

            # 5. Exit position
            exit_payload = {"position_id": pos_id, "exit_price": 3090.0, "exit_reason": "TARGET_1_HIT"}
            resp_exit = await client.post("/api/v1/swing/positions/exit", json=exit_payload)
            assert resp_exit.status_code == 200
            closed_data = resp_exit.json()["data"]
            assert closed_data["status"] == "CLOSED"
            assert closed_data["r_multiple"] == 1.5
    finally:
        # Clean up test state so production state file remains completely pristine
        save_swing_state(setups=[], open_positions=[], closed_positions=[])
