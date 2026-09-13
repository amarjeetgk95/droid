"""
Unit tests for Swing Strategies Suite (v5.0 §6).
"""
import pytest
from app.swing.models import MarketRegime, SectorClassification
from app.swing.technical import extract_swing_features
from app.swing.strategies.vcp_breakout import VCPBreakoutStrategy
from app.swing.strategies.trend_pullback import TrendPullbackStrategy
from app.swing.strategies.stage2_breakout import Stage2BreakoutStrategy


def _generate_synthetic_candles(
    count: int = 50,
    base_price: float = 1000.0,
    trend_step: float = 3.0,
    contract_last_n: int = 5,
) -> list[dict]:
    candles = []
    for i in range(count):
        close = base_price + i * trend_step
        spread = 20.0 if i < (count - contract_last_n) else 4.0
        vol = 500000 if i < (count - contract_last_n) else 150000
        candles.append({
            "timestamp": 1700000000 + i * 86400,
            "open": close - 2.0,
            "high": close + spread,
            "low": close - spread,
            "close": close,
            "volume": vol,
        })
    return candles


def test_vcp_breakout_strategy():
    candles = _generate_synthetic_candles(count=50, base_price=1000.0, trend_step=4.0, contract_last_n=6)
    features = extract_swing_features(candles)
    regime = MarketRegime(regime="BULL", confidence=85.0)
    sector_status = SectorClassification(sector="Auto", trend="LEADING", relative_strength=80.0)

    strat = VCPBreakoutStrategy()
    setup = strat.evaluate(
        symbol="TATAMOTORS",
        sector="Auto",
        features=features,
        candles=candles,
        regime=regime,
        sector_status=sector_status,
    )

    assert setup is not None
    assert setup.strategy == "VCP_BREAKOUT"
    assert setup.symbol == "TATAMOTORS"
    assert setup.trigger_price > setup.stop_price
    assert setup.target_1 > setup.trigger_price
    assert setup.target_2 > setup.target_1
    assert setup.score.total >= 50.0
    assert setup.stop_price <= setup.structural_stop  # ATR floor enforces >= structural distance


def test_trend_pullback_strategy():
    # Uptrend with a dip to 20 EMA
    candles = _generate_synthetic_candles(count=50, base_price=500.0, trend_step=3.0, contract_last_n=0)
    # Simulate a pullback on the last 2 bars towards 20 EMA
    f_prior = extract_swing_features(candles[:-2])
    ema20 = f_prior.ema_20 or 600.0

    # Dip bar touching 20 EMA then recovering
    candles[-1]["open"] = ema20 + 2.0
    candles[-1]["low"] = ema20 - 1.0
    candles[-1]["high"] = ema20 + 10.0
    candles[-1]["close"] = ema20 + 8.0 # Reversal close near high of bar
    candles[-1]["volume"] = 150000     # Low volume pullback

    features = extract_swing_features(candles)
    regime = MarketRegime(regime="BULL", confidence=80.0)
    sector_status = SectorClassification(sector="Banking", trend="IMPROVING", relative_strength=70.0)

    strat = TrendPullbackStrategy()
    setup = strat.evaluate(
        symbol="SBIN",
        sector="Banking",
        features=features,
        candles=candles,
        regime=regime,
        sector_status=sector_status,
    )

    assert setup is not None
    assert setup.strategy == "TREND_PULLBACK_20EMA"
    assert setup.risk_reward_t1 >= 1.2
    assert setup.trigger_price > setup.stop_price


def test_stage2_breakout_strategy():
    candles = _generate_synthetic_candles(count=60, base_price=2000.0, trend_step=5.0, contract_last_n=0)
    # Breakout bar with volume expansion
    last_high = max(c["high"] for c in candles[:-1])
    candles[-1]["close"] = last_high + 2.0
    candles[-1]["high"] = last_high + 5.0
    candles[-1]["low"] = last_high - 10.0
    candles[-1]["volume"] = 1500000 # High volume surge

    features = extract_swing_features(candles)
    regime = MarketRegime(regime="BULL", confidence=85.0)
    sector_status = SectorClassification(sector="IT", trend="LEADING", relative_strength=85.0)

    strat = Stage2BreakoutStrategy()
    setup = strat.evaluate(
        symbol="TCS",
        sector="IT",
        features=features,
        candles=candles,
        regime=regime,
        sector_status=sector_status,
    )

    assert setup is not None
    assert setup.strategy == "STAGE2_BREAKOUT"
    assert setup.score.volume >= 10.0


def test_bear_regime_setup_surfaced_as_blocked():
    """Verify that during BEAR market regimes, constructive setups are preserved on radar as BLOCKED."""
    candles = _generate_synthetic_candles(count=50, base_price=1000.0, trend_step=4.0, contract_last_n=6)
    features = extract_swing_features(candles)
    bear_regime = MarketRegime(regime="BEAR", confidence=80.0)
    sector_status = SectorClassification(sector="Auto", trend="IMPROVING", relative_strength=65.0)

    strat = VCPBreakoutStrategy()
    setup = strat.evaluate(
        symbol="BAJAJ-AUTO",
        sector="Auto",
        features=features,
        candles=candles,
        regime=bear_regime,
        sector_status=sector_status,
    )

    # Must NOT be dropped (None)
    assert setup is not None
    # Must be marked BLOCKED so live unhedged long execution is prevented
    assert setup.signal_state == "BLOCKED"
    # Must explain the regime restriction
    assert any("BEAR" in r for r in setup.risk_reasons)
    assert any("reclaims" in r for r in setup.invalidation_rules)
