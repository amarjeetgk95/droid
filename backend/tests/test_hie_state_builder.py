"""
Tests for Historical State Builder & PIT Integrity — §§4, 5, 6, 7, 34
"""
import pytest
import math
from datetime import datetime, timezone, timedelta
from app.historical_intelligence.schemas import (
    CandleData,
    MarketRegime,
    VolatilityRegime,
    SessionPhase,
)
from app.historical_intelligence.state_builder import (
    state_builder,
    validate_candle_integrity,
    derive_session_phase,
    derive_regimes,
)
from app.historical_intelligence.feature_adapter import adapt_market_features
from app.historical_intelligence.normalizer import normalize_features
from app.historical_intelligence.embedding import embedding_generator, EMBEDDING_DIM


def _make_candle(i: int, o: float, h: float, l: float, c: float, v: float = 1000.0, base_ts: int = 1772605200000) -> CandleData:
    return CandleData(
        timestamp_utc=base_ts + (i * 60000),  # 1-minute steps
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
    )


class TestHistoricalStateBuilder:

    def test_candle_data_integrity_validation(self):
        # 1. Negative prices
        bad1 = _make_candle(0, -100, 105, 95, 102)
        ok, err = validate_candle_integrity(bad1)
        assert not ok
        assert "Negative or zero" in err

        # 2. High < Low
        bad2 = _make_candle(0, 100, 90, 95, 92)
        ok, err = validate_candle_integrity(bad2)
        assert not ok
        assert "High (90.0) < Low (95.0)" in err

        # 3. Open out of [Low, High]
        bad3 = _make_candle(0, 110, 105, 95, 100)
        ok, err = validate_candle_integrity(bad3)
        assert not ok
        assert "Open (110.0) outside" in err

        # 4. Valid candle
        good = _make_candle(0, 100, 105, 95, 102, 5000)
        ok, err = validate_candle_integrity(good)
        assert ok
        assert err is None

    def test_session_phase_derivation(self):
        # 09:20 IST = Market Open
        # 09:20 IST is 03:50 UTC
        ts_open = datetime(2026, 3, 4, 3, 50, tzinfo=timezone.utc)
        phase, min_sess = derive_session_phase(ts_open)
        assert phase == SessionPhase.MARKET_OPEN
        assert 0 <= min_sess <= 30

        # 12:00 IST = Mid Session (06:30 UTC)
        ts_mid = datetime(2026, 3, 4, 6, 30, tzinfo=timezone.utc)
        phase_mid, _ = derive_session_phase(ts_mid)
        assert phase_mid == SessionPhase.MID_SESSION

        # 15:15 IST = Closing Phase (09:45 UTC)
        ts_close = datetime(2026, 3, 4, 9, 45, tzinfo=timezone.utc)
        phase_close, _ = derive_session_phase(ts_close)
        assert phase_close == SessionPhase.CLOSING_PHASE

    def test_feature_adaptation_and_normalization(self):
        candles = []
        p = 24000.0
        for i in range(25):
            o = p
            c = p + 15.0
            h = c + 5.0
            l = o - 4.0
            candles.append(_make_candle(i, o, h, l, c, v=2000.0 + i * 100))
            p = c

        features = adapt_market_features(candles, vix_val=15.5)
        assert features.price.returns > 0.0
        assert features.candle.range_pts > 0.0
        assert features.volume_vol.atr > 0.0
        assert features.trend.rsi > 50.0

        # Normalization
        norm = normalize_features(features)
        assert len(norm.dense_vector) > 30
        assert all(not math.isnan(x) for x in norm.dense_vector)
        # Verify clamped values
        assert all(-5.0 <= x <= 5.0 for x in norm.dense_vector)

    def test_embedding_generator_unit_norm(self):
        candles = [_make_candle(i, 100 + i, 105 + i, 98 + i, 103 + i) for i in range(20)]
        features = adapt_market_features(candles)
        norm = normalize_features(features)

        emb = embedding_generator.generate_embedding(norm)
        assert len(emb) == EMBEDDING_DIM
        # Check L2 unit norm sum(x^2) approx 1.0
        l2_sum = sum(x * x for x in emb)
        assert math.isclose(l2_sum, 1.0, rel_tol=1e-3)

    def test_state_builder_lookahead_prevention(self):
        # Candle timestamp in future relative to snapshot timestamp
        now = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)
        now_ms = int(now.timestamp() * 1000)

        # Candle timestamp is 10 minutes ahead of snapshot
        bad_candle = [_make_candle(0, 100, 105, 95, 102, base_ts=now_ms + 600000)]

        with pytest.raises(ValueError, match="Lookahead detected"):
            state_builder.build_snapshot(
                instrument="NIFTY",
                candles=bad_candle,
                timestamp=now,
            )

    def test_valid_state_builder_construction(self):
        base_dt = datetime(2026, 3, 4, 6, 0, tzinfo=timezone.utc)
        base_ms = int(base_dt.timestamp() * 1000)
        candles = [_make_candle(i, 24500 + i * 2, 24510 + i * 2, 24495 + i * 2, 24505 + i * 2, base_ts=base_ms - (35 * 60000)) for i in range(30)]

        snapshot = state_builder.build_snapshot(
            instrument="NIFTY",
            candles=candles,
            timestamp=base_dt,
            timeframe="1m",
            vix=14.5,
        )

        assert snapshot.instrument == "NIFTY"
        assert snapshot.timeframe == "1m"
        assert snapshot.feature_version == "1.0.0"
        assert len(snapshot.embedding) == EMBEDDING_DIM
        assert snapshot.data_quality_score == 1.0
