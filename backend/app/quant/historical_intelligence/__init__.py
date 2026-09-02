"""
Historical Intelligence Engine Package — §§1-66
"""
from app.quant.historical_intelligence.models import (
    ENGINE_VERSION, FEATURE_VERSION, SIMILARITY_VERSION, OUTCOME_VERSION, SR_VERSION,
    CandleData, SessionPhase, MarketRegime, NormalizedFeatures,
    HistoricalAnalogMatch, AnalogAnalyticsSummary, SupportResistanceZone
)
from app.quant.historical_intelligence.data_validator import (
    validate_single_candle, validate_and_clean_candle_series, has_complete_forward_window
)
from app.quant.historical_intelligence.session_context import (
    get_session_phase, compute_session_context, SessionContextData
)
from app.quant.historical_intelligence.feature_extractor import extract_features
from app.quant.historical_intelligence.regime_classifier import classify_regime, are_regimes_compatible
from app.quant.historical_intelligence.similarity import (
    cosine_similarity, pearson_correlation, fast_dtw_similarity, compute_composite_similarity
)
from app.quant.historical_intelligence.outcome_engine import (
    compute_forward_outcomes, ForwardOutcomeResult
)
from app.quant.historical_intelligence.analog_selector import find_historical_analogs
from app.quant.historical_intelligence.support_resistance import detect_support_resistance_zones

__all__ = [
    "ENGINE_VERSION", "FEATURE_VERSION", "SIMILARITY_VERSION", "OUTCOME_VERSION", "SR_VERSION",
    "CandleData", "SessionPhase", "MarketRegime", "NormalizedFeatures",
    "HistoricalAnalogMatch", "AnalogAnalyticsSummary", "SupportResistanceZone",
    "validate_single_candle", "validate_and_clean_candle_series", "has_complete_forward_window",
    "get_session_phase", "compute_session_context", "SessionContextData",
    "extract_features", "classify_regime", "are_regimes_compatible",
    "cosine_similarity", "pearson_correlation", "fast_dtw_similarity", "compute_composite_similarity",
    "compute_forward_outcomes", "ForwardOutcomeResult",
    "find_historical_analogs", "detect_support_resistance_zones"
]
