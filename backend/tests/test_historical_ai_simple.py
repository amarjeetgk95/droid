"""
Comprehensive tests for Simple Historical AI Module
Validates:
1. Exact Output Contract (JSON & schema)
2. Point-In-Time (PIT) Safety (zero lookahead)
3. Non-invention of probabilities (exact empirical frequencies)
4. Insufficient sample size behavior (INSUFFICIENT_SAMPLE)
5. Missing or stale data behavior (UNKNOWN)
6. Asynchronous execution performance (<50ms)
7. Integration with Main AI Prompt Builder
"""
from __future__ import annotations

import pytest
import time
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from app.historical_intelligence.schemas import (
    CandleData,
    HistoricalAIResult,
    HorizonProbabilities,
    ForwardOutcomeHorizon,
    HistoricalOutcomeRecord,
)
from app.historical_intelligence.state_builder import state_builder
from app.historical_intelligence.similarity_engine import SimilarityEngine
from app.historical_intelligence.outcome_engine import outcome_engine, OutcomeEngine
from app.historical_intelligence.historical_ai import HistoricalAI
from app.ai.prompt_builder import build_market_context_prompt


def _generate_synthetic_candle(
    candle_ts: datetime,
    close: float,
    ret_pts: float = 0.0,
    volume: float = 2000.0,
) -> CandleData:
    c = close + ret_pts
    o = c - (ret_pts * 0.6)
    h = max(o, c) + 3.0
    l = min(o, c) - 3.0
    return CandleData(
        timestamp_utc=int(candle_ts.timestamp() * 1000),
        open=round(o, 2),
        high=round(h, 2),
        low=round(l, 2),
        close=round(c, 2),
        volume=volume,
    )


def _build_synthetic_history(
    hist_ai: HistoricalAI,
    n_records: int = 52,
    base_time: datetime = datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc),
    bullish_ratio: float = 0.69,
    bearish_ratio: float = 0.21,
    failure_ratio: float = 0.18,
):
    """Seed Historical AI store with controlled empirical outcomes."""
    hist_ai.clear_store()

    n_bull = int(n_records * bullish_ratio)
    n_bear = int(n_records * bearish_ratio)
    n_fail = int(n_records * failure_ratio)

    for i in range(n_records):
        ts = base_time + timedelta(hours=i)
        # Create 25 bars ending exactly at ts
        candles = []
        p = 24000.0
        for b in range(25):
            p += (2.0 if b > 15 else 0.5)
            bar_ts = ts - timedelta(minutes=24 - b)
            c = _generate_synthetic_candle(bar_ts, p, ret_pts=2.0)
            candles.append(c)

        snap = state_builder.build_snapshot(
            instrument="NIFTY",
            candles=candles,
            timestamp=ts,
            timeframe="1m",
        )

        # Determine outcome according to ratio
        if i < n_bull:
            dir_15 = "BULLISH"
            dir_30 = "BULLISH" if i < int(n_records * 0.63) else "NEUTRAL"
            dir_60 = "BULLISH" if i < int(n_records * 0.57) else "BEARISH"
            ret = 0.45
        elif i < n_bull + n_bear:
            dir_15 = "BEARISH"
            dir_30 = "BEARISH"
            dir_60 = "BEARISH"
            ret = -0.35
        else:
            dir_15 = "NEUTRAL"
            dir_30 = "NEUTRAL"
            dir_60 = "NEUTRAL"
            ret = 0.02

        is_failed = (i < n_fail)

        out_rec = HistoricalOutcomeRecord(
            snapshot_id=snap.snapshot_id,
            instrument="NIFTY",
            timestamp=ts,
            entry_price=snap.feature_vector.price.vwap_distance + 24000.0,
            outcome_15m=ForwardOutcomeHorizon(
                horizon_minutes=15,
                return_pct=ret,
                direction=dir_15,
                mfe_pct=0.55 if dir_15 == "BULLISH" else 0.10,
                mae_pct=-0.15 if not is_failed else -0.40,
                high_price=24120.0,
                low_price=23970.0,
                target_hit=(dir_15 == "BULLISH" and not is_failed),
                stop_hit=is_failed,
                continuation=(dir_15 == "BULLISH" and not is_failed),
                failure=is_failed,
            ),
            outcome_30m=ForwardOutcomeHorizon(
                horizon_minutes=30,
                return_pct=ret * 0.9,
                direction=dir_30,
                mfe_pct=0.60,
                mae_pct=-0.20 if not is_failed else -0.50,
                high_price=24150.0,
                low_price=23950.0,
                target_hit=(dir_30 == "BULLISH" and not is_failed),
                stop_hit=is_failed,
                continuation=(dir_30 == "BULLISH" and not is_failed),
                failure=is_failed,
            ),
            outcome_60m=ForwardOutcomeHorizon(
                horizon_minutes=60,
                return_pct=ret * 0.8,
                direction=dir_60,
                mfe_pct=0.65,
                mae_pct=-0.25,
                high_price=24180.0,
                low_price=23920.0,
                target_hit=False,
                stop_hit=is_failed,
                continuation=(dir_60 == "BULLISH" and not is_failed),
                failure=is_failed,
            ),
            labeled_at=ts + timedelta(minutes=65),
            outcome_version="1.0.0",
        )
        hist_ai.register_snapshot_and_outcome(snap, out_rec)


def _create_mock_regime():
    """Build mock regime matching prompt_builder requirements."""
    return SimpleNamespace(
        symbol="NIFTY",
        spot_price=24500.0,
        regime_state="TRENDING_BULLISH",
        confidence_score=85.0,
        summary_headline="Bullish expansion above VWAP",
        institutional_rationale="Strong institutional buying detected",
        indicators=SimpleNamespace(
            rsi_14=62.5,
            adx_14=28.4,
            plus_di=29.0,
            minus_di=14.0,
            supertrend_direction="BULLISH",
            supertrend_value=24380.0,
            atr_14=55.0,
            bollinger_bandwidth=2.1,
            bollinger_upper=24620.0,
            bollinger_lower=24380.0,
        ),
        key_levels=SimpleNamespace(
            classic_pivots=SimpleNamespace(pivot=24450.0),
            poc=24480.0,
            vah=24560.0,
            val=24420.0,
            nearest_resistance=24600.0,
            distance_to_resistance_pts=100.0,
            nearest_support=24400.0,
            distance_to_support_pts=100.0,
        ),
        vix_regime=SimpleNamespace(
            vix_value=13.5,
            change_percent=-2.1,
            regime_category="NORMAL",
            historical_percentile=42.0,
            recommended_option_strategy="BULL_CALL_SPREAD",
        ),
    )


@pytest.fixture
def clean_hist_ai():
    ai = HistoricalAI()
    ai.clear_store()
    yield ai
    ai.clear_store()


class TestHistoricalAI:

    @pytest.mark.asyncio
    async def test_output_contract_keys_and_types(self, clean_hist_ai):
        """Verify the exact output contract structure, types, and values."""
        hist_ai = clean_hist_ai
        base_time = datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)
        _build_synthetic_history(hist_ai, n_records=52, base_time=base_time)

        # Query time strictly AFTER historical records
        query_time = base_time + timedelta(hours=60)
        query_candles = []
        p = 24000.0
        for b in range(25):
            p += 1.5
            bar_ts = query_time - timedelta(minutes=24 - b)
            query_candles.append(_generate_synthetic_candle(bar_ts, p, ret_pts=2.0))

        res: HistoricalAIResult = await hist_ai.analyze_setup(
            instrument="NIFTY",
            candles=query_candles,
            timestamp=query_time,
            prior_bias="BULLISH",
            min_samples=10,
            top_k=100,
        )

        assert isinstance(res, HistoricalAIResult)
        assert res.status == "READY"
        assert res.sample_count == 52
        assert isinstance(res.probability_15m, HorizonProbabilities)
        assert isinstance(res.probability_30m, HorizonProbabilities)
        assert isinstance(res.probability_60m, HorizonProbabilities)
        assert isinstance(res.failure_rate, float)
        assert res.confidence in ("LOW", "MEDIUM", "HIGH")
        assert isinstance(res.historical_context, str)
        assert len(res.historical_context) > 10

        # Validate JSON serialization matches requested keys
        d = res.model_dump()
        required_keys = {
            "status",
            "sample_count",
            "probability_15m",
            "probability_30m",
            "probability_60m",
            "failure_rate",
            "confidence",
            "historical_context",
        }
        for k in required_keys:
            assert k in d

        # Sub-keys for probability maps
        for horiz in ["probability_15m", "probability_30m", "probability_60m"]:
            assert "bullish" in d[horiz]
            assert "bearish" in d[horiz]
            assert "neutral" in d[horiz]
            # Probabilities sum to 1.0 (allow minor rounding tolerance 0.98 - 1.02)
            total_p = d[horiz]["bullish"] + d[horiz]["bearish"] + d[horiz]["neutral"]
            assert 0.98 <= total_p <= 1.02

        # Verify values align closely with seeded values (~69% bullish, ~21% bearish, ~18% fail)
        assert 0.60 <= res.probability_15m.bullish <= 0.75
        assert 0.15 <= res.probability_15m.bearish <= 0.28
        assert 0.12 <= res.failure_rate <= 0.22

    @pytest.mark.asyncio
    async def test_point_in_time_safety(self, clean_hist_ai):
        """
        Verify Point-In-Time (PIT) safety:
        Historical setups occurred at or after query timestamp are NEVER matched.
        """
        hist_ai = clean_hist_ai
        t0 = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
        _build_synthetic_history(hist_ai, n_records=40, base_time=t0)

        # Set query time right in the middle (at record 20)
        query_time = t0 + timedelta(hours=20)

        query_candles = []
        p = 24000.0
        for b in range(25):
            p += 1.0
            bar_ts = query_time - timedelta(minutes=24 - b)
            query_candles.append(_generate_synthetic_candle(bar_ts, p, ret_pts=1.0))

        res = await hist_ai.analyze_setup(
            instrument="NIFTY",
            candles=query_candles,
            timestamp=query_time,
            prior_bias="BULLISH",
            min_samples=5,
        )

        # Exactly 20 records exist BEFORE query_time (t0 + 0h to t0 + 19h)
        # Records at t0 + 20h, 21h, etc. MUST BE EXCLUDED!
        assert res.status == "READY"
        assert res.sample_count == 20

    @pytest.mark.asyncio
    async def test_insufficient_sample_returns_insufficient_status(self, clean_hist_ai):
        """When fewer than min_samples are found, return INSUFFICIENT_SAMPLE."""
        hist_ai = clean_hist_ai
        t0 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        # Seed only 5 records
        _build_synthetic_history(hist_ai, n_records=5, base_time=t0)

        query_time = t0 + timedelta(hours=10)
        query_candles = [
            _generate_synthetic_candle(query_time - timedelta(minutes=24 - b), 24000.0 + b)
            for b in range(25)
        ]

        res = await hist_ai.analyze_setup(
            instrument="NIFTY",
            candles=query_candles,
            timestamp=query_time,
            min_samples=10,  # Needs 10, but only 5 exist
        )

        assert res.status == "INSUFFICIENT_SAMPLE"
        assert res.sample_count == 5
        assert res.confidence == "LOW"
        assert "Insufficient" in res.historical_context
        # Probabilities must not be fabricated
        assert res.probability_15m.bullish == 0.0
        assert res.probability_15m.bearish == 0.0
        assert res.probability_15m.neutral == 0.0

    @pytest.mark.asyncio
    async def test_missing_historical_data_returns_unknown(self, clean_hist_ai):
        """When historical database is empty, return UNKNOWN (never 0 or neutral)."""
        hist_ai = clean_hist_ai
        # Store is empty
        assert hist_ai.count_historical_records() == 0

        query_time = datetime.now(timezone.utc)
        query_candles = [
            _generate_synthetic_candle(query_time - timedelta(minutes=24 - b), 24000.0 + b)
            for b in range(25)
        ]

        res = await hist_ai.analyze_setup(
            instrument="NIFTY",
            candles=query_candles,
            timestamp=query_time,
        )

        assert res.status == "UNKNOWN"
        assert res.sample_count == 0
        assert res.confidence == "UNKNOWN"
        assert "missing" in res.historical_context.lower() or "unpopulated" in res.historical_context.lower()

    @pytest.mark.asyncio
    async def test_non_invention_of_probabilities(self, clean_hist_ai):
        """
        Confirm mathematical exactness:
        If 20 matches are found with exactly 14 Bullish, 4 Bearish, 2 Neutral,
        the probabilities must be exactly 0.70, 0.20, 0.10.
        """
        hist_ai = clean_hist_ai
        t0 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        _build_synthetic_history(
            hist_ai,
            n_records=20,
            base_time=t0,
            bullish_ratio=0.70,
            bearish_ratio=0.20,
            failure_ratio=0.15,
        )

        query_time = t0 + timedelta(hours=30)
        query_candles = [
            _generate_synthetic_candle(query_time - timedelta(minutes=24 - b), 24000.0 + b)
            for b in range(25)
        ]

        res = await hist_ai.analyze_setup(
            instrument="NIFTY",
            candles=query_candles,
            timestamp=query_time,
            min_samples=10,
        )

        assert res.status == "READY"
        assert res.sample_count == 20
        # Check exact empirical match: 14/20 = 0.70, 4/20 = 0.20, 2/20 = 0.10
        assert res.probability_15m.bullish == 0.70
        assert res.probability_15m.bearish == 0.20
        assert res.probability_15m.neutral == 0.10
        assert res.failure_rate == 0.15

    @pytest.mark.asyncio
    async def test_asynchronous_performance_benchmark(self, clean_hist_ai):
        """Ensure Historical AI completes asynchronously in < 50ms without blocking."""
        hist_ai = clean_hist_ai
        t0 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        _build_synthetic_history(hist_ai, n_records=50, base_time=t0)

        query_time = t0 + timedelta(hours=60)
        query_candles = [
            _generate_synthetic_candle(query_time - timedelta(minutes=24 - b), 24000.0 + b)
            for b in range(25)
        ]

        start_t = time.perf_counter()
        res = await hist_ai.analyze_setup(
            instrument="NIFTY",
            candles=query_candles,
            timestamp=query_time,
        )
        elapsed_ms = (time.perf_counter() - start_t) * 1000

        assert res.status == "READY"
        # Should easily complete in under 50ms in-memory
        assert elapsed_ms < 50.0

    def test_main_ai_prompt_builder_integration(self):
        """Confirm Main AI prompt builder formats Historical AI evidence cleanly."""
        res = HistoricalAIResult(
            status="READY",
            sample_count=52,
            probability_15m=HorizonProbabilities(bullish=0.69, bearish=0.21, neutral=0.10),
            probability_30m=HorizonProbabilities(bullish=0.63, bearish=0.26, neutral=0.11),
            probability_60m=HorizonProbabilities(bullish=0.57, bearish=0.31, neutral=0.12),
            failure_rate=0.18,
            confidence="MEDIUM",
            historical_context="Similar historical setups generally favored bullish continuation, but the edge weakened over the 60-minute horizon.",
        )

        dummy_regime = _create_mock_regime()

        prompt = build_market_context_prompt(
            symbol="NIFTY",
            regime=dummy_regime,
            hie_evidence=res,
        )

        assert "## HISTORICAL INTELLIGENCE ENGINE" in prompt
        assert "Similar historical setups generally favored bullish continuation" in prompt
        assert "Sample Size: N=52" in prompt
        assert "15-Minute Probabilities: Bullish 69%, Bearish 21%, Neutral 10%" in prompt
        assert "30-Minute Probabilities: Bullish 63%, Bearish 26%, Neutral 11%" in prompt
        assert "60-Minute Probabilities: Bullish 57%, Bearish 31%, Neutral 12%" in prompt
        assert "Failure Rate: 18%" in prompt
