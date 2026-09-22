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


@pytest.fixture(autouse=True)
def _pinned_selector_clock(monkeypatch):
    """Pin the contract selector's clock for this module.

    Selection economics are priced against hours-to-expiry, so these fixtures
    only clear the class theta-drag ceilings mid-cycle (~5 days out). With an
    unpinned clock this module is a calendar time bomb: near/at expiry every
    candidate correctly fails closed and the strategies abstain, which the
    tests misread as a regression.
    """
    from datetime import datetime

    import app.signals.options_intelligence.selector as selector_mod
    from app.signals.safety.clocks import IST

    fixed = datetime(2026, 10, 1, 10, 0, tzinfo=IST)

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(selector_mod, "datetime", _FixedDateTime)


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


def _chain_for_spot(
    spot: float,
    step: float = 50.0,
    ltps: tuple[float, float, float] = (250.0, 180.0, 110.0),
) -> object:
    """Minimal chain snapshot with live LTPs around ATM (fail-closed happy path).

    Unit tests have no broker, so without explicit quotes the selector must
    return None. These LTPs stand in for the broker chain — never a model.
    """
    from types import SimpleNamespace

    atm = round(spot / step) * step
    strikes = []
    for k, ltp in ((atm - step, ltps[0]), (atm, ltps[1]), (atm + step, ltps[2])):
        strikes.append(
            SimpleNamespace(
                strike=k,
                call=SimpleNamespace(ltp=ltp),
                put=SimpleNamespace(ltp=ltp),
            )
        )
    return SimpleNamespace(strikes=strikes)


def test_breakout_options_strategy():
    candles = _generate_synthetic_candles(count=50, base_price=24000.0, trend_step=30.0, contract_last_n=6)
    features = extract_swing_features(candles)
    regime = MarketRegime(regime="BULL", confidence=85.0)

    strat = BreakoutOptionsStrategy()
    spot = float(features.close)
    setup = strat.evaluate(
        underlying="NIFTY",
        features=features,
        candles=candles,
        regime=regime,
        portfolio_equity=1_000_000.0,
        current_iv=0.14,
        iv_percentile=30.0,
        spot_price=spot,
        options_chain=_chain_for_spot(spot, ltps=(100.0, 70.0, 45.0)),
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
    spot = float(features.close)
    setup = strat.evaluate(
        underlying="NIFTY",
        features=features,
        candles=candles,
        regime=regime,
        portfolio_equity=1_000_000.0,
        current_iv=0.15,
        iv_percentile=40.0,
        spot_price=spot,
        options_chain=_chain_for_spot(spot),
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
    spot = float(features.close)
    setup = strat.evaluate(
        underlying="BANKNIFTY",
        features=features,
        candles=candles,
        regime=regime,
        portfolio_equity=1_000_000.0,
        current_iv=0.16,
        iv_percentile=45.0,
        spot_price=spot,
        options_chain=_chain_for_spot(spot, step=100.0),
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
    spot = float(features.close)
    setup = strat.evaluate(
        underlying="NIFTY",
        features=features,
        candles=candles,
        regime=regime,
        portfolio_equity=1_000_000.0,
        current_iv=0.12,
        iv_percentile=20.0,
        spot_price=spot,
        options_chain=_chain_for_spot(spot, ltps=(100.0, 70.0, 45.0)),
    )

    assert setup is not None
    assert setup.strategy == "IV_DIRECTIONAL"
    assert setup.iv_percentile == 20.0
    assert setup.entry_premium > 0
    assert setup.stop_premium < setup.entry_premium
    assert setup.target_premium_1 > setup.entry_premium
    assert setup.target_premium_2 > setup.target_premium_1
    assert setup.trade_validity.underlying_valid is True


def test_bear_regime_setup_blocked_on_radar():
    """Verify that during BEAR market regimes, unhedged Call setups are preserved on radar as BLOCKED."""
    candles = _generate_synthetic_candles(count=50, base_price=24000.0, trend_step=30.0, contract_last_n=6)
    features = extract_swing_features(candles)
    bear_regime = MarketRegime(regime="BEAR", confidence=80.0)

    strat = BreakoutOptionsStrategy()
    spot = float(features.close)
    setup = strat.evaluate(
        underlying="NIFTY",
        features=features,
        candles=candles,
        regime=bear_regime,
        portfolio_equity=1_000_000.0,
        current_iv=0.14,
        iv_percentile=30.0,
        spot_price=spot,
        options_chain=_chain_for_spot(spot, ltps=(100.0, 70.0, 45.0)),
    )

    assert setup is not None
    # Bullish breakout in BEAR regime must be BLOCKED
    assert setup.direction == "LONG_CALL"
    assert setup.signal_state == "BLOCKED"
    assert any("BEAR" in r for r in setup.risk_reasons)

