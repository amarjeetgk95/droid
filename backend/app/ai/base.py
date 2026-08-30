from abc import ABC, abstractmethod
from typing import Any

from app.models.ai import AIInsightResponse


class AIProvider(ABC):
    """
    Common AI Provider Abstraction — §13
    Quantitative/trading engine must not contain provider-specific inference code.
    """

    @abstractmethod
    async def list_models(self) -> list[dict[str, Any]]:
        """List available models for this provider."""
        ...

    @abstractmethod
    async def analyze(self, market_state: dict, task: str) -> dict:
        """Analyze immutable MarketState for given task (§14)."""
        ...

    @abstractmethod
    async def test_connection(self) -> dict[str, Any]:
        """Lightweight connectivity check."""
        ...

    @abstractmethod
    async def get_model_info(self, model_id: str) -> dict[str, Any]:
        """Return metadata/capabilities for model_id."""
        ...

    @abstractmethod
    async def generate_analysis(
        self,
        symbol: str,
        system_prompt: str,
        user_prompt: str,
    ) -> AIInsightResponse:
        """Generate structured market analysis given grounded context (legacy)."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier."""
        ...


# Backward compat alias
BaseLLMProvider = AIProvider
