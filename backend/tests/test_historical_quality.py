"""Tests for Data Quality Engine (Hard Gates & Zero-Volume Index Rules)."""

from datetime import date, datetime, timezone, timedelta
import polars as pl
from app.historical_data.validation.quality_engine import HistoricalQualityEngine
from app.historical_data.validation.gap_detector import HistoricalGapDetector


def _make_dummy_candles(n: int = 375, base_price: float = 80000.0, volume: float = 0.0) -> pl.DataFrame:
    base_ts = datetime(2024, 6, 5, 3, 45, tzinfo=timezone.utc)  # 09:15 IST
    ts_list = [base_ts + timedelta(minutes=i) for i in range(n)]

    return pl.DataFrame({
        "timestamp": pl.Series("timestamp", ts_list, dtype=pl.Datetime("ms", "UTC")),
        "symbol": ["SENSEX"] * n,
        "exchange": ["BSE"] * n,
        "asset_type": ["INDEX"] * n,
        "timeframe": ["1m"] * n,
        "open": [base_price + i for i in range(n)],
        "high": [base_price + i + 2.0 for i in range(n)],
        "low": [base_price + i - 1.0 for i in range(n)],
        "close": [base_price + i + 1.0 for i in range(n)],
        "volume": [volume] * n,
        "provider": ["fyers"] * n,
        "ingestion_job_id": ["test"] * n,
        "data_version": ["v1"] * n,
    })


def test_quality_hard_gates_pass():
    engine = HistoricalQualityEngine()
    df = _make_dummy_candles(375, 80000.0, volume=0.0)

    res = engine.run_hard_gates(df, asset_type="INDEX")
    assert res.hard_gates_passed is True
    assert len(res.violations) == 0


def test_quality_hard_gates_fail_on_geometric_violation():
    """Verify that High < Low immediately fails hard gates and poisons the dataset."""
    engine = HistoricalQualityEngine()
    df = _make_dummy_candles(10, 80000.0)

    # Corrupt one candle: High < Low
    corrupted_df = df.with_columns(
        pl.when(pl.col("open") == 80000.0)
        .then(pl.lit(70000.0))  # High lower than Low
        .otherwise(pl.col("high"))
        .alias("high")
    )

    res = engine.run_hard_gates(corrupted_df, asset_type="INDEX")
    assert res.hard_gates_passed is False
    assert "GEOMETRIC_OHLC_VIOLATIONS" in res.violations


def test_quality_hard_gates_fail_on_negative_price():
    engine = HistoricalQualityEngine()
    df = _make_dummy_candles(10, 80000.0)

    corrupted_df = df.with_columns(
        pl.when(pl.col("open") == 80000.0)
        .then(pl.lit(-50.0))
        .otherwise(pl.col("low"))
        .alias("low")
    )

    res = engine.run_hard_gates(corrupted_df, asset_type="INDEX")
    assert res.hard_gates_passed is False
    assert "NEGATIVE_OR_ZERO_PRICES" in res.violations


def test_sensex_zero_volume_is_not_penalized():
    """Verify that SENSEX index spot with volume=0 scores 100% sanity."""
    engine = HistoricalQualityEngine()
    trading_day = date(2024, 6, 5)
    df = _make_dummy_candles(375, 80000.0, volume=0.0)

    report = engine.validate_dataset(
        df=df,
        symbol="SENSEX",
        timeframe="1m",
        asset_type="INDEX",
        start_date=trading_day,
        end_date=trading_day,
    )

    assert report.hard_gates_passed is True
    assert report.status == "PASSED"
    assert report.dimensional_scores.sanity_score == 100.0
    assert report.dimensional_scores.completeness_score == 100.0
    assert report.quality_score == 100.0


def test_gap_detector_identifies_missing_bars():
    detector = HistoricalGapDetector()
    trading_day = date(2024, 6, 5)

    # Supply only 370 of 375 bars (5 missing)
    df = _make_dummy_candles(370, 80000.0, volume=0.0)

    gaps = detector.detect_gaps(
        df=df,
        dataset_id="SENSEX_1M",
        start_date=trading_day,
        end_date=trading_day,
        timeframe="1m",
    )

    assert len(gaps) == 1
    assert gaps[0].expected_candles == 375
    assert gaps[0].actual_candles == 370
    assert gaps[0].missing_candles == 5
    assert gaps[0].status == "OPEN"
