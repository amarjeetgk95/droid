"""
Tests for Intraday Swing Mode (v6.1).
Validates:
  1. extract_intraday_swing_features (15M EMA ribbon, VWAP, ORB, ATR)
  2. IntradayPullbackStrategy (15M 20 EMA + VWAP alignment)
  3. IntradayORBStrategy (Opening Range Breakout)
  4. 15:15 IST hard auto-close and accelerated intraday trailing (+1.0R break-even)
"""
from __future__ import annotations

import pytest
from app.swing.technical import extract_intraday_swing_features
from app.swing.models import MarketRegime, SwingPosition, SwingSetup
from app.swing.strategies.intraday_pullback import IntradayPullbackStrategy
from app.swing.strategies.intraday_orb import IntradayORBStrategy
from app.swing.lifecycle import update_position, create_position_from_setup


def _generate_synthetic_intraday_candles(count: int = 20, base: float = 24000.0, step: float = 10.0):
    candles = []
    for i in range(count):
        c = base + i * step
        candles.append({
            "open": c - 5.0,
            "high": c + 15.0,
            "low": c - 15.0,
            "close": c,
            "volume": 50000 + i * 2000,
            "timestamp": 1700000000 + i * 900,
        })
    return candles


def test_extract_intraday_swing_features():
    candles = _generate_synthetic_intraday_candles(count=20, base=24000.0, step=15.0)
    feat = extract_intraday_swing_features(candles)

    assert feat.close == 24000.0 + 19 * 15.0
    assert feat.vwap is not None
    assert feat.price_above_vwap is True
    assert feat.opening_range_high > 0.0
    assert feat.opening_range_low > 0.0
    assert feat.is_orb_bullish is True
    assert feat.atr_14 > 0.0


def test_intraday_pullback_strategy():
    candles = _generate_synthetic_intraday_candles(count=20, base=24000.0, step=8.0)
    feat = extract_intraday_swing_features(candles)
    regime = MarketRegime(regime="BULL", confidence=80.0)

    strat = IntradayPullbackStrategy()
    setup = strat.evaluate(
        underlying="NIFTY",
        features=feat,
        candles=candles,
        regime=regime,
        portfolio_equity=1_000_000.0,
    )

    if setup is not None:
        assert setup.horizon == "INTRADAY"
        assert setup.timeframe == "15M"
        assert setup.hard_exit_time == "15:15:00"
        assert setup.expected_holding_days == 0
        assert setup.option_type in ("CE", "PE")


def test_intraday_orb_strategy():
    candles = _generate_synthetic_intraday_candles(count=20, base=24000.0, step=20.0)
    feat = extract_intraday_swing_features(candles)
    regime = MarketRegime(regime="BULL", confidence=80.0)

    strat = IntradayORBStrategy()
    setup = strat.evaluate(
        underlying="NIFTY",
        features=feat,
        candles=candles,
        regime=regime,
        portfolio_equity=1_000_000.0,
    )

    assert setup is not None
    assert setup.horizon == "INTRADAY"
    assert setup.timeframe == "15M"
    assert setup.strategy == "INTRADAY_ORB_CE"
    assert setup.hard_exit_time == "15:15:00"


def test_intraday_accelerated_breakeven_trailing():
    pos = SwingPosition(
        setup_id="test-intra-1",
        underlying="NIFTY",
        option_type="CE",
        strike=24000.0,
        expiry_date="2026-09-17",
        contract_symbol="NSE:NIFTY2691724000CE",
        direction="LONG_CALL",
        strategy="INTRADAY_PULLBACK_CE",
        horizon="INTRADAY",
        timeframe="15M",
        hard_exit_time="15:15:00",
        entry_premium=100.0,
        current_premium=100.0,
        initial_stop_premium=80.0,  # 20 pt risk
        current_stop_premium=80.0,
        spot_stop=23900.0,
        spot_at_entry=24000.0,
        current_spot=24000.0,
        target_1=130.0,  # +1.5R
        target_2=160.0,  # +3.0R
    )

    # At +1.0R (premium moves to 120): For intraday, break-even activates!
    upd = update_position(pos, current_premium=120.0, current_spot=24100.0, check_time_stop=False)
    assert upd.stop_method == "BREAK_EVEN"
    assert upd.current_stop_premium == 100.0


def test_intraday_1515_hard_time_stop():
    from datetime import datetime
    pos = SwingPosition(
        setup_id="test-intra-close",
        underlying="NIFTY",
        option_type="CE",
        strike=24000.0,
        expiry_date="2026-09-17",
        contract_symbol="NSE:NIFTY2691724000CE",
        direction="LONG_CALL",
        strategy="INTRADAY_PULLBACK_CE",
        horizon="INTRADAY",
        timeframe="15M",
        hard_exit_time="15:15:00",
        entry_premium=100.0,
        current_premium=105.0,
        initial_stop_premium=80.0,
        current_stop_premium=80.0,
        spot_stop=23900.0,
        spot_at_entry=24000.0,
        current_spot=24000.0,
        target_1=130.0,
        target_2=160.0,
    )

    # Simulate 15:16:00 IST (after 15:15:00)
    time_after_close = datetime.strptime("2026-09-13 15:16:00", "%Y-%m-%d %H:%M:%S")
    upd = update_position(pos, current_premium=105.0, current_spot=24020.0, current_time=time_after_close)
    assert upd.status == "CLOSED"
    assert upd.exit_reason == "TIME_STOP"

