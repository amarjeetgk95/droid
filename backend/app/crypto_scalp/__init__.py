"""
Crypto Scalp & Signal Module
Production-grade 24/7 institutional signal engine for BTC and ETH.
Features:
  - 5 specialized quantitative strategies
  - 11-State deterministic FSM paper execution & +0.8R Breakeven Ratchets
  - Central Risk Engine with asset envelopes and 'no clamping' invariant
  - Trigger Integrity Gate (eliminates born-triggered setups)
  - Multi-Domain Confluence Fusion (Technical, MTF, Funding/OI, Regime, Sentiment)
  - Staged Fills (50% T1 partial close, runner to T2) and fee accounting
  - Dual-Cadence Worker (2.5s Risk Loop + 10s Scalp / 30s Intraday Scanner)
  - Real-Time Server-Sent Events (SSE) stream & Supabase persistence
"""
from app.crypto_scalp.base import (
    CryptoScalpContext,
    CryptoScalpCandidate,
    CryptoScalpStrategy,
)
from app.crypto_scalp.strategies import CRYPTO_SCALP_STRATEGIES
from app.crypto_scalp.trigger_gate import (
    check_crypto_trigger_integrity,
    CryptoTriggerCheckResult,
)
from app.crypto_scalp.risk_engine import (
    crypto_risk_engine,
    CryptoStrategySetup,
    CryptoValidatedRiskDecision,
    CryptoCentralRiskEngine,
)
from app.crypto_scalp.fsm import (
    crypto_signal_fsm,
    CryptoSignalInstance,
    CryptoFSMTransitionAudit,
    CryptoSignalFSMManager,
)
from app.crypto_scalp.confluence import (
    crypto_confluence_engine,
    CryptoConfluenceEngine,
)
from app.crypto_scalp.fill_reconciler import (
    crypto_fill_reconciler,
    CryptoFillReconciliationRecord,
    CryptoStageFill,
    CryptoFillReconciler,
)
from app.crypto_scalp.sse import (
    crypto_sse_hub,
    CryptoSSEHub,
)
from app.crypto_scalp.scanner import crypto_scalp_scanner
from app.crypto_scalp.worker import crypto_scalp_worker
from app.crypto_scalp.persistence import (
    ensure_crypto_scalp_tables,
    persist_scalp_signal,
    fetch_persisted_scalp_signals,
    save_execution_record,
    save_execution_event,
    fetch_execution_records,
    fetch_execution_record_by_id,
    fetch_events_for_trade,
    load_unclosed_execution_records,
    save_crypto_signals_state_local,
    restore_crypto_signals_state_local,
)
from app.crypto_scalp.telegram import dispatch_crypto_scalp_telegram
from app.crypto_scalp.models_execution import (
    CryptoScalpPositionState,
    CryptoScalpExitEventType,
    CryptoScalpExecutionMode,
    CryptoScalpExecutionConfig,
    CryptoScalpExecutionRecord,
    CryptoScalpExecutionEvent,
    CryptoScalpStrategyStats,
    CryptoScalpAssetStats,
    CryptoScalpPerformanceMetrics,
)
from app.crypto_scalp.paper_execution import paper_execution_provider, PaperExecutionProvider
from app.crypto_scalp.outcome_tracker import crypto_scalp_outcome_tracker, CryptoScalpOutcomeTracker
from app.crypto_scalp.performance import performance_engine, CryptoScalpPerformanceEngine

__all__ = [
    "CryptoScalpContext",
    "CryptoScalpCandidate",
    "CryptoScalpStrategy",
    "CRYPTO_SCALP_STRATEGIES",
    "check_crypto_trigger_integrity",
    "CryptoTriggerCheckResult",
    "crypto_risk_engine",
    "CryptoStrategySetup",
    "CryptoValidatedRiskDecision",
    "CryptoCentralRiskEngine",
    "crypto_signal_fsm",
    "CryptoSignalInstance",
    "CryptoFSMTransitionAudit",
    "CryptoSignalFSMManager",
    "crypto_confluence_engine",
    "CryptoConfluenceEngine",
    "crypto_fill_reconciler",
    "CryptoFillReconciliationRecord",
    "CryptoStageFill",
    "CryptoFillReconciler",
    "crypto_sse_hub",
    "CryptoSSEHub",
    "crypto_scalp_scanner",
    "crypto_scalp_worker",
    "ensure_crypto_scalp_tables",
    "persist_scalp_signal",
    "fetch_persisted_scalp_signals",
    "save_execution_record",
    "save_execution_event",
    "fetch_execution_records",
    "fetch_execution_record_by_id",
    "fetch_events_for_trade",
    "load_unclosed_execution_records",
    "save_crypto_signals_state_local",
    "restore_crypto_signals_state_local",
    "dispatch_crypto_scalp_telegram",
    "CryptoScalpPositionState",
    "CryptoScalpExitEventType",
    "CryptoScalpExecutionMode",
    "CryptoScalpExecutionConfig",
    "CryptoScalpExecutionRecord",
    "CryptoScalpExecutionEvent",
    "CryptoScalpStrategyStats",
    "CryptoScalpAssetStats",
    "CryptoScalpPerformanceMetrics",
    "paper_execution_provider",
    "PaperExecutionProvider",
    "crypto_scalp_outcome_tracker",
    "CryptoScalpOutcomeTracker",
    "performance_engine",
    "CryptoScalpPerformanceEngine",
]
