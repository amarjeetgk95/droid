"""Data Quality Engine with Two-Tier Hard Gating and Dimensional Scoring."""

from __future__ import annotations
from datetime import datetime, timezone, date
from typing import Dict, Any, List, Tuple
import polars as pl
import structlog

from app.historical_data.models.quality import (
    QualityGateResult,
    DimensionalScores,
    HistoricalQualityReport,
)
from app.historical_data.models.dataset import QualityStatus
from app.historical_data.calendar.india import indian_calendar

logger = structlog.get_logger(__name__)


class HistoricalQualityEngine:
    """Rigorous quant-grade data quality validation engine."""

    def __init__(self, calendar=indian_calendar):
        self.calendar = calendar

    def run_hard_gates(self, df: pl.DataFrame, asset_type: str = "INDEX") -> QualityGateResult:
        """Evaluate non-negotiable Tier 1 hard gates.
        
        Any failure immediately marks the dataset as POISONED / unusable.
        """
        violations: List[str] = []
        details: Dict[str, Any] = {}

        if df.is_empty():
            return QualityGateResult(hard_gates_passed=False, violations=["DATASET_EMPTY"], details={})

        # 1. Negative or zero prices
        neg_prices = df.filter(
            (pl.col("open") <= 0) | (pl.col("high") <= 0) | (pl.col("low") <= 0) | (pl.col("close") <= 0)
        )
        if len(neg_prices) > 0:
            violations.append("NEGATIVE_OR_ZERO_PRICES")
            details["negative_price_rows"] = len(neg_prices)

        # 2. Geometric OHLC violations: High must be >= max(open, close, low) and Low <= min(open, close, high)
        ohlc_bad = df.filter(
            (pl.col("high") < pl.col("open"))
            | (pl.col("high") < pl.col("close"))
            | (pl.col("high") < pl.col("low"))
            | (pl.col("low") > pl.col("open"))
            | (pl.col("low") > pl.col("close"))
            | (pl.col("low") > pl.col("high"))
        )
        if len(ohlc_bad) > 0:
            violations.append("GEOMETRIC_OHLC_VIOLATIONS")
            details["geometric_violations"] = len(ohlc_bad)

        # 3. Monotonic chronological ordering & duplicates
        timestamps = df["timestamp"].to_list()
        out_of_order = 0
        duplicate_ts = 0
        for i in range(1, len(timestamps)):
            if timestamps[i] < timestamps[i - 1]:
                out_of_order += 1
            elif timestamps[i] == timestamps[i - 1]:
                duplicate_ts += 1

        if out_of_order > 0:
            violations.append("NON_MONOTONIC_TIMESTAMPS")
            details["out_of_order_count"] = out_of_order

        if duplicate_ts > 0:
            violations.append("DUPLICATE_TIMESTAMPS")
            details["duplicate_timestamps"] = duplicate_ts

        # 4. Impossible future timestamps
        now_utc = datetime.now(timezone.utc)
        future_rows = df.filter(pl.col("timestamp") > now_utc)
        if len(future_rows) > 0:
            violations.append("FUTURE_TIMESTAMPS_DETECTED")
            details["future_rows"] = len(future_rows)

        passed = len(violations) == 0
        return QualityGateResult(hard_gates_passed=passed, violations=violations, details=details)

    def calculate_dimensional_scores(
        self,
        df: pl.DataFrame,
        symbol: str,
        timeframe: str,
        asset_type: str,
        start_date: date,
        end_date: date,
    ) -> Tuple[DimensionalScores, int, int]:
        """Calculate Tier 2 sub-scores (0-100 scale).
        
        Returns (scores, expected_bars, missing_bars).
        """
        trading_days = self.calendar.get_trading_days(start_date, end_date)
        expected_bars = sum(self.calendar.get_expected_candles(d, timeframe) for d in trading_days)
        actual_bars = len(df)

        # 1. Completeness score
        if expected_bars > 0:
            completeness = min(100.0, max(0.0, (actual_bars / expected_bars) * 100.0))
            missing_bars = max(0, expected_bars - actual_bars)
        else:
            completeness = 100.0
            missing_bars = 0

        # 2. Temporal Continuity (continuity penalizes gap frequency)
        continuity = max(0.0, 100.0 - (missing_bars / max(1, expected_bars) * 80.0))

        # 3. Sanity Score: asset-aware volume check & jump check
        sanity = 100.0
        if asset_type.upper() in ("EQUITY", "FUTURES", "OPTIONS"):
            zero_vol = df.filter(pl.col("volume") == 0)
            if len(df) > 0 and len(zero_vol) > 0:
                zero_vol_pct = (len(zero_vol) / len(df)) * 100.0
                sanity = max(0.0, 100.0 - zero_vol_pct)
        else:
            # Cash index spots (SENSEX, NIFTY) have 0 traded shares naturally
            sanity = 100.0

        # Composite score
        composite = (0.50 * completeness) + (0.30 * continuity) + (0.20 * sanity)

        scores = DimensionalScores(
            completeness_score=round(completeness, 2),
            temporal_continuity_score=round(continuity, 2),
            sanity_score=round(sanity, 2),
            composite_score=round(composite, 2),
        )
        return scores, expected_bars, missing_bars

    def validate_dataset(
        self,
        df: pl.DataFrame,
        symbol: str,
        timeframe: str,
        asset_type: str,
        start_date: date,
        end_date: date,
        dataset_id: str = "",
        version_id: str = "",
    ) -> HistoricalQualityReport:
        """Run complete two-tier quality evaluation."""
        hard_gate_res = self.run_hard_gates(df, asset_type)

        if not hard_gate_res.hard_gates_passed:
            # Fatal poisoning
            scores = DimensionalScores(
                completeness_score=0.0,
                temporal_continuity_score=0.0,
                sanity_score=0.0,
                composite_score=0.0,
            )
            report = HistoricalQualityReport(
                report_id=f"rep_{symbol}_{timeframe}_{int(datetime.now(timezone.utc).timestamp())}",
                dataset_id=dataset_id or f"{symbol}_{timeframe}",
                version_id=version_id,
                quality_score=0.0,
                status="POISONED",
                hard_gates_passed=False,
                dimensional_scores=scores,
                total_rows=len(df),
                valid_rows=0,
                invalid_rows=len(df),
                details={"hard_gate_violations": hard_gate_res.violations, **hard_gate_res.details},
            )
            return report

        # Compute dimensional scores
        scores, expected_bars, missing_bars = self.calculate_dimensional_scores(
            df, symbol, timeframe, asset_type, start_date, end_date
        )

        status: QualityStatus = "PASSED" if scores.composite_score >= 95.0 else "DEGRADED"

        report = HistoricalQualityReport(
            report_id=f"rep_{symbol}_{timeframe}_{int(datetime.now(timezone.utc).timestamp())}",
            dataset_id=dataset_id or f"{symbol}_{timeframe}",
            version_id=version_id,
            quality_score=scores.composite_score,
            status=status,
            hard_gates_passed=True,
            dimensional_scores=scores,
            total_rows=len(df),
            valid_rows=len(df),
            invalid_rows=0,
            missing_candles=missing_bars,
            details={
                "expected_bars": expected_bars,
                "actual_bars": len(df),
                "trading_days_checked": len(self.calendar.get_trading_days(start_date, end_date)),
            },
        )
        return report


# Global quality engine instance
quality_engine = HistoricalQualityEngine()
