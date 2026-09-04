"""
Point-In-Time (PIT) Data Warehouse & AS-OF Temporal Join Engine — Sections 46, 47
Guarantees point-in-time correctness: any observation at timestamp T may contain ONLY
information computed and published by or before T.
Preserves historical contract universe integrity to eliminate survivorship & look-ahead bias.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("app.ml.pit_store")


@dataclass(frozen=True)
class PITRecord:
    symbol: str
    feature_name: str
    feature_value: float
    observation_time_utc: int  # T
    computed_at_utc: int       # when computed
    published_at_utc: int      # when made available
    feature_version: str = "1.0"


class PITStore:
    """
    Point-in-Time dataset builder with strict AS-OF temporal joins.
    """

    def __init__(self) -> None:
        self._records: List[PITRecord] = []
        self._universe_history: Dict[str, List[Tuple[int, int]]] = {}  # symbol -> list of (valid_from, valid_to)

    def register_instrument_validity(self, symbol: str, valid_from_utc: int, valid_to_utc: Optional[int] = None) -> None:
        """Tracks the historical active universe of instruments (§47)."""
        to_ts = valid_to_utc if valid_to_utc is not None else 9999999999999
        if symbol not in self._universe_history:
            self._universe_history[symbol] = []
        self._universe_history[symbol].append((valid_from_utc, to_ts))

    def is_instrument_valid_at(self, symbol: str, timestamp_utc: int) -> bool:
        """Checks if symbol was legitimately tradable at observation time T (§47)."""
        intervals = self._universe_history.get(symbol, [])
        if not intervals:
            # Default valid if not tracked
            return True
        for valid_from, valid_to in intervals:
            if valid_from <= timestamp_utc <= valid_to:
                return True
        return False

    def insert_record(
        self,
        symbol: str,
        feature_name: str,
        feature_value: float,
        observation_time_utc: int,
        computed_at_utc: int,
        published_at_utc: int,
        feature_version: str = "1.0",
    ) -> bool:
        """
        Inserts record with validation against future timestamps.
        """
        # Strict PIT check: published_at must not be after observation_time
        if published_at_utc > observation_time_utc:
            logger.error(
                "PIT Violation: published_at (%d) > observation_time (%d) for %s:%s",
                published_at_utc,
                observation_time_utc,
                symbol,
                feature_name,
            )
            return False

        rec = PITRecord(
            symbol=symbol,
            feature_name=feature_name,
            feature_value=feature_value,
            observation_time_utc=observation_time_utc,
            computed_at_utc=computed_at_utc,
            published_at_utc=published_at_utc,
            feature_version=feature_version,
        )
        self._records.append(rec)
        return True

    def as_of_join(self, symbol: str, target_timestamp_utc: int) -> Dict[str, float]:
        """
        Performs AS-OF temporal join to retrieve the latest feature values known at target_timestamp_utc.
        """
        if not self.is_instrument_valid_at(symbol, target_timestamp_utc):
            logger.warning("Instrument %s was not active at timestamp %d", symbol, target_timestamp_utc)
            return {}

        latest_features: Dict[str, Tuple[int, float]] = {}  # feature_name -> (published_at, value)
        for rec in self._records:
            if rec.symbol == symbol and rec.published_at_utc <= target_timestamp_utc:
                current = latest_features.get(rec.feature_name)
                if current is None or rec.published_at_utc > current[0]:
                    latest_features[rec.feature_name] = (rec.published_at_utc, rec.feature_value)

        return {k: v[1] for k, v in latest_features.items()}

    def count(self) -> int:
        return len(self._records)


# Global Singleton
pit_store = PITStore()
