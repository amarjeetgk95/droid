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
from app.signals.strategies import (
    STRATEGY_REGISTRY,
    SCALP_STRATEGIES,
    INTRADAY_STRATEGIES,
    REGISTRY_VERSION,
    EXPECTED_INTRADAY_STRATEGIES,
    EXPECTED_SCALP_STRATEGIES,
)
from app.signals.strategies.base import StrategyContext
from app.signals.confluence import confluence_engine
from app.signals.fsm import signal_fsm
from app.signals.outcome_tracker import outcome_tracker


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _open_market(mock_market_open):
    """Ensure market is considered open for signal centre tests."""
    pass


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
        # Versioned registry contract: renames must update this test + REGISTRY_VERSION,
        # never silently change the traded portfolio.
        assert REGISTRY_VERSION == "2026.09.17-11+1alias-p2"
        assert set(INTRADAY_STRATEGIES.keys()) == set(EXPECTED_INTRADAY_STRATEGIES) == {
            "REGIME_ADAPTIVE_TREND",
            "VOLATILITY_BREAKOUT",
            "TREND_PULLBACK",
            "ORB",
            "MEAN_REVERSION",
            "GAMMA_SQUEEZE",
        }
        assert set(SCALP_STRATEGIES.keys()) == set(EXPECTED_SCALP_STRATEGIES) == {
            "VWAP_SCALP",
            "LIQUIDITY_SWEEP_RECLAIM",
            "MICRO_MOMENTUM",
            "MOMENTUM_REACCELERATION",
            "GAMMA_SPIKE",
        }
        # P1: 11 active + BREAKOUT alias (same instance as VOLATILITY_BREAKOUT) = 12;
        # EMA_RIBBON demoted (importable, disabled, not auto-scanned).
        assert len(STRATEGY_REGISTRY) == 12
        assert set(STRATEGY_REGISTRY.keys()) >= set(INTRADAY_STRATEGIES.keys()) | set(SCALP_STRATEGIES.keys()) | {"BREAKOUT"}
        assert "EMA_RIBBON" not in STRATEGY_REGISTRY
        assert STRATEGY_REGISTRY["BREAKOUT"] is STRATEGY_REGISTRY["VOLATILITY_BREAKOUT"]
        from app.signals.strategies import STRATEGY_ENABLED, DEMOTED_STRATEGIES
        assert STRATEGY_ENABLED.get("EMA_RIBBON") is False
        assert "EMA_RIBBON" in DEMOTED_STRATEGIES

        # Test Breakout (P1: squeeze + close-beyond + vol>=1.5x, fail-closed)
        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=Decimal("24900.0"),
            timeframe="5M",
            candles=[
                {"high": 24780.0, "low": 24750.0, "open": 24755.0, "close": 24770.0},
                {"high": 24800.0, "low": 24770.0, "open": 24772.0, "close": 24790.0},
                {"high": 24810.0, "low": 24780.0, "open": 24785.0, "close": 24800.0},
                {"high": 24860.0, "low": 24850.0, "open": 24852.0, "close": 24858.0},
                {"high": 24865.0, "low": 24855.0, "open": 24857.0, "close": 24862.0},
                {"high": 24870.0, "low": 24860.0, "open": 24862.0, "close": 24868.0},
                {"high": 24910.0, "low": 24885.0, "open": 24890.0, "close": 24900.0},
            ],
            indicators={
                "support_resistance": {"resistance": ["24890.0"], "support": ["24700.0"]},
                "volume_ratio": 1.6,
                "breakout_pressure": 80.0,
                "atr": 20.0,
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

    def test_generate_and_execute_paper_signal(self, client, mock_market_feed, paper_fills_from_marks):
        gen_payload = {
            "underlying": "NIFTY",
            "strategy": "BREAKOUT",
            "direction": "LONG_CALL",
            "timeframe": "5M",
            "trigger": 24900.0,
            "current_price": 24870.0,
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

        # Fail-closed policy: the 1-click execute needs a real broker quote for
        # the resolved contract before it will fill.
        from tests.conftest import seed_chain_mark

        _opt = sig_data["signal"]["option_contract"]
        seed_chain_mark(
            _opt["broker_symbol"], 150.0,
            underlying="NIFTY", strike=float(_opt.get("strike") or 0), option_type="CE",
        )

        # 1-Click execute paper
        exec_res = client.post(f"/api/v1/signals/{sig_id}/execute-paper", json={"lots": 2})
        assert exec_res.status_code == 200
        exec_data = exec_res.json()
        assert exec_data["success"] is True
        assert exec_data["lots"] == 2
        assert exec_data["quantity"] == 150
