from app.ai.base import BaseLLMProvider
from app.ai.mock_ai import MockLLMProvider
from app.ai.gemini import GeminiProvider
from app.ai.ollama import OllamaProvider
from app.ai.openrouter import OpenRouterProvider

_providers: dict[str, BaseLLMProvider] = {
    "mock_ai": MockLLMProvider(),
    "mock": MockLLMProvider(),
    "gemini": GeminiProvider(),
    "ollama": OllamaProvider(),
    "openrouter": OpenRouterProvider(),
}

def get_llm_provider(name: str = "mock_ai") -> BaseLLMProvider:
    key = (name or "mock_ai").lower()
    if key not in _providers:
        raise ValueError(f"Unknown AI provider '{name}'. Supported: mock_ai, gemini, openrouter, ollama")
    return _providers[key]

def create_provider_for_test(provider: str, **kwargs) -> BaseLLMProvider:
    """Instantiate a provider with per-request keys (used by /ai/test strict mode)."""
    p = provider.lower()
    if p == "gemini":
        return GeminiProvider(api_key=kwargs.get("geminiApiKey") or kwargs.get("api_key"), model=kwargs.get("geminiModel") or kwargs.get("model"))
    if p == "openrouter":
        # Fallback to server-side key if frontend key empty (server-side OPENROUTER_API_KEY is primary)
        frontend_key = (kwargs.get("openRouterApiKey") or kwargs.get("api_key") or "").strip()
        if not frontend_key:
            try:
                from app.core.config import settings as _cfg
                frontend_key = (getattr(_cfg, "openrouter_api_key", "") or getattr(_cfg, "OPENROUTER_API_KEY", "") or "").strip()
            except Exception:
                frontend_key = ""
        return OpenRouterProvider(api_key=frontend_key, model=kwargs.get("openRouterModel") or kwargs.get("model"))
    if p == "ollama":
        return OllamaProvider(base_url=kwargs.get("ollamaBaseUrl") or kwargs.get("base_url"), model=kwargs.get("ollamaModel") or kwargs.get("model"))
    if p in ("mock_ai", "mock"):
        return MockLLMProvider()
    raise ValueError(f"Unknown provider '{provider}'")
