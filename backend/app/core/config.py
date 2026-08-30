from pydantic_settings import BaseSettings
from typing import Literal

class Settings(BaseSettings):
    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    app_mode: Literal["development", "production"] = "development"
    app_name: str = "Droid - F&O Market Analysis"
    
    # Server
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    
    # Auth
    auth_required: bool = False
    supabase_jwt_secret: str = ""
    
    # Database
    database_url: str = ""
    
    # Market Data
    market_data_provider: Literal["mock", "fyers", "upstox"] = "mock"
    
    # Mock Data
    mock_data_mode: Literal["deterministic", "random"] = "deterministic"
    mock_seed: int = 42
    
    # Logging
    log_level: str = "INFO"

    # FYERS Settings (Phase 2)
    fyers_app_id: str = ""
    fyers_secret_key: str = ""
    fyers_redirect_uri: str = "http://127.0.0.1:8000/api/v1/tokens/fyers/callback"
    fyers_access_token: str = ""

    # Upstox Settings (Phase 2)
    upstox_api_key: str = ""
    upstox_secret_key: str = ""
    upstox_redirect_uri: str = "http://127.0.0.1:8000/api/v1/tokens/upstox/callback"
    upstox_access_token: str = ""

    # WebSocket & Reconnect Settings (Phase 2)
    ws_reconnect_initial_seconds: float = 1.0
    ws_reconnect_max_seconds: float = 60.0
    ws_reconnect_jitter: bool = True
    ws_heartbeat_interval_seconds: float = 10.0

    # Rate Limiting Settings (Phase 2)
    rate_limit_requests_per_second: float = 10.0
    rate_limit_requests_per_minute: float = 200.0
    rate_limit_burst_limit: int = 20

    # High-Frequency Buffer Settings (Phase 2)
    event_buffer_max_size: int = 10000
    event_buffer_high_watermark: float = 0.8  # 80% capacity before shedding LOW priority

    # Redis & Caching Settings (Phase 3)
    redis_url: str = ""
    cache_ttl_default_seconds: int = 300
    cache_max_memory_items: int = 50000

    # Circuit Breaker Settings (Phase 3)
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout_seconds: float = 30.0
    circuit_breaker_half_open_success_threshold: int = 2

    # Snapshot & Persistence Settings (Phase 3)
    snapshot_interval_seconds: int = 60
    snapshot_file_path: str = "market_snapshot.json"

    # Batch Write Pipeline Settings (Phase 3)
    batch_write_flush_interval_ms: int = 500
    batch_write_max_size: int = 200

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

def get_settings() -> Settings:
    return Settings()

settings = get_settings()
