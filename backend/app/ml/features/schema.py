"""Canonical Point-in-Time Feature Schema V3 (f28-v3) for DROID ML Engine.

Implements Section 9 of the DROID ML Production & Research Specification.
All features adhere to the fundamental invariant:
    data_timestamp <= feature_timestamp
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple
from pydantic import BaseModel, Field

FEATURE_SCHEMA_V3 = "f28-v3"

FEATURE_NAMES_V3: List[str] = [
    # 1. Price & Candle Structure (10)
    "ret_1m",
    "ret_3m",
    "ret_5m",
    "ret_15m",
    "atr_14",
    "atr_percentile",
    "range_expansion_ratio",
    "body_to_range_ratio",
    "upper_wick_ratio",
    "lower_wick_ratio",

    # 2. Trend & Market Structure (5)
    "vwap_distance_pct",
    "ema_alignment_score",
    "supertrend_direction",
    "adx_14",
    "trend_persistence_score",

    # 3. Volatility Context (4)
    "realized_vol_15m",
    "vix_level",
    "vix_normalized",
    "vol_expansion_flag",

    # 4. F&O Context & Microstructure (5)
    "pcr_oi",
    "pcr_oi_change",
    "oi_imbalance_ratio",
    "atm_iv",
    "spread_bps",

    # 5. Session & Expiry Dynamics (4)
    "minutes_since_open",
    "minutes_to_close",
    "days_to_expiry",
    "is_expiry_day",
]

assert len(FEATURE_NAMES_V3) == 28, f"FEATURE_NAMES_V3 width must be exactly 28, got {len(FEATURE_NAMES_V3)}"

# Safe neutral imputations when auxiliary feeds are offline / degraded
NEUTRAL_IMPUTE_V3: Dict[str, float] = {
    "ret_1m": 0.0,
    "ret_3m": 0.0,
    "ret_5m": 0.0,
    "ret_15m": 0.0,
    "atr_14": 20.0,
    "atr_percentile": 50.0,
    "range_expansion_ratio": 1.0,
    "body_to_range_ratio": 0.5,
    "upper_wick_ratio": 0.25,
    "lower_wick_ratio": 0.25,
    "vwap_distance_pct": 0.0,
    "ema_alignment_score": 0.0,
    "supertrend_direction": 0.0,
    "adx_14": 20.0,
    "trend_persistence_score": 0.0,
    "realized_vol_15m": 0.12,
    "vix_level": 14.0,
    "vix_normalized": 0.50,
    "vol_expansion_flag": 0.0,
    "pcr_oi": 1.0,
    "pcr_oi_change": 0.0,
    "oi_imbalance_ratio": 0.0,
    "atm_iv": 14.0,
    "spread_bps": 2.5,
    "minutes_since_open": 180.0,
    "minutes_to_close": 195.0,
    "days_to_expiry": 3.0,
    "is_expiry_day": 0.0,
}


class FeatureVectorV3(BaseModel):
    """Point-in-Time validated feature snapshot."""
    schema_version: str = FEATURE_SCHEMA_V3
    instrument: str
    feature_timestamp: int = Field(..., description="Timestamp ms at which prediction is evaluated")
    max_source_timestamp: int = Field(..., description="Latest source data timestamp ms included in features")
    features: List[float] = Field(..., description="28-length numerical feature vector")
    feature_dict: Dict[str, float] = Field(..., description="Named mapping of features")
    missing_imputed_count: int = 0

    def validate_pit(self) -> bool:
        """Enforces data_timestamp <= feature_timestamp (no lookahead)."""
        if self.max_source_timestamp > self.feature_timestamp:
            raise ValueError(
                f"Temporal leakage detected: max_source_timestamp ({self.max_source_timestamp}) "
                f"> feature_timestamp ({self.feature_timestamp})"
            )
        if len(self.features) != len(FEATURE_NAMES_V3):
            raise ValueError(
                f"Feature vector length mismatch: expected {len(FEATURE_NAMES_V3)}, got {len(self.features)}"
            )
        return True
