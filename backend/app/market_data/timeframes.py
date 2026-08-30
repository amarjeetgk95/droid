TIMEFRAME_CONFIG = {
    "1m":  {"minutes": 1,  "horizon_minutes": 10,  "weight": 0.15, "description": "Very short-term movement and momentum", "refresh_seconds": 15},
    "5m":  {"minutes": 5,  "horizon_minutes": 20,  "weight": 0.25, "description": "Intraday entry/exit structure", "refresh_seconds": 30},
    "15m": {"minutes": 15, "horizon_minutes": 60, "weight": 0.35, "description": "Primary intraday trend and structure", "refresh_seconds": 60},
    "1h":  {"minutes": 60, "horizon_minutes": 120, "weight": 0.25, "description": "Higher-timeframe intraday context", "refresh_seconds": 300},
    # extensible
    "30m": {"minutes": 30, "horizon_minutes": 90, "weight": 0.20, "description": "Extended intraday", "refresh_seconds": 120},
    "4h":  {"minutes": 240,"horizon_minutes": 240, "weight": 0.20, "description": "Swing context", "refresh_seconds": 600},
    "1D":  {"minutes": 1440,"horizon_minutes": 1440,"weight": 0.20, "description": "Daily", "refresh_seconds": 3600},
    "1W":  {"minutes": 10080,"horizon_minutes": 10080,"weight": 0.20, "description": "Weekly", "refresh_seconds": 3600},
}

SUPPORTED_INITIAL = ["1m","5m","15m","1h"]

def get_timeframe_config(tf: str) -> dict | None:
    return TIMEFRAME_CONFIG.get(tf)

def validate_timeframe(tf: str) -> bool:
    return tf in TIMEFRAME_CONFIG

def horizon_for(tf: str) -> int:
    cfg = TIMEFRAME_CONFIG.get(tf)
    return cfg["horizon_minutes"] if cfg else 30
