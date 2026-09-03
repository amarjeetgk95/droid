"""
Embedding Architecture — §7
Phase 1: Deterministic Domain-Weighted Projection with L2 Normalization
Phase 2: Learned Embedding Model Interface (Autoencoder / Contrastive)
"""
from __future__ import annotations

import math
from typing import Optional
from app.historical_intelligence.schemas import NormalizedFeatureVector
from app.historical_intelligence.versioning import EMBEDDING_VERSION, FEATURE_VERSION

EMBEDDING_DIM: int = 64

# Feature family importance weights for deterministic projection
DOMAIN_WEIGHTS: dict[str, float] = {
    "price": 1.25,
    "candle": 1.0,
    "struct": 1.20,
    "trend": 1.15,
    "vol": 1.10,
    "fut": 0.95,
    "opt": 1.05,
    "ctx": 0.90,
}


class EmbeddingGenerator:
    """
    Generates standardized ANN embeddings from normalized market features.
    Guarantees that identical market states produce identical unit-norm vectors.
    """

    def __init__(self, embedding_version: str = EMBEDDING_VERSION):
        self.embedding_version = embedding_version
        self.dim = EMBEDDING_DIM

    def generate_embedding(
        self,
        normalized: NormalizedFeatureVector,
        learned_model: Optional[object] = None,
    ) -> list[float]:
        """
        Produce unit-norm embedding vector (64 dimensions) for Qdrant ANN search.
        """
        # Phase 2: If a learned sequence/autoencoder model is provided, use it
        if learned_model is not None and hasattr(learned_model, "encode"):
            try:
                learned_vec = learned_model.encode(normalized.dense_vector)
                return self._l2_normalize(list(learned_vec))
            except Exception:
                pass  # Fall back to Phase 1 deterministic embedding

        # Phase 1: Deterministic Domain-Weighted Projection
        base_dense = normalized.dense_vector
        n_base = len(base_dense)

        # Allocate 64-dim target embedding
        projected = [0.0] * self.dim

        # Weighted mapping of base features
        for i, val in enumerate(base_dense):
            key_idx = i % self.dim
            # Determine domain weight from prefix
            w = 1.0
            if i < 5:
                w = DOMAIN_WEIGHTS["price"]
            elif i < 10:
                w = DOMAIN_WEIGHTS["candle"]
            elif i < 16:
                w = DOMAIN_WEIGHTS["struct"]
            elif i < 21:
                w = DOMAIN_WEIGHTS["trend"]
            elif i < 28:
                w = DOMAIN_WEIGHTS["vol"]
            elif i < 32:
                w = DOMAIN_WEIGHTS["fut"]
            elif i < 37:
                w = DOMAIN_WEIGHTS["opt"]
            else:
                w = DOMAIN_WEIGHTS["ctx"]

            projected[key_idx] += val * w

        # Cross-domain interaction features to fill remainder of vector
        # (e.g. Price Return * Realized Vol, EMA Slope * Relative Volume, PCR * Basis)
        if n_base >= 35:
            ret = base_dense[0]
            rv = base_dense[25]
            ema_slope = base_dense[16]
            rel_vol = base_dense[21]
            pcr = base_dense[32]
            basis = base_dense[28]

            for offset, interaction in enumerate([
                ret * rv,
                ema_slope * rel_vol,
                pcr * basis,
                ret * rel_vol,
                ema_slope * pcr,
            ]):
                idx = (n_base + offset) % self.dim
                projected[idx] += interaction * 0.5

        return self._l2_normalize(projected)

    def _l2_normalize(self, vec: list[float]) -> list[float]:
        norm_sq = sum(x * x for x in vec)
        if norm_sq < 1e-12:
            return [0.0] * len(vec)
        norm = math.sqrt(norm_sq)
        return [round(x / norm, 6) for x in vec]


embedding_generator = EmbeddingGenerator()
