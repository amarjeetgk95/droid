"""Unit test suite for Fisher-9 + MACD Confluence Strategy.

Tests:
  - Protocol adherence & fail-closed contracts
  - Bullish trend pullback detection (LONG_CALL)
  - Bearish trend pullback detection (LONG_PUT)
  - Neutral / no-trigger conditions (returns None)
"""

from decimal import Decimal
import pytest

from app.signals.strategies.base import StrategyContext
from app.signals.strategies.fisher_macd_confluence import FisherMACDConfluenceStrategy


def _generate_candles_for_fisher_oversold(base_price: float = 25000.0) -> list[dict]:
    """Generate candles where price drops sharply to drive Fisher < -1.0, then hooks up across trigger."""
    candles = []
    p = base_price

    # 12 bars steady flat
    for _ in range(12):
        candles.append({"open": p, "high": p + 10.0, "low": p - 10.0, "close": p, "volume": 1500})

    # 4 bars sharp drop to push Fisher < -1.5
    for _ in range(4):
        p -= 50.0
        candles.append({"open": p + 20.0, "high": p + 25.0, "low": p - 5.0, "close": p, "volume": 2500})

    # 2 bars bounce to hook Fisher upward and cross trigger
    p += 40.0
    candles.append({"open": p - 30.0, "high": p + 5.0, "low": p - 5.0, "close": p, "volume": 3000})
    p += 40.0
    candles.append({"open": p - 30.0, "high": p + 10.0, "low": p - 5.0, "close": p, "volume": 3500})

    return candles


def _generate_candles_for_fisher_overbought(base_price: float = 25000.0) -> list[dict]:
    """Generate candles where price rallies sharply to drive Fisher > +1.0, then hooks down across trigger."""
    candles = []
    p = base_price

    # 12 bars steady flat
    for _ in range(12):
        candles.append({"open": p, "high": p + 10.0, "low": p - 10.0, "close": p, "volume": 1500})

    # 4 bars sharp rally to push Fisher > +1.5
    for _ in range(4):
        p += 50.0
        candles.append({"open": p - 20.0, "high": p + 5.0, "low": p - 25.0, "close": p, "volume": 2500})

    # 2 bars drop to hook Fisher downward and cross trigger
    p -= 40.0
    candles.append({"open": p + 30.0, "high": p + 5.0, "low": p - 5.0, "close": p, "volume": 3000})
    p -= 40.0
    candles.append({"open": p + 30.0, "high": p + 5.0, "low": p - 10.0, "close": p, "volume": 3500})

    return candles


def test_fisher_macd_strategy_protocol_and_fail_closed():
    strat = FisherMACDConfluenceStrategy()
    assert strat.name == "FISHER_MACD_CONFLUENCE"

    # Fewer than 15 candles -> fail-closed (returns None)
    ctx_few_candles = StrategyContext(
        underlying="NIFTY",
        spot_price=Decimal("25000.00"),
        timeframe="5M",
        candles=[{"open": 25000, "high": 25010, "low": 24990, "close": 25005, "volume": 1000}],
        indicators={"atr": 30.0},
    )
    assert strat.detect(ctx_few_candles) is None

    # Invalid spot -> fail-closed
    ctx_zero_spot = StrategyContext(
        underlying="NIFTY",
        spot_price=Decimal("0.00"),
        timeframe="5M",
        candles=[],
    )
    assert strat.detect(ctx_zero_spot) is None


def test_fisher_macd_strategy_bullish_pullback(mock_market_feed):
    strat = FisherMACDConfluenceStrategy()
    candles = _generate_candles_for_fisher_oversold(base_price=25000.0)
    current_close = Decimal(str(candles[-1]["close"]))

    ctx = StrategyContext(
        underlying="NIFTY",
        spot_price=current_close,
        timeframe="5M",
        candles=candles,
        indicators={"atr": 40.0},
        mtf={
            "overall_bias": "BULLISH",
            "timeframe_biases": {"15M": "BULLISH"},
            "alignment_score": 80.0,
        },
        regime="TREND_UP",
    )

    candidate = strat.detect(ctx)
    assert candidate is not None
    assert candidate.strategy == "FISHER_MACD_CONFLUENCE"
    assert candidate.direction == "LONG_CALL"
    assert candidate.trigger > candidate.stop_loss
    assert candidate.target_1 > candidate.spot_price
    assert candidate.target_2 > candidate.target_1
    assert candidate.stop_loss < candidate.spot_price
    assert candidate.risk_points > Decimal("0")
    assert candidate.risk_reward_t1 == 0.5
    assert candidate.risk_reward_t2 == 1.0
    assert candidate.overall_confidence >= 60.0
    assert candidate.option_contract is not None
    assert candidate.option_contract.option_type == "CE"
    assert any("Fisher-9 Oversold Pullback" in r for r in candidate.rationale)


def test_fisher_macd_strategy_bearish_pullback(mock_market_feed):
    strat = FisherMACDConfluenceStrategy()
    candles = _generate_candles_for_fisher_overbought(base_price=25000.0)
    current_close = Decimal(str(candles[-1]["close"]))

    ctx = StrategyContext(
        underlying="NIFTY",
        spot_price=current_close,
        timeframe="5M",
        candles=candles,
        indicators={"atr": 40.0},
        mtf={
            "overall_bias": "BEARISH",
            "timeframe_biases": {"15M": "BEARISH"},
            "alignment_score": 80.0,
        },
        regime="TREND_DOWN",
    )

    candidate = strat.detect(ctx)
    assert candidate is not None
    assert candidate.strategy == "FISHER_MACD_CONFLUENCE"
    assert candidate.direction == "LONG_PUT"
    assert candidate.trigger < candidate.stop_loss
    assert candidate.target_1 < candidate.spot_price
    assert candidate.target_2 < candidate.target_1
    assert candidate.stop_loss > candidate.spot_price
    assert candidate.risk_points > Decimal("0")
    assert candidate.option_contract is not None
    assert candidate.option_contract.option_type == "PE"
    assert any("Fisher-9 Overbought Rally" in r for r in candidate.rationale)


def test_fisher_macd_strategy_neutral_no_trigger():
    strat = FisherMACDConfluenceStrategy()
    # 20 flat candles with no extreme
    candles = [
        {"open": 25000.0, "high": 25005.0, "low": 24995.0, "close": 25000.0, "volume": 1000}
        for _ in range(20)
    ]

    ctx = StrategyContext(
        underlying="NIFTY",
        spot_price=Decimal("25000.00"),
        timeframe="5M",
        candles=candles,
        indicators={"atr": 30.0},
        mtf={"overall_bias": "NEUTRAL"},
        regime="RANGE",
    )

    candidate = strat.detect(ctx)
    assert candidate is None


def test_fisher_macd_dispatch_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/v1/strategies/fisher-macd/dispatch",
        json={
            "symbol": "NIFTY",
            "direction": "LONG_CALL",
            "contract_symbol": "NIFTY 23500 CE",
            "quantity": 75,
            "entry_price": 23500.0,
            "target_price": 23550.0,
            "stop_price": 23450.0,
            "destination": "PAPER_PORTFOLIO",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "dispatch_id" in data
    assert data["symbol"] == "NIFTY"
    assert data["direction"] == "LONG_CALL"
    assert data["order"] is not None
    assert "alert" in data
