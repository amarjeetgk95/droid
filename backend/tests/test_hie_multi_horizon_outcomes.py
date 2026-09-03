"""
Tests for Multi-Horizon Forward Outcomes, Same-Candle Resolution, and Statistical Reliability — §§11, 15, 16, 20, 21
"""
import pytest
from datetime import datetime, timezone
from app.historical_intelligence.schemas import (
    CandleData,
    HistoricalAnalogMatch,
    ForwardOutcomeHorizon,
    SimilarityBreakdown,
    MarketRegime,
    SessionPhase,
    SampleReliability,
)
from app.historical_intelligence.outcome_engine import compute_horizon_outcome
from app.historical_intelligence.statistics import (
    calculate_wilson_ci,
    calculate_effective_sample_size,
    classify_sample_reliability,
    compute_horizon_statistics,
)


def _candle(i: int, o: float, h: float, l: float, c: float) -> CandleData:
    return CandleData(
        timestamp_utc=1772605200000 + i * 60000,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=1000.0,
    )


class TestHIEMultiHorizonOutcomes:

    def test_conservative_same_candle_ambiguity(self):
        # Entry at 25000. Target +0.5% (25125), Stop -0.25% (24937.5)
        # Bar with massive range breaching BOTH levels in same bar
        wild_bar = [_candle(0, 25000, 25200, 24800, 25050)]
        outcome = compute_horizon_outcome(
            forward_candles=wild_bar,
            entry_price=25000.0,
            horizon_minutes=15,
            target_pct=0.50,
            stop_pct=0.25,
            prior_bias="BULLISH",
        )
        # Conservative execution rule (§52): Stop must take precedence
        assert outcome.stop_hit is True
        assert outcome.target_hit is False
        assert outcome.duration_bars == 1

    def test_clean_target_hit_progression(self):
        entry = 25000.0
        # Bar 1: inside range
        # Bar 2: hits target cleanly (high 25150 >= 25125) without touching stop
        candles = [
            _candle(0, 25000, 25050, 24980, 25040),
            _candle(1, 25040, 25150, 25020, 25130),
        ]
        outcome = compute_horizon_outcome(
            forward_candles=candles,
            entry_price=entry,
            horizon_minutes=15,
            target_pct=0.50,
            stop_pct=0.25,
            prior_bias="BULLISH",
        )
        assert outcome.target_hit is True
        assert outcome.stop_hit is False
        assert outcome.duration_bars == 2
        assert outcome.mfe_pct >= 0.50
        assert outcome.continuation is True

    def test_wilson_confidence_interval(self):
        # 1. 0 successes out of 10
        ci_zero = calculate_wilson_ci(0, 10)
        assert ci_zero.lower >= 0.0
        assert ci_zero.point_estimate == 0.0
        assert ci_zero.upper > 0.0

        # 2. 70 successes out of 100
        ci_70 = calculate_wilson_ci(70, 100)
        assert ci_70.point_estimate == 0.70
        assert 0.60 < ci_70.lower < 0.70
        assert 0.70 < ci_70.upper < 0.80

    def test_effective_sample_size(self):
        # Equal weights: ESS equals N
        equal_w = [1.0] * 50
        ess_equal = calculate_effective_sample_size(equal_w)
        assert pytest.approx(ess_equal, rel=1e-2) == 50.0

        # Highly skewed weights: ESS is significantly lower than N
        skewed_w = [10.0] + [0.1] * 49
        ess_skewed = calculate_effective_sample_size(skewed_w)
        assert ess_skewed < 25.0

    def test_minimum_sample_policy_thresholds(self):
        assert classify_sample_reliability(5) == SampleReliability.INSUFFICIENT
        assert classify_sample_reliability(9) == SampleReliability.INSUFFICIENT
        assert classify_sample_reliability(10) == SampleReliability.LOW_CONFIDENCE
        assert classify_sample_reliability(24) == SampleReliability.LOW_CONFIDENCE
        assert classify_sample_reliability(25) == SampleReliability.MODERATE
        assert classify_sample_reliability(49) == SampleReliability.MODERATE
        assert classify_sample_reliability(50) == SampleReliability.GOOD
        assert classify_sample_reliability(99) == SampleReliability.GOOD
        assert classify_sample_reliability(100) == SampleReliability.HIGH_SAMPLE
        assert classify_sample_reliability(250) == SampleReliability.HIGH_SAMPLE

    def test_horizon_statistics_aggregation(self):
        # Create 10 synthetic matches with outcomes
        matches = []
        dummy_bd = SimilarityBreakdown(
            embedding_similarity=0.8, regime_similarity=0.8, volatility_similarity=0.8,
            session_similarity=0.8, structure_similarity=0.8, market_context_similarity=0.8,
            final_similarity=0.8,
        )

        for i in range(20):
            is_bull = (i % 4 != 0)  # 75% bullish
            dir_str = "BULLISH" if is_bull else "BEARISH"
            ret = 0.35 if is_bull else -0.30

            out_15 = ForwardOutcomeHorizon(
                horizon_minutes=15, return_pct=ret, direction=dir_str,
                mfe_pct=0.4, mae_pct=-0.1, high_price=25100, low_price=24950,
                target_hit=is_bull, stop_hit=not is_bull, duration_bars=5,
                continuation=is_bull, failure=not is_bull, reversal=False,
            )
            out_30 = ForwardOutcomeHorizon(
                horizon_minutes=30, return_pct=ret * 1.2, direction=dir_str,
                mfe_pct=0.6, mae_pct=-0.15, high_price=25150, low_price=24900,
                target_hit=is_bull, stop_hit=not is_bull, duration_bars=8,
                continuation=is_bull, failure=not is_bull, reversal=False,
            )
            out_60 = ForwardOutcomeHorizon(
                horizon_minutes=60, return_pct=ret * 1.5, direction=dir_str,
                mfe_pct=0.8, mae_pct=-0.2, high_price=25200, low_price=24850,
                target_hit=is_bull, stop_hit=not is_bull, duration_bars=12,
                continuation=is_bull, failure=not is_bull, reversal=False,
            )

            m = HistoricalAnalogMatch(
                snapshot_id=f"snap_{i}",
                instrument="NIFTY",
                timeframe="1m",
                timestamp=datetime.now(timezone.utc),
                similarity_score=0.80,
                breakdown=dummy_bd,
                matched_regime=MarketRegime.TRENDING_BULLISH,
                session_phase=SessionPhase.MID_SESSION,
                outcome_15m=out_15,
                outcome_30m=out_30,
                outcome_60m=out_60,
                temporal_weight=1.0,
            )
            matches.append(m)

        stat_15 = compute_horizon_statistics(matches, 15)
        stat_30 = compute_horizon_statistics(matches, 30)

        assert stat_15.bullish_probability == 0.75
        assert stat_15.target_hit_rate == 0.75
        assert stat_15.stop_hit_rate == 0.25
        assert stat_15.confidence_interval_bullish.lower > 0.50
        assert stat_15.median_return > 0.0

        assert stat_30.horizon_minutes == 30
        assert stat_30.bullish_probability == 0.75
