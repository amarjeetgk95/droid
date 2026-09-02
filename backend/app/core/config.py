from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Literal

class Settings(BaseSettings):
    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    app_mode: Literal["development", "production"] = "development"
    app_name: str = "Droid - F&O Market Analysis"
    
    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_public_url: str = ""  # public base URL used for Telegram setWebhook
    frontend_url: str = "https://fo-droid.web.app"
    
    # Auth
    auth_required: bool = False
    supabase_jwt_secret: str = ""
    
    # Database
    database_url: str = ""
    
    # Market Data — api_type gates Indian vs Crypto universes
    api_type: str = "indian"
    market_data_provider: str = "fyers"

    # Logging
    log_level: str = "INFO"

    # FYERS Settings (Indian Market Gateway)
    fyers_app_id: str = ""
    fyers_secret_key: str = ""
    fyers_redirect_uri: str = "https://droid-backend-emeq.onrender.com/api/v1/tokens/fyers/callback"
    fyers_access_token: str = ""

    # Flattrade Settings (Indian Market Gateway)
    flattrade_user_id: str = ""
    flattrade_api_key: str = ""
    flattrade_api_secret: str = ""
    flattrade_redirect_uri: str = "https://droid-backend-emeq.onrender.com/api/v1/tokens/flattrade/callback"
    flattrade_token: str = ""

    # Binance (Crypto) Settings
    binance_api_key: str = ""
    binance_api_secret: str = ""

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

    # Pattern Outcome Worker Settings (Historical Intelligence v2)
    pattern_outcome_worker_interval: int = 3600  # 1 hour

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

    # Telegram — §55-63
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_secret_token: str = ""          # legacy name — prefer TELEGRAM_WEBHOOK_SECRET
    telegram_webhook_secret: str = ""        # §6 X-Telegram-Bot-Api-Secret-Token
    telegram_rate_limit_per_second: float = 20.0
    telegram_rate_limit_per_chat_per_second: float = 1.0

    # Institutional — cross-market sync threshold
    cross_market_sync_threshold_ms: int = 500
    signal_ttl_ms: int = 5000
    institutional_live_mode: bool = False  # §77 NO_MOCK — fail-closed if true and dependency missing

    @model_validator(mode="after")
    def _normalize_market_data_provider(self) -> "Settings":
        import structlog
        indian_providers = ("fyers", "flattrade")
        crypto_providers = ("binance",)

        if self.api_type == "crypto":
            if self.market_data_provider not in crypto_providers:
                structlog.get_logger().warning(
                    "config_provider_fallback",
                    api_type=self.api_type,
                    requested=self.market_data_provider,
                    using="binance",
                )
                self.market_data_provider = "binance"
        else:
            if self.market_data_provider not in indian_providers:
                structlog.get_logger().warning(
                    "config_provider_fallback",
                    api_type=self.api_type,
                    requested=self.market_data_provider,
                    using="fyers",
                )
                self.market_data_provider = "fyers"
        return self

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

def get_settings() -> Settings:
    return Settings()

settings = get_settings()
