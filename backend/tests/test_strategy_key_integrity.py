import pytest
from decimal import Decimal
from app.signals.strategies.base import StrategyContext
from app.signals.strategies.mean_reversion import MeanReversionStrategy
from app.signals.strategies.orb import OpeningRangeBreakoutStrategy
from app.signals.strategies.gamma_squeeze import GammaSqueezeStrategy
from app.signals.strategies.trend_pullback import TrendPullbackStrategy


def test_mean_reversion_strategy_with_flat_volatility_keys():
    """Verify MeanReversionStrategy correctly parses flat bollinger keys from analyzer."""
    strat = MeanReversionStrategy()
    
    # Simulate TA volatility output with flat bollinger keys (as produced by analyzer.py)
    indicators = {
        "volatility": {
            "atr": 20.0,
            "bollinger_upper": 24900.0,
            "bollinger_middle": 24800.0,
            "bollinger_lower": 24700.0,
        },
        "momentum": {
            "rsi": 32.0,  # Oversold <= 35
        },
    }
    
    # Spot near lower band
    ctx = StrategyContext(
        underlying="NIFTY",
        spot_price=Decimal("24702"),  # Near lower band 24700
        timeframe="5M",
        indicators=indicators,
        mtf={"alignment_score": 70.0},
        fno={},
        regime="RANGE",
    )
    
    candidate = strat.detect(ctx)
    assert candidate is not None
    assert candidate.strategy == "MEAN_REVERSION"
    assert candidate.direction == "LONG_CALL"
    assert candidate.trigger > candidate.spot_price
    assert candidate.stop_loss < candidate.entry_min


def test_orb_strategy_calculates_opening_range_from_candles():
    """Verify ORBStrategy calculates opening range from candles when orb dict is missing."""
    strat = OpeningRangeBreakoutStrategy()
    
    candles = [
        {"high": 24820.0, "low": 24780.0, "close": 24810.0, "open": 24790.0},
        {"high": 24830.0, "low": 24790.0, "close": 24825.0, "open": 24810.0},
        {"high": 24840.0, "low": 24800.0, "close": 24835.0, "open": 24825.0},
    ]
    
    # Spot breaks above opening range high (24840)
    ctx = StrategyContext(
        underlying="NIFTY",
        spot_price=Decimal("24845"),  # Breaks above high
        timeframe="5M",
        indicators={"atr": 25.0},
        mtf={"overall_bias": "BULLISH"},
        fno={},
        regime="RANGE",
        candles=candles,
        timestamp_ms=0,  # Bypass session time window in test
    )
    
    candidate = strat.detect(ctx)
    assert candidate is not None
    assert candidate.strategy == "ORB"
    assert candidate.direction == "LONG_CALL"
    assert candidate.trigger >= Decimal("24845")


def test_gamma_squeeze_strategy_derives_oi_change():
    """Verify GammaSqueezeStrategy handles missing explicit oi_change_pct."""
    strat = GammaSqueezeStrategy()
    
    fno = {
        "pcr": 1.35,  # Extreme PCR >= 1.25
        "futures_oi_change": 50000,
        "futures_oi": 500000,  # 10% change >= 5%
        "max_pain": 24800.0,
    }
    
    ctx = StrategyContext(
        underlying="NIFTY",
        spot_price=Decimal("24820"),  # Above max pain
        timeframe="5M",
        indicators={"atr": 20.0},
        mtf={"alignment_score": 75.0},
        fno=fno,
        regime="HIGH_VOL",
    )
    
    candidate = strat.detect(ctx)
    assert candidate is not None
    assert candidate.strategy == "GAMMA_SQUEEZE"
    assert candidate.direction == "LONG_CALL"


def test_trend_pullback_strategy_without_ema200():
    """Verify TrendPullbackStrategy detects pullbacks without hard ema200 requirement."""
    strat = TrendPullbackStrategy()
    
    indicators = {
        "trend": {
            "ema20": 24800.0,
            "ema50": 24750.0,
            "trend": "BULLISH",
            "adx": 26.0,
        },
        "atr": 22.0,
    }
    
    ctx = StrategyContext(
        underlying="NIFTY",
        spot_price=Decimal("24805"),  # Retesting EMA20 (24800)
        timeframe="5M",
        indicators=indicators,
        mtf={"overall_bias": "BULLISH"},
        fno={},
        regime="TREND_UP",
    )
    
    candidate = strat.detect(ctx)
    assert candidate is not None
    assert candidate.strategy == "TREND_PULLBACK"
    assert candidate.direction == "LONG_CALL"
