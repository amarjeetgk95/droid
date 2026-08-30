"""HPI constants — fixed universe, data categories, budgets, safety caps.

§1: Exactly seven selectable derivatives. No other derivative may be
automatically added. This list is the single source of truth for the HPI
module (kept in sync with app.instruments.registry.CHART_ANALYSIS_UNIVERSE).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# §1 — Supported Derivative Universe (7 only)
# ---------------------------------------------------------------------------
HPI_DERIVATIVES: dict[str, dict] = {
    "NIFTY":     {"display_name": "NIFTY 50",  "asset_class": "INDEX",  "exchange": "NSE"},
    "BANKNIFTY": {"display_name": "BANKNIFTY", "asset_class": "INDEX",  "exchange": "NSE"},
    "FINNIFTY":  {"display_name": "FINNIFTY",  "asset_class": "INDEX",  "exchange": "NSE"},
    "SENSEX":    {"display_name": "SENSEX",    "asset_class": "INDEX",  "exchange": "BSE"},
    "BTC":       {"display_name": "Bitcoin",   "asset_class": "CRYPTO", "exchange": "BINANCE"},
    "ETH":       {"display_name": "Ethereum",  "asset_class": "CRYPTO", "exchange": "BINANCE"},
    "SOL":       {"display_name": "Solana",    "asset_class": "CRYPTO", "exchange": "BINANCE"},
}

HPI_UNIVERSE: list[str] = list(HPI_DERIVATIVES.keys())

# ---------------------------------------------------------------------------
# §2 / §6 — Data categories per derivative category (asset class)
# ---------------------------------------------------------------------------
INDEX_DATA_CATEGORIES: list[str] = [
    "1m_market_data",
    "futures",
    "open_interest",
    "option_chain",
    "iv",
    "pcr",
    "greeks",
]

CRYPTO_DATA_CATEGORIES: list[str] = [
    "1m_market_data",
    "futures",
    "open_interest",
    "funding",
    "liquidations",
]

CATEGORY_LABELS: dict[str, str] = {
    "1m_market_data": "1m Market Data",
    "futures": "Futures",
    "open_interest": "Open Interest",
    "option_chain": "Option Chain",
    "iv": "IV",
    "pcr": "PCR",
    "greeks": "Greeks",
    "funding": "Funding",
    "liquidations": "Liquidations",
}

# Human-readable analytical impact used in delete confirmation screens (§7).
CATEGORY_IMPACT: dict[str, str] = {
    "1m_market_data": "1m historical candle analysis will be unavailable for this period.",
    "futures": "Futures confirmation will be unavailable for this period.",
    "open_interest": "Open-interest confirmation will be unavailable for this period.",
    "option_chain": "Option-chain confirmation will be unavailable for this period.",
    "iv": "IV-based features will be unavailable for this period.",
    "pcr": "PCR-based features will be unavailable for this period.",
    "greeks": "Greeks-based features will be unavailable for this period.",
    "funding": "Funding-rate confirmation will be unavailable for this period.",
    "liquidations": "Liquidation confirmation will be unavailable for this period.",
}

# Price/technical analysis is independent of derivative-data selection (§2).
PRICE_TECH_IMPACT = "Not affected — price/technical analysis continues independently."


def categories_for(symbol: str) -> list[str]:
    """Data categories available for a derivative (INDEX vs CRYPTO set)."""
    meta = HPI_DERIVATIVES.get(symbol.upper())
    if not meta:
        return []
    return list(INDEX_DATA_CATEGORIES if meta["asset_class"] == "INDEX" else CRYPTO_DATA_CATEGORIES)


# ---------------------------------------------------------------------------
# §3 / §4 — Sampling intervals (seconds)
# ---------------------------------------------------------------------------
SAMPLING_INTERVALS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "1D": 86400,
}

# ---------------------------------------------------------------------------
# §10 — Storage-budget protection
# ---------------------------------------------------------------------------
STORAGE_TARGET_MB: float = 150.0
STORAGE_WARNING_MB: float = 175.0
STORAGE_HARD_CEILING_MB: float = 200.0

# Rough on-disk bytes per stored record per category (used for estimates).
BYTES_PER_RECORD: dict[str, int] = {
    "1m_market_data": 48,
    "futures": 64,
    "open_interest": 32,
    "option_chain": 96,
    "iv": 16,
    "pcr": 16,
    "greeks": 64,
    "funding": 24,
    "liquidations": 32,
}

# Validation cap: refuse to materialize absurd datasets in one import.
# The user is told to reduce the period or increase the sampling interval.
MAX_IMPORT_RECORDS_PER_DATASET: int = 300_000

# §12 — Automatic deletion background sweep cadence.
AUTO_DELETE_SWEEP_SECONDS: int = 900

# Alternatives offered when the hard ceiling is exceeded (§10). The system
# NEVER silently deletes data to satisfy the storage limit.
STORAGE_ALTERNATIVES: list[str] = [
    "Reduce historical period",
    "Reduce sampling frequency (e.g. 5m or 15m instead of 1m)",
    "Retain selected feature groups only",
    "Delete older unprotected data",
    "Disable lower-priority derivative datasets",
]
