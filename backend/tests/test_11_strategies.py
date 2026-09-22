"""
Unit & Integration Tests for the 100-Grade 11-Strategy Engine Architecture (§3, §67).
Verifies:
  - 5 Scalp Strategies (VWAP_SCALP, LIQUIDITY_SWEEP_RECLAIM, MICRO_MOMENTUM, MOMENTUM_REACCELERATION, GAMMA_SPIKE)
  - 6 Intraday Strategies (REGIME_ADAPTIVE_TREND, VOLATILITY_BREAKOUT, TREND_PULLBACK, ORB, MEAN_REVERSION, GAMMA_SQUEEZE)
  - Shared Feature Snapshot Provider
  - Participation Engine (Scalp vs Intraday)
  - Orthogonal Confluence Engine
"""
from decimal import Decimal
import pytest

from app.signals.strategies.base import StrategyContext, SignalCandidate
from app.signals.strategies import (
    SCALP_STRATEGIES,
    INTRADAY_STRATEGIES,
    STRATEGY_REGISTRY,
    SCALP_STRATEGY_NAMES,
    INTRADAY_STRATEGY_NAMES,
    DEMOTED_STRATEGIES,
    ALL_KNOWN_STRATEGIES,
    REGISTRY_VERSION,
)
from app.signals.strategies.ema_ribbon import EMARibbonScalpStrategy
from app.signals.strategies.liquidity_sweep import LiquiditySweepReclaimStrategy
from app.signals.strategies.momentum_reacceleration import MomentumReaccelerationStrategy
from app.signals.strategies.regime_trend import RegimeAdaptiveTrendStrategy
from app.signals.strategies.volatility_breakout import VolatilityBreakoutStrategy
from app.signals.features.engine import compute_feature_snapshot
from app.signals.participation.oi_volume_engine import participation_engine
from app.signals.orthogonal_confluence import orthogonal_confluence_engine


def _closed_candle_series(count: int = 63, start: float = 24800.0) -> list[dict]:
    """PIT-valid closed 5M candles: >= 60 bars, zigzag HH_HL uptrend.

    The feature engine drops forming bars and demands >= 60 closed bars, so
    fixtures must carry count and timestamps that prove closure.
    """
    closes: list[float] = []
    price = start
    while len(closes) < count - 3:
        for delta in (8.0, 8.0, 8.0, -6.0, -6.0):
            price += delta
            closes.append(price)
    closes = closes[: count - 3]
    for delta in (6.0, 10.0, 16.0):
        price += delta
        closes.append(price)

    base_ts = 1_700_000_400_000
    candles = []
    for i, close in enumerate(closes):
        open_ = closes[i - 1] if i else close - 3.0
        candles.append({
            "timestamp": base_ts + i * 300_000,
            "open": open_,
            "high": max(open_, close) + 4.0,
            "low": min(open_, close) - 4.0,
            "close": close,
            "volume": 1000.0 + (i % 10) * 50.0,
        })
    return candles


class Test11StrategyRegistry:
    def test_registry_contains_11_strategies(self):
        # 5 Scalp strategies
        assert len(SCALP_STRATEGIES) == 5
        assert set(SCALP_STRATEGIES.keys()) == {
            "VWAP_SCALP",
            "LIQUIDITY_SWEEP_RECLAIM",
            "MICRO_MOMENTUM",
            "MOMENTUM_REACCELERATION",
            "GAMMA_SPIKE",
        }

        # 6 Intraday strategies
        assert len(INTRADAY_STRATEGIES) == 6
        assert set(INTRADAY_STRATEGIES.keys()) == {
            "REGIME_ADAPTIVE_TREND",
            "VOLATILITY_BREAKOUT",
            "TREND_PULLBACK",
            "ORB",
            "MEAN_REVERSION",
            "GAMMA_SQUEEZE",
        }

        # Total official portfolio = 11 strategies
        assert len(SCALP_STRATEGY_NAMES) + len(INTRADAY_STRATEGY_NAMES) == 11
        # Auto-scan registry = 11 active + BREAKOUT alias (same instance).
        assert len(STRATEGY_REGISTRY) == 12
        assert STRATEGY_REGISTRY["BREAKOUT"] is STRATEGY_REGISTRY["VOLATILITY_BREAKOUT"]
        # EMA_RIBBON demoted: importable but NOT in the auto-scan registry.
        assert "EMA_RIBBON" not in STRATEGY_REGISTRY
        assert "EMA_RIBBON" in DEMOTED_STRATEGIES
        assert isinstance(DEMOTED_STRATEGIES["EMA_RIBBON"], EMARibbonScalpStrategy)
        assert len(ALL_KNOWN_STRATEGIES) == 13
        # Versioned registry contract must be present and pinned.
        assert REGISTRY_VERSION


class TestNewScalpStrategies:
    def test_liquidity_sweep_reclaim_bullish(self):
        strat = LiquiditySweepReclaimStrategy()
        spot = Decimal("24810.0")

        # Prior candles set swing low at 24800 (index 3 of 9, so it is a valid
        # window-3 pivot), current candle sweeps to 24785 and reclaims 24815.
        candles = [
            {"high": 24860.0, "low": 24835.0, "open": 24840.0, "close": 24850.0, "volume": 1000},
            {"high": 24855.0, "low": 24830.0, "open": 24850.0, "close": 24835.0, "volume": 1000},
            {"high": 24840.0, "low": 24820.0, "open": 24835.0, "close": 24825.0, "volume": 1000},
            {"high": 24830.0, "low": 24800.0, "open": 24825.0, "close": 24805.0, "volume": 1000},  # Swing Low 24800
            {"high": 24825.0, "low": 24810.0, "open": 24805.0, "close": 24820.0, "volume": 1000},
            {"high": 24835.0, "low": 24815.0, "open": 24820.0, "close": 24830.0, "volume": 1000},
            {"high": 24845.0, "low": 24825.0, "open": 24830.0, "close": 24840.0, "volume": 1000},
            {"high": 24845.0, "low": 24820.0, "open": 24840.0, "close": 24825.0, "volume": 1000},
            {"high": 24830.0, "low": 24785.0, "open": 24795.0, "close": 24815.0, "volume": 4000},  # Swept + reclaimed
        ]

        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="1M",
            candles=candles,
            indicators={"atr": 20.0, "volume_ratio": 1.5},
            mtf={"alignment_score": 75.0},
            regime="RANGE",
            is_new_1m_candle=True,
        )

        cand = strat.detect(ctx)
        assert cand is not None
        assert cand.strategy == "LIQUIDITY_SWEEP_RECLAIM"
        assert cand.direction == "LONG_CALL"
        assert cand.is_scalp is True
        assert cand.trigger > cand.spot_price
        assert cand.stop_loss < cand.entry_min
        assert cand.risk_points >= Decimal("10.0")

    def test_momentum_reacceleration_bullish(self):
        strat = MomentumReaccelerationStrategy()
        spot = Decimal("24920.0")

        # Impulse -> 1 bar pullback holding above EMA -> reacceleration candle
        candles = [
            {"high": 24860.0, "low": 24830.0, "open": 24835.0, "close": 24855.0, "volume": 1000},
            {"high": 24880.0, "low": 24850.0, "open": 24855.0, "close": 24875.0, "volume": 1000},
            {"high": 24900.0, "low": 24870.0, "open": 24875.0, "close": 24895.0, "volume": 1000},
            {"high": 24915.0, "low": 24890.0, "open": 24895.0, "close": 24910.0, "volume": 1000},  # Impulse high 24915
            {"high": 24910.0, "low": 24895.0, "open": 24908.0, "close": 24898.0, "volume": 1000},  # Controlled pause
            {"high": 24925.0, "low": 24898.0, "open": 24900.0, "close": 24920.0, "volume": 3000},  # Reacceleration breaking 24910
        ]

        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="1M",
            candles=candles,
            indicators={"atr": 20.0, "volume_ratio": 1.5},
            mtf={"alignment_score": 80.0},
            regime="TREND_UP",
            is_new_1m_candle=True,
        )

        cand = strat.detect(ctx)
        assert cand is not None
        assert cand.strategy == "MOMENTUM_REACCELERATION"
        assert cand.direction == "LONG_CALL"
        assert cand.is_scalp is True
        assert cand.trigger > cand.spot_price
        assert cand.stop_loss < cand.entry_min


class TestNewIntradayStrategies:
    def test_regime_adaptive_trend_bullish(self):
        strat = RegimeAdaptiveTrendStrategy()
        spot = Decimal("25100.0")

        # Bullish steady progression
        candles = [
            {"high": 24940.0, "low": 24900.0, "open": 24905.0, "close": 24930.0},
            {"high": 24980.0, "low": 24940.0, "open": 24945.0, "close": 24970.0},
            {"high": 25020.0, "low": 24970.0, "open": 24975.0, "close": 25010.0},
            {"high": 25060.0, "low": 25010.0, "open": 25015.0, "close": 25050.0},
            {"high": 25080.0, "low": 25040.0, "open": 25045.0, "close": 25075.0},
            {"high": 25110.0, "low": 25070.0, "open": 25075.0, "close": 25100.0},
        ]

        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="5M",
            candles=candles,
            indicators={"atr": 25.0, "adx": 28.0},
            mtf={"overall_bias": "BULLISH", "alignment_score": 85.0},
            regime="TREND_UP",
        )

        cand = strat.detect(ctx)
        assert cand is not None
        assert cand.strategy == "REGIME_ADAPTIVE_TREND"
        assert cand.direction == "LONG_CALL"
        assert cand.signal_type == "INTRADAY"
        assert cand.trigger > cand.spot_price
        assert cand.stop_loss < cand.entry_min

    def test_volatility_breakout_bullish(self):
        strat = VolatilityBreakoutStrategy()
        spot = Decimal("25015.0")

        # Tight ranges (compression) followed by breakout candle closing
        # beyond resistance with measured volume + breakout pressure.
        candles = [
            {"high": 25005.0, "low": 24995.0, "open": 25000.0, "close": 25002.0, "volume": 1000},
            {"high": 25008.0, "low": 24998.0, "open": 25002.0, "close": 25005.0, "volume": 1000},
            {"high": 25006.0, "low": 24997.0, "open": 25004.0, "close": 25000.0, "volume": 1000},
            {"high": 25030.0, "low": 25000.0, "open": 25002.0, "close": 25022.0, "volume": 8000},
        ]

        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="5M",
            candles=candles,
            indicators={
                "atr": 20.0,
                "volume_ratio": 1.8,
                "breakout_pressure": 78.0,
                "support_resistance": {"resistance": [25010.0], "support": [24950.0]},
            },
            mtf={"overall_bias": "BULLISH", "alignment_score": 80.0},
            regime="BREAKOUT",
        )

        cand = strat.detect(ctx)
        assert cand is not None
        assert cand.strategy == "VOLATILITY_BREAKOUT"
        assert cand.direction == "LONG_CALL"
        assert cand.trigger > cand.spot_price

    def test_volatility_breakout_requires_fresh_cross_of_broken_level(self):
        """Live analyzer shape: nearest `resistance` sits ABOVE the last close.

        The breakout must be measured against a typed level the decision
        candle actually crossed (prev close at/below it, close above it),
        never against the nearest-overhead scalar — `c_close >= resistance`
        was unsatisfiable on real data and silenced the strategy.
        """
        strat = VolatilityBreakoutStrategy()

        candles = [
            {"high": 25005.0, "low": 24995.0, "open": 25000.0, "close": 25002.0, "volume": 1000},
            {"high": 25008.0, "low": 24998.0, "open": 25002.0, "close": 25005.0, "volume": 1000},
            {"high": 25006.0, "low": 24997.0, "open": 25004.0, "close": 25000.0, "volume": 1000},
            {"high": 25030.0, "low": 25000.0, "open": 25002.0, "close": 25022.0, "volume": 8000},
        ]

        def _ctx(candle_series):
            return StrategyContext(
                underlying="NIFTY",
                spot_price=Decimal("25022.0"),
                timeframe="5M",
                candles=candle_series,
                indicators={
                    "atr": 20.0,
                    "volume_ratio": 1.8,
                    "breakout_pressure": 78.0,
                    "support_resistance": {
                        "resistance": 25050.0,
                        "support": 24950.0,
                        "levels": [
                            {"level": 25010.0, "type": "RESISTANCE", "source": "Pivot R1"},
                            {"level": 24950.0, "type": "SUPPORT", "source": "Pivot S1"},
                        ],
                    },
                },
                mtf={"overall_bias": "BULLISH", "alignment_score": 80.0},
                regime="TREND_UP",
            )

        cand = strat.detect(_ctx(candles))
        assert cand is not None
        assert cand.direction == "LONG_CALL"

        # Prev close already above the level => no fresh cross, no breakout.
        stale = [dict(c) for c in candles]
        stale[-2]["close"] = 25015.0
        assert strat.detect(_ctx(stale)) is None


class TestSharedFeaturesAndConfluence:
    def test_feature_snapshot_computation(self):
        candles = _closed_candle_series()
        snap = compute_feature_snapshot(
            underlying="NIFTY",
            spot_price=25025.0,
            candles=candles,
            timeframe="5M",
            vwap=25000.0,
            indicators={"atr": 20.0, "rsi": 62.0},
        )
        assert snap.spot_price == 25025.0
        assert snap.vwap == 25000.0
        assert snap.distance_to_vwap_pct > 0
        assert snap.roc_1 > 0
        assert snap.ema is not None
        assert snap.structure is not None

    def test_orthogonal_confluence_evaluation(self):
        cand = SignalCandidate(
            underlying="NIFTY",
            strategy="REGIME_ADAPTIVE_TREND",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=Decimal("25050.0"),
            entry_min=Decimal("25050.0"),
            entry_max=Decimal("25060.0"),
            trigger=Decimal("25065.0"),
            stop_loss=Decimal("25020.0"),
            target_1=Decimal("25120.0"),
            target_2=Decimal("25180.0"),
            risk_points=Decimal("30.0"),
            risk_reward_t1=1.8,
            risk_reward_t2=3.6,
        )

        snap = compute_feature_snapshot(
            underlying="NIFTY",
            spot_price=25050.0,
            candles=_closed_candle_series(),
            timeframe="5M",
            vwap=25020.0,
            indicators={"atr": 22.0, "rsi": 62.0},
        )

        part = participation_engine.evaluate(
            direction="LONG_CALL",
            desk="INTRADAY",
            rvol=1.5,
            volume_acceleration=0.3,
            price_change_pct=0.2,
            fno_data={"pcr": 1.25, "oi_change_pct": 3.5},
        )

        res = orthogonal_confluence_engine.evaluate(cand, snap, part)
        # P0-2: only a SUPPORTIVE (>=78) unanimous tape arms with full size.
        assert res.passed is True
        assert res.status == "SUPPORTIVE"
        assert res.confluence_score >= 78.0
        assert len(res.confirmed_factors) >= 2
        assert res.sizing_multiplier >= 0.75

    def test_orthogonal_confluence_fails_closed_without_features(self):
        cand = SignalCandidate(
            underlying="NIFTY",
            strategy="REGIME_ADAPTIVE_TREND",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=Decimal("25050.0"),
            entry_min=Decimal("25050.0"),
            entry_max=Decimal("25060.0"),
            trigger=Decimal("25065.0"),
            stop_loss=Decimal("25020.0"),
            target_1=Decimal("25120.0"),
            target_2=Decimal("25180.0"),
            risk_points=Decimal("30.0"),
            risk_reward_t1=1.8,
            risk_reward_t2=3.6,
        )
        res = orthogonal_confluence_engine.evaluate(cand, None, None)
        assert res.passed is False
        assert res.status == "CONTRADICTORY"
        assert res.sizing_multiplier == 0.0


class TestPortfolioStrategiesAPI:
    def test_get_portfolio_strategies(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.get("/api/v1/signals/portfolio-strategies")
        assert r.status_code == 200
        data = r.json()
        assert data["strategy_count"] == 11
        assert len(data["scalp_desk"]) == 5
        assert len(data["intraday_desk"]) == 6
        assert "LIQUIDITY_SWEEP_RECLAIM" in data["scalp_desk"]
        assert "MOMENTUM_REACCELERATION" in data["scalp_desk"]
        assert "REGIME_ADAPTIVE_TREND" in data["intraday_desk"]
        assert "VOLATILITY_BREAKOUT" in data["intraday_desk"]
