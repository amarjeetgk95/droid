"""
Signals Processing Pipeline Package (Phase 3)
Decomposed quantitative scanning, evaluation, and registration pipeline.
"""
from app.signals.pipeline.data_acquisition import (
    ScanDiagnostics,
    acquire_market_context,
    calculate_session_vwap,
    detect_market_regime,
    is_fallback_quote,
)
from app.signals.pipeline.strategy_runner import (
    GAP_EXEMPT_STRATEGIES,
    run_strategies,
)
from app.signals.pipeline.gates import (
    Gate,
    GateChain,
    GateResult,
    FeedCircuitGate,
    FNOIntegrityGate,
    DeskConcurrencyGate,
    PortfolioConcurrencyGate,
    CrossDeskArbiterGate,
    RSIGate,
    MarketStructureGate,
    TriggerIntegrityGate,
    OptionViabilityGate,
    ChainMarkGate,
)
from app.signals.pipeline.enrichment import enrich_candidate
from app.signals.pipeline.signal_factory import build_signal_instance, register_and_notify

__all__ = [
    "ScanDiagnostics",
    "acquire_market_context",
    "calculate_session_vwap",
    "detect_market_regime",
    "is_fallback_quote",
    "GAP_EXEMPT_STRATEGIES",
    "run_strategies",
    "Gate",
    "GateChain",
    "GateResult",
    "FeedCircuitGate",
    "FNOIntegrityGate",
    "DeskConcurrencyGate",
    "PortfolioConcurrencyGate",
    "CrossDeskArbiterGate",
    "RSIGate",
    "MarketStructureGate",
    "TriggerIntegrityGate",
    "OptionViabilityGate",
    "ChainMarkGate",
    "enrich_candidate",
    "build_signal_instance",
    "register_and_notify",
]
