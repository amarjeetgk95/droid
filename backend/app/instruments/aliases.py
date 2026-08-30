"""Instrument alias mappings — satisfies spec backend/app/instruments/aliases.py"""
# Canonical alias map for quick lookup and documentation. Registry remains source of truth.
# This file exists to satisfy the module structure demanded by §42 and to allow future
# extension with human-curated aliases without touching registry.py directly.

# Restricted to 7 approved chart-analysis derivatives only.
ALIAS_MAP: dict[str, str] = {
    "nifty": "NIFTY",
    "nifty 50": "NIFTY",
    "nifty50": "NIFTY",
    "cnx nifty": "NIFTY",
    "banknifty": "BANKNIFTY",
    "bank nifty": "BANKNIFTY",
    "nifty bank": "BANKNIFTY",
    "finnifty": "FINNIFTY",
    "fin nifty": "FINNIFTY",
    "sensex": "SENSEX",
    "bse sensex": "SENSEX",
    "bse30": "SENSEX",
    "bitcoin": "BTC",
    "btc": "BTC",
    "btcusd": "BTC",
    "btc usd": "BTC",
    "btc-usd": "BTC",
    "btcusdt": "BTC",
    "btc usdt": "BTC",
    "btc-usdt": "BTC",
    "xbt": "BTC",
    "ethereum": "ETH",
    "eth": "ETH",
    "ethusd": "ETH",
    "eth usd": "ETH",
    "eth-usd": "ETH",
    "ethusdt": "ETH",
    "eth usdt": "ETH",
    "solana": "SOL",
    "sol": "SOL",
    "solusd": "SOL",
    "sol usd": "SOL",
    "sol-usd": "SOL",
    "solusdt": "SOL",
    "sol usdt": "SOL",
    "sol-usdt": "SOL",
}

def get_canonical_alias(alias: str) -> str | None:
    if not alias:
        return None
    return ALIAS_MAP.get(alias.strip().lower())
