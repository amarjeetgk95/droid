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
)
from app.signals.strategies.liquidity_sweep import LiquiditySweepReclaimStrategy
from app.signals.strategies.momentum_reacceleration import MomentumReaccelerationStrategy
from app.signals.strategies.regime_trend import RegimeAdaptiveTrendStrategy
from app.signals.strategies.volatility_breakout import VolatilityBreakoutStrategy
from app.signals.features.engine import compute_feature_snapshot
from app.signals.participation.oi_volume_engine import participation_engine
from app.signals.orthogonal_confluence import orthogonal_confluence_engine


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
        # Registry has all 11 plus backward compatibility aliases
        assert "BREAKOUT" in STRATEGY_REGISTRY
        assert "EMA_RIBBON" in STRATEGY_REGISTRY


class TestNewScalpStrategies:
    def test_liquidity_sweep_reclaim_bullish(self):
        strat = LiquiditySweepReclaimStrategy()
        spot = Decimal("24810.0")

        # Prior candles set swing low at 24800, current candle sweeps to 24785 and reclaims to 24810
        candles = [
            {"high": 24860.0, "low": 24830.0, "open": 24840.0, "close": 24850.0},
            {"high": 24850.0, "low": 24820.0, "open": 24850.0, "close": 24825.0},
            {"high": 24840.0, "low": 24800.0, "open": 24825.0, "close": 24805.0}, # Swing Low 24800
            {"high": 24820.0, "low": 24802.0, "open": 24805.0, "close": 24815.0},
            {"high": 24815.0, "low": 24785.0, "open": 24790.0, "close": 24810.0}, # Swept 24800 to 24785, reclaimed 24810
        ]

        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="1M",
            candles=candles,
            indicators={"atr": 20.0},
            mtf={"alignment_score": 75.0},
            regime="RANGE",
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
            {"high": 24860.0, "low": 24830.0, "open": 24835.0, "close": 24855.0},
            {"high": 24880.0, "low": 24850.0, "open": 24855.0, "close": 24875.0},
            {"high": 24900.0, "low": 24870.0, "open": 24875.0, "close": 24895.0},
            {"high": 24915.0, "low": 24890.0, "open": 24895.0, "close": 24910.0}, # Impulse high 24915
            {"high": 24910.0, "low": 24895.0, "open": 24908.0, "close": 24898.0}, # Controlled pause
            {"high": 24925.0, "low": 24898.0, "open": 24900.0, "close": 24920.0}, # Reacceleration breaking 24910
        ]

        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="1M",
            candles=candles,
            indicators={"atr": 20.0},
            mtf={"alignment_score": 80.0},
            regime="TREND_UP",
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

        # Tight ranges (compression) followed by breakout candle
        candles = [
            {"high": 25005.0, "low": 24995.0, "open": 25000.0, "close": 25002.0},
            {"high": 25008.0, "low": 24998.0, "open": 25002.0, "close": 25005.0},
            {"high": 25006.0, "low": 24997.0, "open": 25004.0, "close": 25000.0},
            {"high": 25020.0, "low": 25000.0, "open": 25002.0, "close": 25015.0},
        ]

        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="5M",
            candles=candles,
            indicators={
                "atr": 20.0,
                "volume_ratio": 1.8,
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


class TestSharedFeaturesAndConfluence:
    def test_feature_snapshot_computation(self):
        candles = [
            {"high": 25010.0, "low": 24990.0, "open": 24995.0, "close": 25005.0, "volume": 1000},
            {"high": 25020.0, "low": 25000.0, "open": 25005.0, "close": 25015.0, "volume": 1200},
            {"high": 25030.0, "low": 25010.0, "open": 25015.0, "close": 25025.0, "volume": 1500},
        ]
        snap = compute_feature_snapshot(
            underlying="NIFTY",
            spot_price=25025.0,
            candles=candles,
            timeframe="5M",
            vwap=25000.0,
            indicators={"atr": 20.0},
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
            candles=[{"high": 25055.0, "low": 25030.0, "open": 25035.0, "close": 25050.0, "volume": 2000}],
            timeframe="5M",
            vwap=25020.0,
            indicators={"atr": 22.0},
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
        assert res.passed is True
        assert res.confluence_score >= 65.0
        assert len(res.confirmed_factors) >= 2
        assert res.sizing_multiplier >= 0.75


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
