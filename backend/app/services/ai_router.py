"""
Task-Specific Model Router — §14, §15

Allow different AI models for different tasks.
Tasks:
INTRADAY_ANALYSIS, NEWS_ANALYSIS, DEEP_RESEARCH, MTF_SYNTHESIS,
CHART_EXPLANATION, FINAL_REVIEW

Each task must have its own model configuration.
Example mapping per spec §14 and §41.

Routing Modes (§15):
Manual, Task Optimized, Best Available, Cost Optimized
Default: Task Optimized
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

import structlog

logger = structlog.get_logger()


class AITask(str, Enum):
    INTRADAY_ANALYSIS = "INTRADAY_ANALYSIS"
    NEWS_ANALYSIS = "NEWS_ANALYSIS"
    DEEP_RESEARCH = "DEEP_RESEARCH"
    MTF_SYNTHESIS = "MTF_SYNTHESIS"
    CHART_EXPLANATION = "CHART_EXPLANATION"
    FINAL_REVIEW = "FINAL_REVIEW"


class RoutingMode(str, Enum):
    MANUAL = "Manual"
    TASK_OPTIMIZED = "Task Optimized"
    BEST_AVAILABLE = "Best Available"
    COST_OPTIMIZED = "Cost Optimized"


# Default task → model guidance per §14, §41
# When free_only=True, these resolve to best free in category via catalog ranking
TASK_DEFAULTS_TASK_OPTIMIZED: dict[AITask, dict[str, str]] = {
    AITask.INTRADAY_ANALYSIS: {"hint": "fast finance/reasoning free model", "category": "Finance"},
    AITask.NEWS_ANALYSIS: {"hint": "research/news free model", "category": "Research"},
    AITask.DEEP_RESEARCH: {"hint": "strongest reasoning free model", "category": "Reasoning"},
    AITask.MTF_SYNTHESIS: {"hint": "strong synthesis reasoning model", "category": "Reasoning"},
    AITask.CHART_EXPLANATION: {"hint": "fast model", "category": "Fast"},
    AITask.FINAL_REVIEW: {"hint": "highest-quality configured model", "category": "Reasoning"},
}


class TaskModelRouter:
    """
    Routes tasks to models based on routing mode.
    Stores per-task model config; never requires one global model.
    """

    def __init__(self):
        # task -> model_id (or "auto")
        self._task_models: dict[AITask, str] = {t: "auto" for t in AITask}
        self.routing_mode: RoutingMode = RoutingMode.TASK_OPTIMIZED
        # Connection mode §8
        self.connection_mode: Literal["OpenRouter", "Direct Provider", "Local Ollama"] = "OpenRouter"
        # fallback OFF by default §16
        self.fallback_enabled: bool = False
        self.fallback_ollama_model: str | None = None

    def set_task_model(self, task: AITask | str, model_id: str) -> None:
        t = AITask(task) if isinstance(task, str) else task
        self._task_models[t] = model_id.strip() or "auto"

    def get_task_model(self, task: AITask | str) -> str:
        t = AITask(task) if isinstance(task, str) else task
        return self._task_models.get(t, "auto")

    def get_all_task_models(self) -> dict[str, str]:
        return {k.value: v for k, v in self._task_models.items()}

    def set_routing_mode(self, mode: RoutingMode | str) -> None:
        if isinstance(mode, str):
            # Normalize case
            for m in RoutingMode:
                if m.value.lower() == mode.lower() or m.name.lower() == mode.lower():
                    self.routing_mode = m
                    return
            raise ValueError(f"Unknown routing mode {mode}")
        self.routing_mode = mode

    async def resolve_model_for_task(
        self,
        task: AITask | str,
        free_only: bool = True,
    ) -> str:
        """
        Resolve Auto to current eligible free model per mode.
        Never silently falls back to paid while FREE ONLY enabled.
        """
        t = AITask(task) if isinstance(task, str) else task
        configured = self._task_models.get(t, "auto")

        if self.routing_mode == RoutingMode.MANUAL:
            # Use explicit config, but validate free-only
            if configured.lower() == "auto":
                # In manual mode auto is not expected; resolve via catalog
                from app.services.openrouter_catalog import validate_model_or_raise
                m = await validate_model_or_raise("auto", free_only=free_only)
                return m["id"]
            from app.services.openrouter_catalog import validate_model_or_raise
            m = await validate_model_or_raise(configured, free_only=free_only)
            return m["id"]

        if self.routing_mode == RoutingMode.TASK_OPTIMIZED:
            # Task-optimized: if configured is specific non-auto, use it; else pick best per category
            if configured.lower() != "auto":
                from app.services.openrouter_catalog import validate_model_or_raise
                m = await validate_model_or_raise(configured, free_only=free_only)
                return m["id"]
            # Auto -> pick best free in category for task
            task_cat = TASK_DEFAULTS_TASK_OPTIMIZED.get(t, {}).get("category", "General")
            from app.services.openrouter_catalog import get_model_catalog
            catalog = await get_model_catalog(free_only=free_only)
            models = catalog.get("models", [])
            # Filter by category if possible
            candidates = [m for m in models if m.get("category") == task_cat and m.get("is_free")]
            if not candidates:
                # Fallback to general best free
                candidates = [m for m in models if m.get("is_free")]
            if not candidates:
                raise ValueError("No eligible free model for task")
            # Already sorted by trading_rank
            candidates_sorted = sorted(candidates, key=lambda x: x.get("trading_rank", 0), reverse=True)
            return candidates_sorted[0]["id"]

        if self.routing_mode == RoutingMode.BEST_AVAILABLE:
            from app.services.openrouter_catalog import get_model_catalog
            catalog = await get_model_catalog(free_only=free_only)
            models = catalog.get("models", [])
            candidates = [m for m in models if m.get("is_free")]
            if not candidates:
                raise ValueError("No eligible free model")
            return sorted(candidates, key=lambda x: x.get("trading_rank", 0), reverse=True)[0]["id"]

        if self.routing_mode == RoutingMode.COST_OPTIMIZED:
            from app.services.openrouter_catalog import get_model_catalog
            catalog = await get_model_catalog(free_only=True)  # always free-only for cost optimized
            models = catalog.get("models", [])
            # Prefer fastest cheap among free
            candidates = [m for m in models if m.get("is_free")]
            if not candidates:
                raise ValueError("No free model")
            # Sort by cost then rank; free all zero, so pick fastest (category Fast bonus)
            fast = [m for m in candidates if m.get("category") == "Fast"]
            if fast:
                return sorted(fast, key=lambda x: x.get("trading_rank", 0), reverse=True)[0]["id"]
            return sorted(candidates, key=lambda x: x.get("trading_rank", 0), reverse=True)[0]["id"]

        # Fallback task optimized
        from app.services.openrouter_catalog import validate_model_or_raise
        m = await validate_model_or_raise(configured, free_only=free_only)
        return m["id"]


# Singleton
ai_router = TaskModelRouter()
