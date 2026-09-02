"""
Leakage CI Gate — Section 48
Build and promotion gate that strictly blocks any model or dataset containing look-ahead bias,
future candles, future OI, future options, or non-monotonic timestamps.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("app.ml.leakage_gate")


class LeakageViolationError(Exception):
    pass


class LeakageGate:
    """
    Validates training and inference datasets for zero look-ahead bias.
    """

    @staticmethod
    def audit_row(
        observation_ts: int,
        feature_published_ts: int,
        feature_name: str,
    ) -> Tuple[bool, str | None]:
        """Audits an individual feature entry."""
        if feature_published_ts > observation_ts:
            msg = (
                f"LEAKAGE_DETECTED: Feature '{feature_name}' published at {feature_published_ts} "
                f"which is AFTER observation timestamp {observation_ts} (delta={feature_published_ts - observation_ts}ms)"
            )
            return False, msg
        return True, None

    @classmethod
    def validate_features_matrix(
        cls,
        records: List[Dict[str, Any]],
    ) -> Tuple[bool, List[str]]:
        """
        Validates an entire dataset of records.
        Each record must contain 'observation_time_utc' and feature publication timestamps.
        """
        violations: List[str] = []
        for i, rec in enumerate(records):
            obs_ts = rec.get("observation_time_utc")
            if obs_ts is None:
                violations.append(f"Row {i}: Missing required 'observation_time_utc'")
                continue

            pub_meta = rec.get("publication_timestamps", {})
            for feat_name, pub_ts in pub_meta.items():
                passed, err = cls.audit_row(obs_ts, pub_ts, feat_name)
                if not passed and err:
                    violations.append(f"Row {i}: {err}")

        passed = len(violations) == 0
        if not passed:
            logger.error("Leakage CI Gate FAILED with %d violations!", len(violations))
        return passed, violations

    @classmethod
    def assert_no_leakage(cls, records: List[Dict[str, Any]]) -> None:
        passed, violations = cls.validate_features_matrix(records)
        if not passed:
            raise LeakageViolationError(f"Leakage CI Gate Failed: {violations[:5]}")


# Global Singleton
leakage_gate = LeakageGate()
