"""
Unit tests for Swing Risk Engine & Portfolio Guard (v5.0 §13, §14, §15, §16, §19).
"""
import pytest
from app.swing.models import SwingSetup, SwingPosition, SetupScoreBreakdown
from app.swing.risk_engine import compute_swing_risk_levels
from app.swing.portfolio_risk import PortfolioRiskManager
from app.swing.lifecycle import create_position_from_setup, update_position_on_candle


def test_structural_stop_with_atr_floor():
    # Case 1: Structural stop is 10 pts below trigger, but 1.2 x ATR(15) = 18 pts.
    # ATR floor must enforce at least 18 pts stop distance.
    res1 = compute_swing_risk_levels(
        trigger_price=1000.0,
        structural_stop_price=990.0,
        daily_atr=15.0,
        portfolio_equity=1_000_000.0,
        atr_multiplier=1.2,
    )
    # Stop distance should be max(10, 18) = 18
    assert res1.effective_stop == 982.0
    assert res1.risk_per_share == 18.0
    # Target 1 = 1000 + 1.5 * 18 = 1027.0
    assert res1.target_1 == 1027.0
    # Target 2 = 1000 + 3.0 * 18 = 1054.0
    assert res1.target_2 == 1054.0
    # Max chase = 1000 * 1.01 = 1010.0
    assert res1.max_chase_price == 1010.0

    # Case 2: Structural stop is 30 pts below trigger, and 1.2 x ATR(15) = 18 pts.
    # Structural stop must be respected since it is wider (30 > 18).
    res2 = compute_swing_risk_levels(
        trigger_price=1000.0,
        structural_stop_price=970.0,
        daily_atr=15.0,
        portfolio_equity=1_000_000.0,
    )
    assert res2.effective_stop == 970.0
    assert res2.risk_per_share == 30.0


def test_portfolio_risk_concentration_guard():
    manager = PortfolioRiskManager(
        total_equity=1_000_000.0,
        max_heat_pct=5.0,
        max_positions_per_sector=2,
        max_positions_count=6,
    )

    # Mock 2 active Banking positions
    pos1 = SwingPosition(
        setup_id="s1", symbol="HDFCBANK", sector="Banking", strategy="VCP_BREAKOUT",
        entry_price=1600.0, current_price=1620.0, quantity=50, initial_stop=1570.0,
        current_stop=1570.0, target_1=1645.0, target_2=1690.0,
    )
    pos2 = SwingPosition(
        setup_id="s2", symbol="ICICIBANK", sector="Banking", strategy="TREND_PULLBACK_20EMA",
        entry_price=1100.0, current_price=1110.0, quantity=100, initial_stop=1080.0,
        current_stop=1080.0, target_1=1130.0, target_2=1160.0,
    )

    open_positions = [pos1, pos2]

    # Candidate 3 is also Banking (e.g. AXISBANK) -> MUST BE BLOCKED
    candidate_bank = SwingSetup(
        setup_id="s3", symbol="AXISBANK", sector="Banking", strategy="STAGE2_BREAKOUT",
        score=SetupScoreBreakdown(total=80.0),
        entry_zone_min=1150.0, entry_zone_max=1165.0, trigger_price=1155.0, max_chase_price=1166.5,
        stop_price=1130.0, structural_stop=1130.0, atr_floor=1135.0, target_1=1192.5, target_2=1230.0,
        risk_per_share=25.0, risk_pct=2.16, risk_reward_t1=1.5, risk_reward_t2=3.0,
    )

    allowed, reason = manager.validate_candidate(candidate_bank, open_positions)
    assert allowed is False
    assert "Sector concentration limit reached" in reason

    # Candidate 4 is Auto (e.g. TATAMOTORS) -> MUST BE ALLOWED
    candidate_auto = candidate_bank.model_copy(update={"symbol": "TATAMOTORS", "sector": "Auto"})
    allowed_auto, reason_auto = manager.validate_candidate(candidate_auto, open_positions)
    assert allowed_auto is True


def test_position_trailing_stop_lifecycle():
    setup = SwingSetup(
        setup_id="s1", symbol="INFY", sector="IT", strategy="VCP_BREAKOUT",
        score=SetupScoreBreakdown(total=85.0),
        entry_zone_min=1800.0, entry_zone_max=1820.0, trigger_price=1810.0, max_chase_price=1828.1,
        stop_price=1770.0, structural_stop=1770.0, atr_floor=1780.0, target_1=1870.0, target_2=1930.0,
        risk_per_share=40.0, risk_pct=2.2, risk_reward_t1=1.5, risk_reward_t2=3.0,
    )

    # Enter position at 1810 with 50 shares
    pos = create_position_from_setup(setup, fill_price=1810.0, quantity=50)
    assert pos.status == "OPEN"
    assert pos.current_stop == 1770.0

    # Day 1: Price rises to 1840 (Gain 30 pts, R-multiple = 30/40 = 0.75R)
    pos = update_position_on_candle(pos, candle_close=1840.0, candle_low=1805.0, candle_high=1845.0)
    assert pos.current_stop == 1770.0 # Stop unchanged

    # Day 2: Price hits Target 1 (1870, R-multiple = 60/40 = 1.5R) -> Stop moves to Break-Even!
    pos = update_position_on_candle(pos, candle_close=1875.0, candle_low=1835.0, candle_high=1880.0)
    assert pos.current_stop == 1810.0 # Trailed to entry price (Break-Even)
    assert pos.trailing_method == "BREAK_EVEN"

    # Day 3: Price expands to 1900 (Gain 90 pts, R-multiple = 2.25R) with 20 EMA at 1850 -> Stop trails to 1850!
    pos = update_position_on_candle(
        pos, candle_close=1900.0, candle_low=1865.0, candle_high=1905.0,
        current_ema20=1850.0, recent_3d_low=1835.0,
    )
    assert pos.current_stop == 1850.0 # Trailed along 20 EMA
    assert pos.trailing_method == "EMA_20"
