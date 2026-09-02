import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from app.main import app
from app.signals.contract_resolver import (
    APPROVED_UNDERLYINGS,
    validate_underlying,
    resolve_option_contract,
    calculate_position_sizing,
    normalize_price,
)
from app.signals.strategies import STRATEGY_REGISTRY
from app.signals.strategies.base import StrategyContext
from app.signals.confluence import confluence_engine
from app.signals.fsm import signal_fsm
from app.signals.outcome_tracker import outcome_tracker


@pytest.fixture
def client():
    return TestClient(app)


class TestInstitutionalSignalCentre:

    def test_approved_universe_guard(self):
        assert validate_underlying("NIFTY") == "NIFTY"
        assert validate_underlying("BANKNIFTY") == "BANKNIFTY"
        assert validate_underlying("SENSEX") == "SENSEX"

        with pytest.raises(ValueError, match="forbidden"):
            validate_underlying("BTCUSD")

        with pytest.raises(ValueError, match="forbidden"):
            validate_underlying("RELIANCE")

    def test_dynamic_contract_resolution(self):
        contract = resolve_option_contract("NIFTY", Decimal("24835.0"), "CE", strike_offset=0)
        assert contract.underlying == "NIFTY"
        assert contract.strike == Decimal("24850.0")  # nearest 50 step
        assert contract.option_type == "CE"
        assert contract.lot_size == 75
        assert contract.exchange == "NSE"

    def test_position_sizing_calculation(self):
        # Capital 1,00,000, Risk 2% = 2,000. Entry 24850, SL 24800 (50 pts). Nifty lot 75 -> Risk/lot = 3750
        sizing = calculate_position_sizing(
            available_capital=100000.0,
            risk_percent=2.0,
            entry_price=24850.0,
            stop_loss=24800.0,
            lot_size=75,
        )
        assert sizing["risk_capital"] == 2000.0
        assert sizing["risk_per_lot"] == 3750.0
        assert sizing["lots"] == 0  # 2000 < 3750 so 0 lots allowed
        assert sizing["allowed"] is False

        # Capital 5,00,000 -> Risk 10,000 -> 10,000 / 3750 = 2 lots
        sizing_large = calculate_position_sizing(
            available_capital=500000.0,
            risk_percent=2.0,
            entry_price=24850.0,
            stop_loss=24800.0,
            lot_size=75,
        )
        assert sizing_large["lots"] == 2
        assert sizing_large["quantity"] == 150
        assert sizing_large["allowed"] is True

    def test_5_strategies_detection(self):
        assert set(STRATEGY_REGISTRY.keys()) == {"BREAKOUT", "MEAN_REVERSION", "TREND_PULLBACK", "GAMMA_SQUEEZE", "ORB"}

        # Test Breakout
        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=Decimal("24900.0"),
            indicators={
                "support_resistance": {"resistance": ["24880.0"], "support": ["24700.0"]},
                "volume_ratio": 1.6,
                "breakout_pressure": 80.0,
                "atr": 40.0,
            },
            mtf={"overall_bias": "BULLISH", "alignment_score": 85.0},
            fno={"pcr": 1.2},
            regime="TREND_UP",
        )
        breakout = STRATEGY_REGISTRY["BREAKOUT"].detect(ctx)
        assert breakout is not None
        assert breakout.direction == "LONG_CALL"
        assert breakout.target_1 > breakout.trigger
        assert breakout.risk_reward_t1 == 1.5

    def test_scanner_api_endpoint(self, client):
        res = client.get("/api/v1/signals/scanner")
        assert res.status_code == 200
        data = res.json()
        assert "scanned_underlyings" in data
        assert "NIFTY" in data["scanned_underlyings"]
        assert "BANKNIFTY" in data["scanned_underlyings"]
        assert "SENSEX" in data["scanned_underlyings"]

    def test_performance_endpoint(self, client):
        res = client.get("/api/v1/signals/performance")
        assert res.status_code == 200
        data = res.json()
        assert "total_signals" in data
        assert "win_rate_pct" in data
        assert "strategy_breakdown" in data

    def test_generate_and_execute_paper_signal(self, client):
        gen_payload = {
            "underlying": "NIFTY",
            "strategy": "BREAKOUT",
            "direction": "LONG_CALL",
            "timeframe": "5M",
            "trigger": 24900.0,
            "stop_loss": 24850.0,
            "target_1": 24975.0,
            "target_2": 25050.0,
            "confidence": 85.0,
            "execute_paper": False,
            "notify_telegram": False,
        }
        res = client.post("/api/v1/signals/generate", json=gen_payload)
        assert res.status_code == 200
        sig_data = res.json()
        sig_id = sig_data["signal"]["signal_id"]
        assert sig_data["signal"]["underlying"] == "NIFTY"

        # 1-Click execute paper
        exec_res = client.post(f"/api/v1/signals/{sig_id}/execute-paper", json={"lots": 2})
        assert exec_res.status_code == 200
        exec_data = exec_res.json()
        assert exec_data["success"] is True
        assert exec_data["lots"] == 2
        assert exec_data["quantity"] == 150
