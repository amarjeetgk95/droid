"""
API endpoint integration tests for Swing Options Trading router (v6.0 Options Overhaul).
"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.swing.models import SwingSetup, SetupScoreBreakdown, TradeValidity
from app.swing.persistence import save_swing_state


@pytest.mark.asyncio
async def test_swing_api_universe():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/swing/universe")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert body["data"]["total_count"] >= 3
        symbols = [inst["symbol"] for inst in body["data"]["instruments"]]
        assert "NIFTY" in symbols
        assert "BANKNIFTY" in symbols
        assert "SENSEX" in symbols


@pytest.mark.asyncio
async def test_swing_api_setups_and_positions_lifecycle():
    # Setup test fixture in state
    test_setup = SwingSetup(
        setup_id="test-setup-999",
        underlying="NIFTY",
        direction="LONG_CALL",
        option_type="CE",
        strategy="TREND_BREAKOUT_CE",
        strike=25000.0,
        expiry_date="2026-09-26",
        contract_symbol="NSE:NIFTY26SEP25000CE",
        lot_size=75,
        spot_price=25000.0,
        spot_trigger=25050.0,
        spot_stop=24800.0,
        entry_premium=200.0,
        stop_premium=160.0,
        target_premium_1=260.0,
        target_premium_2=320.0,
        premium_risk_per_lot=3000.0,
        greeks={"delta": 0.55, "theta_day": -12.0, "vega": 15.0},
        score=SetupScoreBreakdown(total=88.0),
        trade_validity=TradeValidity(
            underlying_valid=True,
            option_valid=True,
            portfolio_valid=True,
            execution_valid=True,
            overall_valid=True,
        ),
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
            assert any(s["underlying"] == "NIFTY" for s in setups_data["setups"])

            # 2. Enter position
            enter_payload = {"setup_id": "test-setup-999", "fill_premium": 200.0, "num_lots": 1}
            resp_enter = await client.post("/api/v1/swing/positions/enter", json=enter_payload)
            assert resp_enter.status_code == 200
            pos_data = resp_enter.json()["data"]
            pos_id = pos_data["position_id"]
            assert pos_data["underlying"] == "NIFTY"
            assert pos_data["contract_symbol"] == "NSE:NIFTY26SEP25000CE"
            assert pos_data["status"] == "OPEN"

            # 3. Check open positions & portfolio risk
            resp_pos = await client.get("/api/v1/swing/positions")
            assert resp_pos.status_code == 200
            open_list = resp_pos.json()["data"]["open_positions"]
            assert len(open_list) == 1
            assert open_list[0]["position_id"] == pos_id
            assert "portfolio_risk" in resp_pos.json()["data"]

            # 4. Generate AI Copilot thesis prompt
            resp_thesis = await client.post("/api/v1/swing/thesis", json={"setup_id": "test-setup-999"})
            assert resp_thesis.status_code == 200
            thesis_data = resp_thesis.json()["data"]
            assert "structured_prompt" in thesis_data
            assert "NIFTY" in thesis_data["structured_prompt"]

            # 5. Exit position
            exit_payload = {"position_id": pos_id, "exit_premium": 260.0, "exit_reason": "TARGET_1"}
            resp_exit = await client.post("/api/v1/swing/positions/exit", json=exit_payload)
            assert resp_exit.status_code == 200
            closed_data = resp_exit.json()["data"]
            assert closed_data["status"] == "CLOSED"
            assert closed_data["r_multiple"] == 1.5
    finally:
        # Clean up test state so state file remains pristine
        save_swing_state(setups=[], open_positions=[], closed_positions=[])

