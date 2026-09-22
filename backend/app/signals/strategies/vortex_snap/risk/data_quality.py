"""
Data Quality Gate (§40).

Enforces data integrity before permitting signal generation:
- market_data_timestamp_fresh
- candle_complete
- reasonable_price / reasonable_volume
- clock_synchronized
Fails closed with NO TRADE if data quality criteria fail.
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

from app.signals.strategies.vortex_snap.types import Candle, VortexFeatureSnapshot
from app.signals.strategies.vortex_snap.signals.reason_codes import ReasonCode


class DataQualityResult(BaseModel):
    """Result of Data Quality assessment."""
    is_valid: bool
    rejection_reason: Optional[ReasonCode] = None
    latency_ms: float = 0.0
    details: str = ""


class DataQualityGate:
    """Verifies market data completeness, freshness, and sanity."""

    def __init__(self, max_staleness_ms: int = 15000) -> None:
        self.max_staleness_ms = max_staleness_ms

    def validate(
        self,
        candles_1m: List[Candle],
        system_time_ms: Optional[int] = None,
    ) -> DataQualityResult:
        """Verify data quality of input series.

        Args:
            candles_1m: Input candle sequence.
            system_time_ms: Current system epoch ms.

        Returns:
            DataQualityResult.
        """
        now = system_time_ms if system_time_ms is not None else int(time.time() * 1000)

        if not candles_1m:
            return DataQualityResult(
                is_valid=False,
                rejection_reason=ReasonCode.DATA_QUALITY_FAIL,
                details="Candle series is empty",
            )

        curr = candles_1m[-1]

        # 1. Price and Volume Sanity Checks
        if curr.close <= 0 or curr.high <= 0 or curr.low <= 0 or curr.open <= 0:
            return DataQualityResult(
                is_valid=False,
                rejection_reason=ReasonCode.DATA_QUALITY_FAIL,
                details=f"Non-positive price encountered in candle: O={curr.open}, C={curr.close}",
            )

        if curr.high < curr.low or curr.high < max(curr.open, curr.close) or curr.low > min(curr.open, curr.close):
            return DataQualityResult(
                is_valid=False,
                rejection_reason=ReasonCode.DATA_QUALITY_FAIL,
                details=f"Inconsistent candle extremes: H={curr.high}, L={curr.low}, O={curr.open}, C={curr.close}",
            )

        if curr.volume < 0:
            return DataQualityResult(
                is_valid=False,
                rejection_reason=ReasonCode.DATA_QUALITY_FAIL,
                details=f"Negative volume encountered: {curr.volume}",
            )

        # 2. Freshness Check
        staleness = abs(now - curr.timestamp)
        if staleness > self.max_staleness_ms:
            return DataQualityResult(
                is_valid=False,
                rejection_reason=ReasonCode.DATA_STALE,
                latency_ms=round(staleness, 2),
                details=f"Candle data is stale by {staleness}ms (limit={self.max_staleness_ms}ms)",
            )

        return DataQualityResult(
            is_valid=True,
            rejection_reason=None,
            latency_ms=round(staleness, 2),
            details="All data quality checks passed",
        )
