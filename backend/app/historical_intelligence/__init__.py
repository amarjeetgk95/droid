"""
Historical Intelligence Engine (HIE) Package — Production Architecture
"""
from app.historical_intelligence.versioning import (
    ENGINE_VERSION,
    FEATURE_VERSION,
    EMBEDDING_VERSION,
    NORMALIZATION_VERSION,
    RETRIEVAL_VERSION,
    OUTCOME_VERSION,
    STATISTICS_VERSION,
    SCHEMA_VERSION,
    CURRENT_VERSIONS,
)
from app.historical_intelligence.schemas import (
    SessionPhase,
    MarketRegime,
    VolatilityRegime,
    VixBucket,
    HIEStatus,
    IndexLifecycleState,
    SampleReliability,
    CandleData,
    CanonicalFeatureVector,
    NormalizedFeatureVector,
    HistoricalStateSnapshot,
    ForwardOutcomeHorizon,
    HistoricalOutcomeRecord,
    HistoricalAnalogMatch,
    HistoricalQuery,
    HistoricalIntelligenceResult,
    AIStructuredContext,
)
from app.historical_intelligence.state_builder import (
    HistoricalStateBuilder,
    state_builder,
    validate_candle_integrity,
)
from app.historical_intelligence.retriever import (
    QdrantRetriever,
    InMemoryVectorStore,
    vector_retriever,
)
from app.historical_intelligence.similarity import (
    compute_composite_similarity,
    cosine_similarity,
)
from app.historical_intelligence.outcome_engine import (
    compute_horizon_outcome,
    construct_forward_outcomes,
)
from app.historical_intelligence.statistics import (
    compute_horizon_statistics,
    calculate_effective_sample_size,
    calculate_wilson_ci,
    classify_sample_reliability,
)
from app.historical_intelligence.confidence import compute_historical_confidence
from app.historical_intelligence.ai_context import AIContextGenerator, ai_context_generator
from app.historical_intelligence.replay import ReplayEngine
from app.historical_intelligence.query_service import HistoricalIntelligenceService, hie_service
from app.historical_intelligence.monitoring import HIEMonitor, hie_monitor

__all__ = [
    "ENGINE_VERSION",
    "FEATURE_VERSION",
    "EMBEDDING_VERSION",
    "NORMALIZATION_VERSION",
    "RETRIEVAL_VERSION",
    "OUTCOME_VERSION",
    "STATISTICS_VERSION",
    "SCHEMA_VERSION",
    "CURRENT_VERSIONS",
    "SessionPhase",
    "MarketRegime",
    "VolatilityRegime",
    "VixBucket",
    "HIEStatus",
    "IndexLifecycleState",
    "SampleReliability",
    "CandleData",
    "CanonicalFeatureVector",
    "NormalizedFeatureVector",
    "HistoricalStateSnapshot",
    "ForwardOutcomeHorizon",
    "HistoricalOutcomeRecord",
    "HistoricalAnalogMatch",
    "HistoricalQuery",
    "HistoricalIntelligenceResult",
    "AIStructuredContext",
    "HistoricalStateBuilder",
    "state_builder",
    "validate_candle_integrity",
    "QdrantRetriever",
    "InMemoryVectorStore",
    "vector_retriever",
    "compute_composite_similarity",
    "cosine_similarity",
    "compute_horizon_outcome",
    "construct_forward_outcomes",
    "compute_horizon_statistics",
    "calculate_effective_sample_size",
    "calculate_wilson_ci",
    "classify_sample_reliability",
    "compute_historical_confidence",
    "AIContextGenerator",
    "ai_context_generator",
    "ReplayEngine",
    "HistoricalIntelligenceService",
    "hie_service",
    "HIEMonitor",
    "hie_monitor",
]
