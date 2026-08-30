"""Instrument alias mappings — satisfies spec backend/app/instruments/aliases.py"""
# Canonical alias map for quick lookup and documentation. Registry remains source of truth.
# This file exists to satisfy the module structure demanded by §42 and to allow future
# extension with human-curated aliases without touching registry.py directly.

ALIAS_MAP: dict[str, str] = {
    "nifty": "NIFTY",
    "nifty 50": "NIFTY",
    "cnx nifty": "NIFTY",
    "banknifty": "BANKNIFTY",
    "bank nifty": "BANKNIFTY",
    "nifty bank": "BANKNIFTY",
    "finnifty": "FINNIFTY",
    "sensex": "SENSEX",
    "bse sensex": "SENSEX",
    "bse30": "SENSEX",
    "midcpnifty": "MIDCPNIFTY",
    "reliance": "RELIANCE",
    "ril": "RELIANCE",
    "tcs": "TCS",
    "infy": "INFY",
    "infosys": "INFY",
    "hdfcbank": "HDFCBANK",
    "bitcoin": "BTCUSD",
    "btc": "BTCUSD",
    "btcusd": "BTCUSD",
    "btc-usd": "BTCUSD",
    "xbt": "BTCUSD",
    "btcusdt": "BTCUSDT",
    "btc usdt": "BTCUSDT",
    "ethereum": "ETHUSD",
    "eth": "ETHUSD",
    "ethusd": "ETHUSD",
    "ethusdt": "ETHUSDT",
    "gold": "GOLD",
    "xau": "GOLD",
}

def get_canonical_alias(alias: str) -> str | None:
    if not alias:
        return None
    return ALIAS_MAP.get(alias.strip().lower())
