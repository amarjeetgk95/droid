"""
Unit tests for Structural Level Engine (§5).
"""
import pytest
from app.signals.strategies.vortex_snap.features.structural_levels import StructuralLevelEngine
from app.signals.strategies.vortex_snap.types import LevelType
from app.signals.strategies.vortex_snap.tests.conftest import create_candle


class TestStructuralLevelEngine:
    def setup_method(self):
        self.engine = StructuralLevelEngine()

    def test_nearest_support_and_resistance(self):
        # Current price = 24100
        candles = [
            create_candle(1000 + i * 60000, 24090, 24105, 24085, 24100)
            for i in range(20)
        ]
        res = self.engine.compute(
            candles_1m=candles,
            pdh=24200.0,
            pdl=24000.0,
            pdc=24050.0,
            cdo=24080.0,
            orh=24150.0,
            orl=24020.0,
            vwap=24090.0,
        )

        assert res.nearest_resistance is not None
        assert res.nearest_support is not None
        # Resistances are > 24100: nearest is SESSION_HIGH at 24105 (since candle high is 24105)
        assert res.nearest_resistance.price == 24105.0
        assert res.nearest_resistance.level_type == LevelType.SESSION_HIGH
        # Supports are < 24100: nearest is VWAP at 24090
        assert res.nearest_support.price == 24090.0
        assert res.nearest_support.level_type == LevelType.VWAP
        assert res.distance_to_nearest_resistance == 5.0
        assert res.distance_to_nearest_support == 10.0

    def test_distance_decay_relevance_score(self):
        # Far level should have lower relevance score than close level
        candles = [
            create_candle(1000 + i * 60000, 24100, 24105, 24095, 24100)
            for i in range(10)
        ]
        res = self.engine.compute(
            candles_1m=candles,
            pdh=25000.0,  # 900 pts away
            pdl=24110.0,  # 10 pts away
        )
        pdh_lvl = next(l for l in res.levels if l.level_type == LevelType.PDH)
        pdl_lvl = next(l for l in res.levels if l.level_type == LevelType.PDL)

        assert pdl_lvl.relevance_score > pdh_lvl.relevance_score

    def test_retest_and_touch_detection(self):
        # Price touching and retesting level at 24200
        candles = [
            create_candle(1000, 24180, 24202, 24175, 24198),
            create_candle(61000, 24198, 24205, 24190, 24195),
            create_candle(121000, 24195, 24201, 24188, 24200),
        ]
        res = self.engine.compute(
            candles_1m=candles,
            pdh=24200.0,
        )
        pdh_lvl = next(l for l in res.levels if l.level_type == LevelType.PDH)
        assert pdh_lvl.touch_count >= 1
        assert pdh_lvl.is_retested
