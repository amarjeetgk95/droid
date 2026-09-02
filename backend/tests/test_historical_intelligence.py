import pytest
import math
from app.quant.historical_intelligence.models import CandleData, MarketRegime
from app.quant.historical_intelligence.data_validator import (
    validate_single_candle, validate_and_clean_candle_series, has_complete_forward_window
)
from app.quant.historical_intelligence.feature_extractor import extract_features
from app.quant.historical_intelligence.regime_classifier import classify_regime, are_regimes_compatible
from app.quant.historical_intelligence.similarity import (
    cosine_similarity, pearson_correlation, fast_dtw_similarity, compute_composite_similarity
)
from app.quant.historical_intelligence.outcome_engine import compute_forward_outcomes
from app.quant.historical_intelligence.analog_selector import find_historical_analogs
from app.quant.historical_intelligence.support_resistance import detect_support_resistance_zones


def _mock_candle(i: int, o: float, h: float, l: float, c: float, v: float = 1000.0) -> CandleData:
    return CandleData(
        timestamp_utc=1772605200000 + (i * 300000),  # 5-min steps
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
    )


class TestHistoricalIntelligenceEngine:

    def test_data_validator_rules(self):
        # 1. Invalid OHLC bounds
        bad_c = _mock_candle(0, o=100.0, h=90.0, l=80.0, c=85.0)  # High < Open
        ok, err = validate_single_candle(bad_c)
        assert not ok
        assert "high (90.0) < low" in err or "open (100.0) out of bounds" in err

        # 2. Valid candle
        good_c = _mock_candle(0, o=100.0, h=105.0, l=95.0, c=102.0, v=5000.0)
        ok, err = validate_single_candle(good_c)
        assert ok
        assert err is None

        # 3. Series deduplication and ordering
        dup_c1 = _mock_candle(1, 100, 105, 95, 102)
        dup_c2 = _mock_candle(1, 100, 105, 95, 102)  # Duplicate ts
        c3 = _mock_candle(2, 102, 108, 101, 106)

        series = [c3, dup_c1, dup_c2]  # Unordered with duplicate
        res = validate_and_clean_candle_series(series, min_bars=2)
        assert res.is_valid
        assert len(res.cleaned_candles) == 2
        assert res.cleaned_candles[0].timestamp_utc < res.cleaned_candles[1].timestamp_utc

    def test_feature_extraction_and_regimes(self):
        # Bullish upward expansion series
        candles = []
        p = 24000.0
        for i in range(15):
            o = p
            c = p + 20.0
            h = c + 5.0
            l = o - 3.0
            candles.append(_mock_candle(i, o, h, l, c, v=2000.0 + i * 500))
            p = c

        features = extract_features(candles)
        assert features.total_return_pct > 0.5
        assert features.trend_direction == "UP"
        assert features.consecutive_bullish >= 10
        assert features.relative_volume > 1.0

        regime = classify_regime(features)
        assert regime in (MarketRegime.TRENDING_UP, MarketRegime.BREAKOUT, MarketRegime.VOLATILITY_EXPANSION)

    def test_multi_metric_similarity_and_dtw(self):
        # 1. Identical patterns should have near 1.0 similarity
        v1 = [0.0, 0.2, 0.5, 0.8, 1.2, 1.5]
        v2 = [0.0, 0.2, 0.5, 0.8, 1.2, 1.5]
        cos_sim = cosine_similarity(v1, v2)
        dtw_sim = fast_dtw_similarity(v1, v2)
        assert cos_sim > 0.99
        assert dtw_sim > 0.99

        # 2. Inverted patterns should have low similarity
        v_inv = [0.0, -0.2, -0.5, -0.8, -1.2, -1.5]
        cos_inv = cosine_similarity(v1, v_inv)
        assert cos_inv < 0.2

    def test_forward_outcomes_and_same_candle_ambiguity(self):
        # 1. Normal Bullish Expansion (Target hit before stop)
        entry_p = 24900.0
        forward = [
            _mock_candle(0, 24905, 24950, 24895, 24940),
            _mock_candle(1, 24940, 25050, 24930, 25040),  # Hits target +0.5% (25024.5)
        ]
        out = compute_forward_outcomes(forward, entry_price=entry_p, target_pct=0.50, stop_pct=0.25)
        assert out.target_hit is True
        assert out.stop_hit is False
        assert out.mfe_pct > 0.50
        assert out.time_to_target_bars == 2

        # 2. Same-candle ambiguity test (§52) — High exceeds target, Low breaches stop in SAME bar
        wild_bar = [_mock_candle(0, 24900, 25100, 24700, 24900)]  # Massive range
        out_wild = compute_forward_outcomes(wild_bar, entry_price=entry_p, target_pct=0.50, stop_pct=0.25)
        # Conservative rule requires Stop Hit first
        assert out_wild.stop_hit is True
        assert out_wild.target_hit is False

    def test_support_resistance_detection(self):
        # Create series with repeated touches at 24900 and 25000
        candles = []
        for i in range(40):
            if i % 10 == 0:
                candles.append(_mock_candle(i, 24910, 25000, 24900, 24995))  # High touch at 25000
            elif i % 10 == 5:
                candles.append(_mock_candle(i, 24980, 24990, 24900, 24910))  # Low touch at 24900
            else:
                candles.append(_mock_candle(i, 24940, 24960, 24930, 24950))

        zones = detect_support_resistance_zones(candles, oi_call_walls=[25000.0], oi_put_walls=[24900.0])
        assert len(zones) >= 1
        centers = [z.zone_center for z in zones]
        assert any(abs(c - 25000.0) < 20.0 or abs(c - 24900.0) < 20.0 for c in centers)
        assert any(z.is_oi_wall for z in zones)

    def test_lookahead_bias_protection(self):
        """
        Verify that for analog search at timestamp T, no future candles are used in feature extraction.
        """
        all_candles = []
        p = 24000.0
        for i in range(60):
            all_candles.append(_mock_candle(i, p, p + 15, p - 10, p + 10))
            p += 10.0

        current_window = all_candles[-15:]
        summary = find_historical_analogs(
            all_candles=all_candles,
            current_window_candles=current_window,
            symbol="NIFTY",
            timeframe="5M",
            top_k=5,
            forward_horizon_bars=10,
        )

        current_end_ts = current_window[-1].timestamp_utc
        # Assert no analog matched beyond the lookahead boundary
        for analog in summary.top_analogs:
            assert analog.pattern_end_ts < current_end_ts
            assert len(analog.forward_returns) == 10
