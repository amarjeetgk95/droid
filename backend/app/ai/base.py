from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator
from app.models.ai import AIInsightResponse, AIChatMessage, AIChatStreamChunk


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
        """Generate structured market analysis given grounded context."""
        ...

    async def stream_chat(
        self,
        messages: list[AIChatMessage],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
    ) -> AsyncGenerator[AIChatStreamChunk, None]:
        """Stream conversational chat tokens, reasoning tokens, and tool calls."""
        # Default fallback non-streaming emulation if provider hasn't overridden
        res = await self.generate_analysis(
            symbol="NIFTY",
            system_prompt=messages[0].content if messages and messages[0].role == "system" else "",
            user_prompt=messages[-1].content if messages else "",
        )
        yield AIChatStreamChunk(type="content", delta=res.executive_summary)
        yield AIChatStreamChunk(type="done", finish_reason="stop")

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier."""
        ...


# Backward compat alias
BaseLLMProvider = AIProvider
