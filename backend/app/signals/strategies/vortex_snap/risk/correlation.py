"""
Cross-Instrument Correlation Control (§38).

Detects simultaneous directional signals across NIFTY, BANKNIFTY, and SENSEX.
Clusters correlated signals to prevent triple-leveraged macro exposure.
"""
from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CorrelatedSignalCluster(BaseModel):
    """Cluster of correlated simultaneous signals."""
    cluster_id: str = Field(default_factory=lambda: f"cls_{uuid.uuid4().hex[:8]}")
    instruments: List[str] = Field(default_factory=list)
    direction: int = Field(description="+1 for bullish cluster, -1 for bearish cluster")
    correlation_score: float = Field(ge=0.0, le=1.0)
    created_at_ms: int = Field(default_factory=lambda: int(time.time() * 1000))


class CorrelationController:
    """Manages simultaneous signal clustering across index derivatives."""

    def __init__(self, cluster_window_seconds: int = 180) -> None:
        self.cluster_window_ms = cluster_window_seconds * 1000
        # active signals: instrument -> (direction, timestamp_ms)
        self._recent_signals: Dict[str, tuple[int, int]] = {}

    def register_and_evaluate(
        self,
        instrument: str,
        direction: int,
        timestamp_ms: int,
    ) -> Optional[CorrelatedSignalCluster]:
        """Register signal and return active cluster if correlated exposure is detected."""
        # Evict stale signals
        self._recent_signals = {
            inst: (d, t)
            for inst, (d, t) in self._recent_signals.items()
            if timestamp_ms - t <= self.cluster_window_ms
        }

        # Check existing aligned signals
        aligned_instruments = [
            inst
            for inst, (d, t) in self._recent_signals.items()
            if d == direction and inst != instrument
        ]

        # Register current signal
        self._recent_signals[instrument] = (direction, timestamp_ms)

        if aligned_instruments:
            all_cluster_instruments = aligned_instruments + [instrument]
            # Correlation score based on index co-movement (e.g. 0.85 for 2 indices, 0.95 for 3)
            corr_score = 0.85 if len(all_cluster_instruments) == 2 else 0.95
            return CorrelatedSignalCluster(
                instruments=all_cluster_instruments,
                direction=direction,
                correlation_score=corr_score,
                created_at_ms=timestamp_ms,
            )

        return None

    def reset(self) -> None:
        self._recent_signals.clear()
