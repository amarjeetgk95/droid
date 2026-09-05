"""
Unit tests for Centralized Risk Engine & Target Validation
Tests:
  - Acceptance of normal structural setups within volatility envelopes.
  - Rejection of oversized stops without artificial clamping.
  - Target ceiling and R:R minimum validation.
  - Integer lot sizing and rupee risk constraints.
  - Independent Two-Clock lifecycles (Trigger TTL vs Active Holding Time Stop).
"""
import pytest
from decimal import Decimal
from app.signals.risk_engine import central_risk_engine, StrategySetup, resolve_realistic_atr


@pytest.fixture(autouse=True)
def open_market_fixture(mock_market_open):
    yield


def test_nifty_normal_5m_trade_acceptance():
    setup = StrategySetup(
        strategy_name="BREAKOUT",
        underlying="NIFTY",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24900.0"),
        entry_trigger=Decimal("24910.0"),
        raw_structural_stop=Decimal("24888.0"),  # 22 pts risk
        atr_5m=Decimal("20.0"),
    )
    decision = central_risk_engine.evaluate(setup, available_capital=100000.0, risk_per_trade_pct=1.0)
    
    assert decision.accepted is True
    assert decision.risk_points == 24.0  # 20 * 1.2 atr multiplier
    assert decision.stop_loss == Decimal("24886.0")
    assert decision.target_1 == Decimal("24946.0")  # +36 pts (1.5R)
    assert decision.reward_t1_points == 36.0
    assert decision.risk_reward_t1 >= 1.35
    assert decision.trigger_ttl_seconds == 600
    assert decision.active_time_stop_seconds == 4500
    assert decision.lots >= 1
    assert decision.quantity % decision.lot_size == 0
    assert decision.max_rupee_loss <= 1000.0  # 1% of 1,00,000


def test_rejection_of_oversized_structural_stop():
    """
    CRITICAL INVARIANT: The engine must NOT clamp an invalid 154 pt stop inward to 35 pts.
    It MUST reject the trade outright.
    """
    setup = StrategySetup(
        strategy_name="BREAKOUT",
        underlying="NIFTY",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24870.0"),
        entry_trigger=Decimal("24900.0"),
        raw_structural_stop=Decimal("24746.0"),  # 154 pts risk!
        atr_5m=Decimal("20.0"),
    )
    decision = central_risk_engine.evaluate(setup)
    
    assert decision.accepted is False
    assert "STRUCTURAL_RISK_EXCEEDS_ENVELOPE" in decision.rejection_reason


def test_banknifty_5m_trade_bounds():
    setup = StrategySetup(
        strategy_name="TREND_PULLBACK",
        underlying="BANKNIFTY",
        direction="LONG_PUT",
        timeframe="5M",
        spot_price=Decimal("52000.0"),
        entry_trigger=Decimal("51980.0"),
        raw_structural_stop=Decimal("52050.0"),  # 70 pts risk
        atr_5m=Decimal("55.0"),
    )
    decision = central_risk_engine.evaluate(setup, available_capital=200000.0, risk_per_trade_pct=1.0)
    
    assert decision.accepted is True
    assert decision.risk_points == 70.0
    assert decision.stop_loss == Decimal("52050.0")
    assert decision.target_1 == Decimal("51875.0")  # -105 pts (1.5R)
    assert decision.trigger_ttl_seconds == 600
    assert decision.active_time_stop_seconds == 4500
    assert decision.quantity % 30 == 0  # BANKNIFTY lot size 30


def test_rejection_when_capital_insufficient_for_1_lot():
    setup = StrategySetup(
        strategy_name="BREAKOUT",
        underlying="NIFTY",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24900.0"),
        entry_trigger=Decimal("24910.0"),
        raw_structural_stop=Decimal("24880.0"),  # 30 pts risk -> ~₹1125 risk per lot
        atr_5m=Decimal("20.0"),
    )
    # Available capital ₹10,000 at 1% risk = ₹100 max loss budget (insufficient for 1 lot)
    decision = central_risk_engine.evaluate(setup, available_capital=10000.0, risk_per_trade_pct=1.0)
    
    assert decision.accepted is False
    assert "INSUFFICIENT_CAPITAL_FOR_1_LOT" in decision.rejection_reason


def test_expiry_day_halves_holding_time_stop():
    setup = StrategySetup(
        strategy_name="VWAP_SCALP",
        underlying="NIFTY",
        direction="LONG_CALL",
        timeframe="1M",
        is_scalp=True,
        spot_price=Decimal("24900.0"),
        entry_trigger=Decimal("24905.0"),
        raw_structural_stop=Decimal("24893.0"),  # 12 pts risk
        atr_5m=Decimal("15.0"),
    )
    normal_dec = central_risk_engine.evaluate(setup, is_expiry_day=False)
    expiry_dec = central_risk_engine.evaluate(setup, is_expiry_day=True)
    
    assert normal_dec.active_time_stop_seconds == 900   # 15 mins
    assert expiry_dec.active_time_stop_seconds == 450   # 7.5 mins (halved to prevent theta decay)


def test_resolve_realistic_atr():
    nifty_atr = resolve_realistic_atr("NIFTY", Decimal("25000.0"), indicators={})
    assert Decimal("14.0") <= nifty_atr <= Decimal("32.0")

    banknifty_atr = resolve_realistic_atr("BANKNIFTY", Decimal("52000.0"), indicators={})
    assert Decimal("35.0") <= banknifty_atr <= Decimal("90.0")

    # Extreme raw ATR must be clamped
    clamped_atr = resolve_realistic_atr("NIFTY", Decimal("25000.0"), indicators={"atr": 150.0})
    assert clamped_atr == Decimal("32.0")
