"""Historical Market Analogue & Regime Memory Engine (Tier 2).

Implements exact CPU k-Nearest-Neighbors over 8D PCA regime projections:
- Strict temporal exclusion window (default +/-60 min buffer) to eliminate
  autocorrelation echo from the same underlying intraday move.
- Causal time boundary (strictly t_historical < t_query) to prevent lookahead leak.
- Dimensionality reduction via 8D PCA over orthogonal market state features.
- Exact Euclidean distance without quantization distortion.
- Computes analogue win rate, return dispersion, and regime consensus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import polars as pl
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import structlog

from app.quant.strategies.strategies import StrategyCandidate
from app.quant.labels.label_engine import BarrierOutcome

logger = structlog.get_logger(__name__)

ANALOGUE_FEATURES = [
    "vwap_distance",
    "ema_cross_spread",
    "atr_pct",
    "realized_vol_20",
    "rsi",
    "return_15m",
    "candle_body_ratio",
    "volume_ratio",
]


@dataclass
class AnalogueNeighbor:
    historical_idx: int
    timestamp: datetime
    distance: float
    similarity: float
    direction: int
    gross_return: float
    net_return: float
    exit_reason: str


@dataclass
class AnalogueContext:
    total_matches: int
    mean_distance: float
    analogue_win_rate: float        # Fraction of historical analogues with net_return > 0
    analogue_mean_return: float     # Average net return of analogues
    analogue_dispersion: float      # Standard deviation of analogue returns
    regime_similarity_score: float  # 0 to 100
    has_historical_support: bool    # True if win_rate >= 0.50 and dispersion is acceptable
    top_neighbors: list[AnalogueNeighbor] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_matches": self.total_matches,
            "mean_distance": round(self.mean_distance, 4),
            "analogue_win_rate": round(self.analogue_win_rate, 4),
            "analogue_mean_return": round(self.analogue_mean_return, 4),
            "analogue_dispersion": round(self.analogue_dispersion, 4),
            "regime_similarity_score": round(self.regime_similarity_score, 1),
            "has_historical_support": self.has_historical_support,
            "neighbor_count": len(self.top_neighbors),
        }


class HistoricalAnalogueEngine:
    """Finds time-separated, causal historical analogues in 8D PCA regime space."""

    def __init__(
        self,
        n_components: int = 8,
        k_neighbors: int = 15,
        exclusion_window_minutes: int = 60,
        support_win_threshold: float = 0.50,
        max_dispersion: float = 0.015,  # 1.5% max return dispersion
    ):
        self.n_components = n_components
        self.k_neighbors = k_neighbors
        self.exclusion_window_minutes = exclusion_window_minutes
        self.support_win_threshold = support_win_threshold
        self.max_dispersion = max_dispersion

        self.scaler = StandardScaler()
        self.pca = PCA(n_components=min(n_components, len(ANALOGUE_FEATURES)))
        
        self.is_indexed = False
        self.projected_vectors: Optional[np.ndarray] = None
        self.timestamps: list[datetime] = []
        self.directions: list[int] = []
        self.gross_returns: list[float] = []
        self.net_returns: list[float] = []
        self.exit_reasons: list[str] = []

    def _extract_feature_matrix(self, df_feat: pl.DataFrame, bar_indices: list[int]) -> np.ndarray:
        """Extracts regime feature matrix from DataFrame at bar indices."""
        sub_df = df_feat[bar_indices]
        cols = []
        for feat in ANALOGUE_FEATURES:
            if feat in sub_df.columns:
                s = sub_df[feat].fill_null(0.0).to_numpy()
            else:
                s = np.zeros(len(sub_df))
            cols.append(s)
        return np.column_stack(cols)

    def build_index(
        self,
        df_feat: pl.DataFrame,
        candidates: list[StrategyCandidate],
        outcomes: list[BarrierOutcome],
        net_returns: list[float],
    ):
        """Indexes historical setups into 8D PCA regime memory."""
        if len(candidates) < 20:
            logger.warning("insufficient_candidates_for_analogue_index", count=len(candidates))
            return

        bar_indices = [c.bar_index for c in candidates]
        X = self._extract_feature_matrix(df_feat, bar_indices)

        # Scale features and fit 8D PCA projection
        X_scaled = self.scaler.fit_transform(X)
        self.projected_vectors = self.pca.fit_transform(X_scaled)

        self.timestamps = [o.t_start for o in outcomes]
        self.directions = [c.direction for c in candidates]
        self.gross_returns = [o.gross_return for o in outcomes]
        self.net_returns = net_returns
        self.exit_reasons = [o.exit_reason for o in outcomes]
        self.is_indexed = True

        logger.info(
            "analogue_index_built",
            indexed_items=len(candidates),
            explained_variance=float(np.sum(self.pca.explained_variance_ratio_)),
        )

    def find_analogues(
        self,
        df_feat: pl.DataFrame,
        query_bar_idx: int,
        query_time: datetime,
        query_direction: int,
        k: Optional[int] = None,
    ) -> AnalogueContext:
        """Finds top k time-separated causal historical analogues."""
        k = k or self.k_neighbors

        if not self.is_indexed or self.projected_vectors is None or len(self.timestamps) == 0:
            return AnalogueContext(
                total_matches=0,
                mean_distance=0.0,
                analogue_win_rate=0.5,
                analogue_mean_return=0.0,
                analogue_dispersion=0.0,
                regime_similarity_score=50.0,
                has_historical_support=False,
            )

        # Extract and project query point
        X_query = self._extract_feature_matrix(df_feat, [query_bar_idx])
        X_query_scaled = self.scaler.transform(X_query)
        z_query = self.pca.transform(X_query_scaled)[0]  # Shape: (n_components,)

        # Filter candidate pool:
        # 1. Causal rule: historical_time < query_time
        # 2. Temporal exclusion buffer: query_time - hist_time > exclusion_minutes
        exclusion_delta = timedelta(minutes=self.exclusion_window_minutes)
        min_cutoff = query_time - exclusion_delta

        valid_indices: list[int] = []
        for i, t_hist in enumerate(self.timestamps):
            if t_hist < min_cutoff:
                # Same direction preference (longs compared to historical longs, shorts to shorts)
                if self.directions[i] == query_direction:
                    valid_indices.append(i)

        if len(valid_indices) < 5:
            # Fallback if too few direction-matched historical points
            for i, t_hist in enumerate(self.timestamps):
                if t_hist < min_cutoff:
                    valid_indices.append(i)

        if not valid_indices:
            return AnalogueContext(
                total_matches=0,
                mean_distance=0.0,
                analogue_win_rate=0.5,
                analogue_mean_return=0.0,
                analogue_dispersion=0.0,
                regime_similarity_score=50.0,
                has_historical_support=False,
            )

        # Compute exact Euclidean distances in 8D PCA space
        sub_vectors = self.projected_vectors[valid_indices]
        diffs = sub_vectors - z_query
        distances = np.linalg.norm(diffs, axis=1)

        # Sort by distance
        k_actual = min(k, len(distances))
        top_k_order = np.argsort(distances)[:k_actual]

        neighbors: list[AnalogueNeighbor] = []
        matched_nets: list[float] = []

        for rank_idx in top_k_order:
            orig_idx = valid_indices[rank_idx]
            dist = float(distances[rank_idx])
            sim = float(np.exp(-dist / 2.0))
            net_ret = self.net_returns[orig_idx]
            matched_nets.append(net_ret)

            neighbors.append(AnalogueNeighbor(
                historical_idx=orig_idx,
                timestamp=self.timestamps[orig_idx],
                distance=round(dist, 4),
                similarity=round(sim, 4),
                direction=self.directions[orig_idx],
                gross_return=self.gross_returns[orig_idx],
                net_return=net_ret,
                exit_reason=self.exit_reasons[orig_idx],
            ))

        mean_dist = float(np.mean([n.distance for n in neighbors]))
        win_count = sum(1 for n in neighbors if n.net_return > 0)
        win_rate = win_count / max(1, len(neighbors))
        mean_ret = float(np.mean(matched_nets)) if matched_nets else 0.0
        dispersion = float(np.std(matched_nets)) if len(matched_nets) > 1 else 0.0

        # Similarity score: 100 * exp(-mean_dist / 3.0)
        sim_score = float(np.clip(100.0 * np.exp(-mean_dist / 3.0), 0.0, 100.0))

        has_support = (
            win_rate >= self.support_win_threshold and
            dispersion <= self.max_dispersion and
            len(neighbors) >= min(5, k)
        )

        return AnalogueContext(
            total_matches=len(valid_indices),
            mean_distance=mean_dist,
            analogue_win_rate=win_rate,
            analogue_mean_return=mean_ret,
            analogue_dispersion=dispersion,
            regime_similarity_score=sim_score,
            has_historical_support=has_support,
            top_neighbors=neighbors,
        )
