from app.ai.base import BaseLLMProvider
from app.ai.gemini import GeminiProvider
from app.ai.ollama import OllamaProvider
from app.ai.openrouter import OpenRouterProvider

# Direct providers — §11
try:
    from app.ai.providers.openai_provider import OpenAIProvider
except Exception:
    OpenAIProvider = None  # type: ignore
try:
    from app.ai.providers.novita_provider import NovitaProvider
except Exception:
    NovitaProvider = None  # type: ignore
try:
    from app.ai.providers.nvidia_provider import NvidiaProvider
except Exception:
    NvidiaProvider = None  # type: ignore
try:
    from app.ai.providers.custom_openai_provider import CustomOpenAICompatibleProvider
except Exception:
    CustomOpenAICompatibleProvider = None  # type: ignore

_providers: dict[str, BaseLLMProvider] = {
    "gemini": GeminiProvider(),
    "ollama": OllamaProvider(),
    "openrouter": OpenRouterProvider(),
}

# Register direct providers if available
if OpenAIProvider:
    _providers["openai"] = OpenAIProvider()
if NovitaProvider:
    _providers["novita"] = NovitaProvider()
if NvidiaProvider:
    _providers["nvidia"] = NvidiaProvider()
# custom_openai requires base_url, so not pre-registered singleton

def get_llm_provider(name: str = "gemini") -> BaseLLMProvider:
    key = (name or "gemini").lower()
    # compat: mock_ai -> openrouter
    if key == "mock_ai":
        key = "openrouter"
    # Normalize direct provider aliases
    if key in ("custom", "custom_openai", "custom_openai_compatible"):
        key = "custom_openai"
    if key not in _providers:
        # Try lazy creation for custom
        if key == "custom_openai" and CustomOpenAICompatibleProvider:
            raise ValueError("Custom OpenAI-compatible requires base_url – use create_provider_for_test with base_url")
        raise ValueError(f"Unknown AI provider '{name}'. Supported: gemini, openrouter, ollama, openai, novita, nvidia, custom_openai")
    return _providers[key]

def create_provider_for_test(provider: str, **kwargs) -> BaseLLMProvider:
    """Instantiate a provider with per-request keys (used by /ai/test strict mode). Per-request key fallback to config (env)."""
    p = provider.lower()
    # compat: mock_ai -> openrouter
    if p == "mock_ai":
        p = "openrouter"
    if p in ("gemini", "google_gemini"):
        key = (kwargs.get("geminiApiKey") or kwargs.get("api_key") or kwargs.get("apiKey") or "").strip() if (kwargs.get("geminiApiKey") or kwargs.get("api_key") or kwargs.get("apiKey")) else ""
        if not key:
            try:
                from app.core.config import settings as _cfg
                key = (getattr(_cfg, "gemini_api_key", "") or "").strip()
            except Exception:
                key = ""
        return GeminiProvider(api_key=key, model=kwargs.get("geminiModel") or kwargs.get("model"))
    if p == "openrouter":
        # Settings-driven key: frontend Settings UI is primary, env is fallback (no hardcode required)
        frontend_key = (kwargs.get("openRouterApiKey") or kwargs.get("api_key") or kwargs.get("apiKey") or kwargs.get("openRouter_api_key") or "").strip()
        if not frontend_key:
            try:
                from app.core.config import settings as _cfg
                frontend_key = (getattr(_cfg, "openrouter_api_key", "") or getattr(_cfg, "OPENROUTER_API_KEY", "") or "").strip()
            except Exception:
                frontend_key = ""
        return OpenRouterProvider(api_key=frontend_key, model=kwargs.get("openRouterModel") or kwargs.get("model"))
    if p == "ollama":
        return OllamaProvider(base_url=kwargs.get("ollamaBaseUrl") or kwargs.get("base_url") or kwargs.get("customBaseUrl"), model=kwargs.get("ollamaModel") or kwargs.get("model"))
    if p in ("openai",):
        if not OpenAIProvider:
            raise ValueError("OpenAI provider not available")
        key = (kwargs.get("apiKey") or kwargs.get("api_key") or kwargs.get("openaiApiKey") or kwargs.get("openai_api_key") or "").strip() if (kwargs.get("apiKey") or kwargs.get("api_key") or kwargs.get("openaiApiKey") or kwargs.get("openai_api_key")) else ""
        if not key:
            try:
                from app.core.config import settings as _cfg
                key = (getattr(_cfg, "openai_api_key", "") or getattr(_cfg, "OPENAI_API_KEY", "") or "").strip()
            except Exception:
                key = ""
        return OpenAIProvider(api_key=key, model=kwargs.get("model") or kwargs.get("openaiModel"), base_url=kwargs.get("base_url") or kwargs.get("apiBaseUrl") or kwargs.get("openaiBaseUrl"))
    if p in ("novita", "novita_ai"):
        if not NovitaProvider:
            raise ValueError("Novita provider not available")
        key = (kwargs.get("apiKey") or kwargs.get("api_key") or kwargs.get("novitaApiKey") or "").strip() if (kwargs.get("apiKey") or kwargs.get("api_key") or kwargs.get("novitaApiKey")) else ""
        if not key:
            try:
                from app.core.config import settings as _cfg
                key = (getattr(_cfg, "novita_api_key", "") or "").strip()
            except Exception:
                key = ""
        return NovitaProvider(api_key=key, model=kwargs.get("model") or kwargs.get("novitaModel"), base_url=kwargs.get("base_url") or kwargs.get("novitaBaseUrl"))
    if p in ("nvidia",):
        if not NvidiaProvider:
            raise ValueError("NVIDIA provider not available")
        key = (kwargs.get("apiKey") or kwargs.get("api_key") or kwargs.get("nvidiaApiKey") or "").strip() if (kwargs.get("apiKey") or kwargs.get("api_key") or kwargs.get("nvidiaApiKey")) else ""
        if not key:
            try:
                from app.core.config import settings as _cfg
                key = (getattr(_cfg, "nvidia_api_key", "") or "").strip()
            except Exception:
                key = ""
        return NvidiaProvider(api_key=key, model=kwargs.get("model") or kwargs.get("nvidiaModel"), base_url=kwargs.get("base_url") or kwargs.get("nvidiaBaseUrl"))
    if p in ("custom", "custom_openai", "custom_openai_compatible"):
        if not CustomOpenAICompatibleProvider:
            raise ValueError("Custom OpenAI provider not available")
        key = (kwargs.get("apiKey") or kwargs.get("api_key") or kwargs.get("customOpenaiApiKey") or kwargs.get("custom_openai_api_key") or "").strip() if (kwargs.get("apiKey") or kwargs.get("api_key") or kwargs.get("customOpenaiApiKey") or kwargs.get("custom_openai_api_key")) else ""
        if not key:
            try:
                from app.core.config import settings as _cfg
                key = (getattr(_cfg, "custom_openai_api_key", "") or "").strip()
            except Exception:
                key = ""
        base = (kwargs.get("base_url") or kwargs.get("apiBaseUrl") or kwargs.get("customBaseUrl") or kwargs.get("customOpenaiBaseUrl") or "").strip()
        if not base:
            try:
                from app.core.config import settings as _cfg
                base = (getattr(_cfg, "custom_openai_base_url", "") or "").strip()
            except Exception:
                base = ""
        # Also check generic custom provider base_url fallback
        return CustomOpenAICompatibleProvider(api_key=key, model=kwargs.get("model") or kwargs.get("customOpenaiModel"), base_url=base or kwargs.get("base_url") or "http://localhost:8080/v1")
    raise ValueError(f"Unknown provider '{provider}'")
