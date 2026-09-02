import time
from datetime import datetime, timezone
from app.core.cache import cache_service

def cache_key(symbol: str, timeframe: str, data_timestamp: str) -> str:
    return f"{symbol.upper()}:{timeframe}:{data_timestamp}"
