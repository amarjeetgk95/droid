from abc import ABC, abstractmethod
from app.models.ai import AIInsightResponse


class BaseLLMProvider(ABC):
    """Abstract interface for LLM market intelligence providers."""

    @abstractmethod
    async def generate_analysis(
        self,
        symbol: str,
        system_prompt: str,
        user_prompt: str,
    ) -> AIInsightResponse:
        """Generate structured market analysis given grounded context."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier."""
        ...
