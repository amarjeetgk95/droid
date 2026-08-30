from app.ai.base import BaseLLMProvider
from app.ai.mock_ai import MockLLMProvider
from app.ai.gemini import GeminiProvider
from app.ai.ollama import OllamaProvider

_providers: dict[str, BaseLLMProvider] = {
    "mock_ai": MockLLMProvider(),
    "mock": MockLLMProvider(),
    "gemini": GeminiProvider(),
    "ollama": OllamaProvider(),
}


def get_llm_provider(name: str = "mock_ai") -> BaseLLMProvider:
    """Retrieve LLM provider instance by name, defaulting to mock_ai."""
    return _providers.get(name.lower(), _providers["mock_ai"])
