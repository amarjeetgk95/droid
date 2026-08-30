from pydantic_settings import BaseSettings
from typing import Literal

class Settings(BaseSettings):
    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    app_mode: Literal["development", "production"] = "development"
    app_name: str = "Droid - F&O Market Analysis"
    
    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_url: str = "https://fo-droid.web.app"
    
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
    fyers_redirect_uri: str = "https://droid-backend-emeq.onrender.com/api/v1/tokens/fyers/callback"
    fyers_access_token: str = ""

    # Upstox Settings (Phase 2)
    upstox_api_key: str = ""
    upstox_secret_key: str = ""
    upstox_redirect_uri: str = "https://droid-backend-emeq.onrender.com/api/v1/tokens/upstox/callback"
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

    # OpenRouter AI Model Catalog Settings (Free-Model Dynamic System)
    openrouter_api_key: str = ""
    openrouter_free_only: bool = True
    openrouter_model_cache_minutes: int = 10
    openrouter_default_model: str = "auto"

    # Direct Provider Keys — §34
    openai_api_key: str = ""
    novita_api_key: str = ""
    nvidia_api_key: str = ""
    gemini_api_key: str = ""
    custom_openai_api_key: str = ""
    custom_openai_base_url: str = ""

    # Direct Provider Models
    openai_model: str = "gpt-4o-mini"
    novita_model: str = "meta-llama/llama-3.3-70b-instruct"
    nvidia_model: str = "meta/llama-3.1-70b-instruct"
    custom_openai_model: str = "custom-model"

    # Ollama — §12
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "deepseek-r1:8b"

    # AI Configuration — §8 Three Connection Modes
    ai_connection_mode: Literal["OpenRouter", "Direct Provider", "Local Ollama"] = "OpenRouter"
    ai_direct_provider: Literal["OpenAI", "Novita AI", "NVIDIA", "Google Gemini", "Custom OpenAI-Compatible"] = "OpenAI"

    # Task-Specific Routing — §14, §15
    ai_routing_mode: Literal["Manual", "Task Optimized", "Best Available", "Cost Optimized"] = "Task Optimized"
    ai_fallback_enabled: bool = False  # §16 OFF by default

    # Risk & Pricing — §25, §26, §27
    risk_min_rr: float = 1.5
    risk_k_atr: float = 1.0
    risk_max_ai_price_drift_atr: float = 0.5  # §23
    risk_max_response_age_seconds: int = 30
    risk_per_trade_pct: float = 1.0
    max_position_size: int = 1000
    max_exposure_pct: float = 20.0
    max_spread: float = 0.5
    max_slippage: float = 0.3

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

def get_settings() -> Settings:
    return Settings()

settings = get_settings()
