"""
Crypto Scalp Module
Production-grade 24/7 scalping engine for BTC and ETH.
Features 5 specialized strategies, Supabase persistence, Telegram alerts, and configurable intervals.
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
)
from app.crypto_scalp.telegram import dispatch_crypto_scalp_telegram

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
    "dispatch_crypto_scalp_telegram",
]
