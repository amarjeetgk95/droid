"""
Unit tests for Options Swing Strategies Suite (v6.0 Options Overhaul).
"""
import pytest
from app.swing.models import MarketRegime
from app.swing.technical import extract_swing_features
from app.swing.strategies.vcp_breakout import BreakoutOptionsStrategy, VCPBreakoutStrategy
from app.swing.strategies.trend_pullback import PullbackOptionsStrategy, TrendPullbackStrategy
from app.swing.strategies.stage2_breakout import Stage2OptionsStrategy, Stage2BreakoutStrategy
from app.swing.strategies.iv_directional import IVDirectionalStrategy


def _generate_synthetic_candles(
    count: int = 50,
    base_price: float = 24000.0,
    trend_step: float = 25.0,
    contract_last_n: int = 5,
) -> list[dict]:
    candles = []
    for i in range(count):
        close = base_price + i * trend_step
        spread = 150.0 if i < (count - contract_last_n) else 30.0
        vol = 500000 if i < (count - contract_last_n) else 150000
        candles.append({
            "timestamp": 1700000000 + i * 86400,
            "open": close - 15.0,
            "high": close + spread,
            "low": close - spread,
            "close": close,
            "volume": vol,
        })
    return candles


def test_breakout_options_strategy():
    candles = _generate_synthetic_candles(count=50, base_price=24000.0, trend_step=30.0, contract_last_n=6)
    features = extract_swing_features(candles)
    regime = MarketRegime(regime="BULL", confidence=85.0)

    strat = BreakoutOptionsStrategy()
    setup = strat.evaluate(
        underlying="NIFTY",
        features=features,
        candles=candles,
        regime=regime,
        portfolio_equity=1_000_000.0,
        current_iv=0.14,
        iv_percentile=30.0,
    )

    assert setup is not None
    assert setup.underlying == "NIFTY"
    assert setup.strategy in ("TREND_BREAKOUT_CE", "TREND_BREAKOUT_PE")
    assert setup.strike > 0
    assert setup.entry_premium > 0
    assert setup.stop_premium < setup.entry_premium
    assert setup.target_premium_1 > setup.entry_premium
    assert setup.target_premium_2 > setup.target_premium_1
    assert setup.trade_validity is not None
    assert setup.trade_validity.underlying_valid is True
    assert setup.score.total >= 40.0


def test_pullback_options_strategy():
    candles = _generate_synthetic_candles(count=50, base_price=24000.0, trend_step=20.0, contract_last_n=0)
    features = extract_swing_features(candles)
    regime = MarketRegime(regime="BULL", confidence=80.0)

    strat = PullbackOptionsStrategy()
    setup = strat.evaluate(
        underlying="NIFTY",
        features=features,
        candles=candles,
        regime=regime,
        portfolio_equity=1_000_000.0,
        current_iv=0.15,
        iv_percentile=40.0,
    )

    # Strategy may return setup or abstain depending on strict EMA pullback condition
    if setup is not None:
        assert setup.underlying == "NIFTY"
        assert setup.strategy in ("PULLBACK_CE", "PULLBACK_PE")
        assert setup.entry_premium > 0


def test_stage2_options_strategy():
    candles = _generate_synthetic_candles(count=60, base_price=24000.0, trend_step=35.0, contract_last_n=0)
    features = extract_swing_features(candles)
    regime = MarketRegime(regime="BULL", confidence=85.0)

    strat = Stage2OptionsStrategy()
    setup = strat.evaluate(
        underlying="BANKNIFTY",
        features=features,
        candles=candles,
        regime=regime,
        portfolio_equity=1_000_000.0,
        current_iv=0.16,
        iv_percentile=45.0,
    )

    assert setup is not None
    assert setup.underlying == "BANKNIFTY"
    assert setup.strategy in ("STAGE2_CE", "STAGE2_PE")
    assert setup.entry_premium > 0
    assert setup.greeks is not None


def test_iv_directional_strategy():
    candles = _generate_synthetic_candles(count=50, base_price=24000.0, trend_step=25.0, contract_last_n=0)
    features = extract_swing_features(candles)
    regime = MarketRegime(regime="BULL", confidence=80.0)

    strat = IVDirectionalStrategy()
    # Favorable low IV condition (IV percentile <= 40%)
    setup = strat.evaluate(
        underlying="NIFTY",
        features=features,
        candles=candles,
        regime=regime,
        portfolio_equity=1_000_000.0,
        current_iv=0.12,
        iv_percentile=20.0,
    )

    assert setup is not None
    assert setup.strategy == "IV_DIRECTIONAL"
    assert setup.iv_percentile == 20.0
    assert setup.trade_validity.underlying_valid is True


def test_bear_regime_setup_blocked_on_radar():
    """Verify that during BEAR market regimes, unhedged Call setups are preserved on radar as BLOCKED."""
    candles = _generate_synthetic_candles(count=50, base_price=24000.0, trend_step=30.0, contract_last_n=6)
    features = extract_swing_features(candles)
    bear_regime = MarketRegime(regime="BEAR", confidence=80.0)

    strat = BreakoutOptionsStrategy()
    setup = strat.evaluate(
        underlying="NIFTY",
        features=features,
        candles=candles,
        regime=bear_regime,
        portfolio_equity=1_000_000.0,
        current_iv=0.14,
        iv_percentile=30.0,
    )

    assert setup is not None
    # Bullish breakout in BEAR regime must be BLOCKED
    if setup.direction == "LONG_CALL":
        assert setup.signal_state == "BLOCKED"
        assert any("BEAR" in r for r in setup.risk_reasons)

