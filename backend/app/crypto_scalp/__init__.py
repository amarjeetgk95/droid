"""
Crypto Scalp Module
Production-grade 24/7 scalping engine for BTC and ETH.
Features 5 specialized strategies, deterministic FSM paper execution,
Supabase persistence, Telegram alerts, and quantitative performance attribution.
"""
from app.crypto_scalp.base import (
    CryptoScalpContext,
    CryptoScalpCandidate,
    CryptoScalpStrategy,
)
from app.crypto_scalp.strategies import CRYPTO_SCALP_STRATEGIES
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
