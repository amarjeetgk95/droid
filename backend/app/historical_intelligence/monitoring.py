"""
Monitoring, Latency Benchmarks, Index Lifecycle & Failure Handling — §§36, 39, 40, 41
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import structlog
from app.historical_intelligence.schemas import (
    HIEStatus,
    IndexLifecycleState,
)

logger = structlog.get_logger()


@dataclass
class LatencyBenchmark:
    ann_retrieval_ms: float = 0.0
    outcome_lookup_ms: float = 0.0
    aggregation_ms: float = 0.0
    total_ms: float = 0.0
    target_met: bool = True


@dataclass
class IndexHealthMetrics:
    lifecycle_state: IndexLifecycleState = IndexLifecycleState.ACTIVE
    total_records: int = 0
    total_embeddings: int = 0
    feature_version_valid: bool = True
    pit_integrity_passed: bool = True
    last_validated_at: Optional[datetime] = None
    query_count: int = 0
    avg_latency_ms: float = 0.0


class HIEMonitor:
    """
    Monitors HIE latency SLAs (§41: < 50ms total), failure states (§40),
    and historical index lifecycle stages (§39).
    """

    def __init__(self):
        self.health = IndexHealthMetrics()
        self._latencies: list[float] = []

    def record_query_latency(
        self,
        ann_ms: float,
        outcome_ms: float,
        aggregation_ms: float,
    ) -> LatencyBenchmark:
        total = ann_ms + outcome_ms + aggregation_ms
        target_met = (total <= 50.0)

        self._latencies.append(total)
        if len(self._latencies) > 500:
            self._latencies.pop(0)

        self.health.query_count += 1
        self.health.avg_latency_ms = sum(self._latencies) / len(self._latencies)

        if not target_met:
            logger.debug(
                "hie_latency_target_exceeded",
                ann_ms=ann_ms,
                outcome_ms=outcome_ms,
                agg_ms=aggregation_ms,
                total_ms=total,
            )

        return LatencyBenchmark(
            ann_retrieval_ms=round(ann_ms, 2),
            outcome_lookup_ms=round(outcome_ms, 2),
            aggregation_ms=round(aggregation_ms, 2),
            total_ms=round(total, 2),
            target_met=target_met,
        )

    def validate_index_activation(
        self,
        record_count: int,
        embedding_count: int,
        feature_version_ok: bool,
        pit_tests_ok: bool,
    ) -> bool:
        """
        Guards index activation (§39):
        Never activate a newly rebuilt historical index until record count,
        embedding count, feature version, and PIT tests have passed.
        """
        if record_count <= 0 or embedding_count != record_count:
            self.health.lifecycle_state = IndexLifecycleState.DEGRADED
            return False

        if not feature_version_ok or not pit_tests_ok:
            self.health.lifecycle_state = IndexLifecycleState.DEGRADED
            return False

        self.health.total_records = record_count
        self.health.total_embeddings = embedding_count
        self.health.feature_version_valid = feature_version_ok
        self.health.pit_integrity_passed = pit_tests_ok
        self.health.lifecycle_state = IndexLifecycleState.ACTIVE
        self.health.last_validated_at = datetime.now(timezone.utc)
        return True


hie_monitor = HIEMonitor()
