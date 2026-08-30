import time
from datetime import datetime, timezone
from app.core.cache import cache_service

def cache_key(symbol: str, timeframe: str, data_timestamp: str) -> str:
    return f"{symbol.upper()}:{timeframe}:{data_timestamp}"

def cache_key_for_analysis(symbol: str, timeframe: str, data_timestamp: str) -> str:
    return f"chart_analysis:{symbol.upper()}:{timeframe}:{data_timestamp}"

async def get_cached_analysis(symbol: str, timeframe: str, data_timestamp: str):
    return await cache_service.get(cache_key_for_analysis(symbol, timeframe, data_timestamp))

async def set_cached_analysis(symbol: str, timeframe: str, data_timestamp: str, value, ttl: int = 60):
    await cache_service.set(cache_key_for_analysis(symbol, timeframe, data_timestamp), value, ttl_seconds=ttl)
