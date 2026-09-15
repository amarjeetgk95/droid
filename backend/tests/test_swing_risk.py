"""
Unit tests for Swing Options Risk Engine & Portfolio Guard (v6.0 Options Overhaul).
"""
import pytest
from app.swing.models import SwingSetup, SwingPosition, SetupScoreBreakdown, TradeValidity
from app.swing.risk_engine import compute_swing_risk_levels, compute_swing_options_risk
from app.swing.portfolio_risk import PortfolioRiskManager
from app.swing.lifecycle import create_position_from_setup, update_position, close_position
from app.signals.portfolio_greeks import portfolio_greeks_ledger


def test_spot_structural_stop_with_atr_floor():
    # Structural stop is 10 pts below trigger, but 1.2 x ATR(15) = 18 pts.
    res1 = compute_swing_risk_levels(
        trigger_price=25000.0,
        structural_stop_price=24990.0,
        daily_atr=15.0,
        portfolio_equity=1_000_000.0,
        atr_multiplier=1.2,
    )
    assert res1.effective_stop == 24982.0
    assert res1.risk_per_share == 18.0
    assert res1.target_1 == 25027.0
    assert res1.target_2 == 25054.0
    assert res1.max_chase_price == 25250.0


def test_options_dual_budget_sizing_and_zero_lot_rejection():
    # Case 1: Normal viable trade
    # Equity = 1,000,000. Risk budget = 10,000 (1%). Outlay budget = 50,000 (5%).
    # Entry = 200, Stop = 160 -> Risk = 40/unit. Lot size = 75 (NIFTY).
    # Risk/lot = 40 * 75 = 3,000.
    # Outlay/lot = 200 * 75 = 15,000.
    # Lots by risk = int(10,000 / 3,000) = 3.
    # Lots by outlay = int(50,000 / 15,000) = 3.
    res = compute_swing_options_risk(
        entry_premium=200.0,
        stop_premium=160.0,
        target_premium_1=260.0,
        target_premium_2=320.0,
        lot_size=75,
        portfolio_equity=1_000_000.0,
        max_risk_pct=1.0,
        max_premium_pct=5.0,
    )
    assert res.is_viable is True
    assert res.num_lots == 3
    assert res.total_premium_outlay == 45000.0
    assert res.max_loss == 9000.0
    assert res.capital_at_risk_pct == 0.9

    # Case 2: Zero-lot rejection (§14: No forced 1-lot!)
    # Expensive option where 1 lot violates 1% risk budget.
    # Entry = 600, Stop = 400 -> Risk/unit = 200. Lot size = 75.
    # Risk/lot = 200 * 75 = 15,000 > 10,000 risk budget!
    res_rejected = compute_swing_options_risk(
        entry_premium=600.0,
        stop_premium=400.0,
        target_premium_1=900.0,
        target_premium_2=1200.0,
        lot_size=75,
        portfolio_equity=1_000_000.0,
        max_risk_pct=1.0,
        max_premium_pct=5.0,
    )
    assert res_rejected.is_viable is False
    assert res_rejected.num_lots == 0
    assert "Capital budget insufficient for 1 lot" in res_rejected.rejection_reason


def test_portfolio_risk_underlying_concentration():
    manager = PortfolioRiskManager(
        total_equity=1_000_000.0,
        max_heat_pct=5.0,
        max_positions_per_underlying=2,
        max_positions_count=6,
    )

    pos1 = SwingPosition(
        setup_id="s1", underlying="NIFTY", option_type="CE", strike=25000.0,
        expiry_date="2026-09-26", contract_symbol="NSE:NIFTY26SEP25000CE",
        direction="LONG_CALL", strategy="TREND_BREAKOUT_CE",
        entry_premium=200.0, current_premium=210.0, num_lots=1, lot_size=75,
        initial_stop_premium=160.0, current_stop_premium=160.0, spot_stop=24800.0,
        target_1=260.0, target_2=320.0, spot_at_entry=25000.0, current_spot=25100.0,
    )
    pos2 = SwingPosition(
        setup_id="s2", underlying="NIFTY", option_type="PE", strike=24800.0,
        expiry_date="2026-09-26", contract_symbol="NSE:NIFTY26SEP24800PE",
        direction="LONG_PUT", strategy="PULLBACK_PE",
        entry_premium=180.0, current_premium=185.0, num_lots=1, lot_size=75,
        initial_stop_premium=140.0, current_stop_premium=140.0, spot_stop=25100.0,
        target_1=240.0, target_2=300.0, spot_at_entry=25000.0, current_spot=24950.0,
    )

    open_positions = [pos1, pos2]

    # Candidate 3 is also NIFTY -> MUST BE BLOCKED (max 2 per underlying)
    candidate_nifty = SwingSetup(
        setup_id="s3", underlying="NIFTY", direction="LONG_CALL", option_type="CE",
        strategy="STAGE2_CE", strike=25200.0, expiry_date="2026-09-26",
        contract_symbol="NSE:NIFTY26SEP25200CE", lot_size=75, spot_price=25050.0,
        spot_trigger=25100.0, spot_stop=24900.0, entry_premium=150.0, stop_premium=110.0,
        target_premium_1=210.0, target_premium_2=270.0, premium_risk_per_lot=3000.0,
        score=SetupScoreBreakdown(total=80.0),
        trade_validity=TradeValidity(),
    )

    allowed, reason = manager.validate_candidate(candidate_nifty, open_positions)
    assert allowed is False
    assert "Underlying concentration limit reached for 'NIFTY'" in reason

    # Candidate 4 is BANKNIFTY -> ALLOWED
    candidate_bnf = candidate_nifty.model_copy(update={"underlying": "BANKNIFTY", "contract_symbol": "NSE:BANKNIFTY26SEP52000CE"})
    allowed_bnf, reason_bnf = manager.validate_candidate(candidate_bnf, open_positions)
    assert allowed_bnf is True


def test_dual_layer_stop_and_trailing():
    portfolio_greeks_ledger.clear()

    setup = SwingSetup(
        setup_id="s1", underlying="NIFTY", direction="LONG_CALL", option_type="CE",
        strategy="TREND_BREAKOUT_CE", strike=25000.0, expiry_date="2026-09-26",
        contract_symbol="NSE:NIFTY26SEP25000CE", lot_size=75, spot_price=25000.0,
        spot_trigger=25050.0, spot_stop=24800.0, entry_premium=200.0, stop_premium=160.0,
        target_premium_1=260.0, target_premium_2=320.0, premium_risk_per_lot=3000.0,
        greeks={"delta": 0.55, "theta_day": -12.0, "vega": 15.0},
        score=SetupScoreBreakdown(total=85.0),
        trade_validity=TradeValidity(),
    )

    # Enter position
    pos = create_position_from_setup(setup, fill_premium=200.0, num_lots=1)
    assert pos.status == "OPEN"
    assert pos.current_stop_premium == 160.0
    assert pos.spot_stop == 24800.0

    # Test 1: Underlying Spot Invalidation (spot breaches 24,800 even if premium is still 170)
    pos_inv = update_position(pos, current_premium=170.0, current_spot=24780.0)
    assert pos_inv.status == "CLOSED"
    assert pos_inv.exit_reason == "UNDERLYING_STOP"

    # Test 2: Option Premium Stop Hit (spot is fine at 25,020, but premium dropped to 155 due to theta/iv crush)
    pos_opt_stop = update_position(pos, current_premium=155.0, current_spot=25020.0)
    assert pos_opt_stop.status == "CLOSED"
    assert pos_opt_stop.exit_reason == "OPTION_STOP"

    # Test 3: +1.5R Target hit -> Break-Even Stop
    # Risk is 40. +1.5R gain = +60 -> Premium 260.
    pos_be = update_position(pos, current_premium=262.0, current_spot=25150.0)
    assert pos_be.status == "OPEN"
    assert pos_be.current_stop_premium == 200.0
    assert pos_be.stop_method == "BREAK_EVEN"

    # Test 4: +2.0R Trailing Stop (50% of peak profit protected)
    # Entry = 200, Risk = 40. Target 2 is 320 (+3R).
    # Premium reaches 290 (+2.25R, gain = 90). Peak gain = 90.
    # Trail stop moves to 200 + 90 * 0.50 = 245.0
    pos_trail = update_position(pos, current_premium=290.0, current_spot=25220.0)
    assert pos_trail.status == "OPEN"
    assert pos_trail.highest_premium == 290.0
    assert pos_trail.current_stop_premium == 245.0
    assert pos_trail.stop_method == "TRAILING_PREMIUM"


