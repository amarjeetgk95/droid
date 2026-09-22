"""
Unit tests for Market Regime Engine (§19).
"""
import pytest
from app.signals.strategies.vortex_snap.features.compression import CompressionEngine
from app.signals.strategies.vortex_snap.features.pressure import DirectionalPressureEngine
from app.signals.strategies.vortex_snap.features.translation import TranslationRatioEngine
from app.signals.strategies.vortex_snap.features.regime import MarketRegimeEngine
from app.signals.strategies.vortex_snap.types import EventType, MarketRegime
from app.signals.strategies.vortex_snap.tests.conftest import (
    generate_flat_candles,
    generate_trending_candles,
)


class TestMarketRegimeEngine:
    def setup_method(self):
        self.comp_engine = CompressionEngine()
        self.press_engine = DirectionalPressureEngine()
        self.trans_engine = TranslationRatioEngine()
        self.regime_engine = MarketRegimeEngine()

    def test_trend_regime_detection(self):
        # 35 bars of clean trending move
        candles = generate_trending_candles(35, base_price=24000.0, step=15.0)
        comp = self.comp_engine.compute(candles)
        press = self.press_engine.compute(candles)
        trans = self.trans_engine.compute(candles, press)

        res = self.regime_engine.compute(candles, comp, press, trans)

        assert res.regime in (MarketRegime.TREND, MarketRegime.TRENDING_VOLATILITY)
        assert EventType.CONTINUATION in res.permitted_events
        assert res.efficiency_ratio > 0.60

    def test_range_regime_detection(self):
        # 35 bars of flat consolidation
        candles = generate_flat_candles(35, base_price=24000.0, bar_range=4.0)
        comp = self.comp_engine.compute(candles)
        press = self.press_engine.compute(candles)
        trans = self.trans_engine.compute(candles, press)

        res = self.regime_engine.compute(candles, comp, press, trans)

        assert res.regime in (MarketRegime.RANGE, MarketRegime.EXHAUSTION)
        assert EventType.ABSORPTION in res.permitted_events
        assert EventType.VACUUM_TRAP in res.permitted_events
