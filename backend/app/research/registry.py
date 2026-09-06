"""Central Indicator Registry for the Research Laboratory (§13, §14).

Manages indicator lifecycle, registration, version tracking, and lookup.
"""

from typing import Dict, List, Optional, Type
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.research.enums import IndicatorCategory, IndicatorLifecycle
from app.research.indicator_base import IndicatorBase
from app.research.models import IndicatorDefinition

logger = structlog.get_logger(__name__)


class IndicatorRegistry:
    """Central registry holding all research indicators.
    
    Permits dynamic registration and lifecycle management without
    requiring modifications to core pipeline execution code.
    """

    _instance: Optional["IndicatorRegistry"] = None
    _indicators: Dict[str, IndicatorBase] = {}

    def __new__(cls) -> "IndicatorRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._indicators = {}
        return cls._instance

    @classmethod
    def register(cls, indicator_instance: IndicatorBase) -> None:
        """Register an indicator instance in the in-memory registry."""
        ind_id = indicator_instance.indicator_id
        if ind_id in cls._indicators:
            logger.info("replacing_registered_indicator", indicator_id=ind_id, version=indicator_instance.version)
        else:
            logger.info("registered_research_indicator", indicator_id=ind_id, version=indicator_instance.version)
        cls._indicators[ind_id] = indicator_instance

    @classmethod
    def _ensure_discovered(cls) -> None:
        """Ensure built-in indicators are discovered if registry is empty."""
        if not cls._indicators:
            try:
                import app.research.indicators  # noqa: F401
            except Exception as e:
                logger.warning("indicator_autodiscovery_failed", error=str(e))

    @classmethod
    def get(cls, indicator_id: str) -> Optional[IndicatorBase]:
        """Retrieve an indicator by its unique identifier."""
        cls._ensure_discovered()
        return cls._indicators.get(indicator_id)

    @classmethod
    def list_all(cls) -> List[IndicatorDefinition]:
        """List metadata definitions for all registered indicators."""
        cls._ensure_discovered()
        return [ind.get_definition() for ind in cls._indicators.values()]

    @classmethod
    def get_by_category(cls, category: IndicatorCategory) -> List[IndicatorDefinition]:
        """Filter indicators by category."""
        cls._ensure_discovered()
        return [
            ind.get_definition()
            for ind in cls._indicators.values()
            if ind.category == category
        ]

    @classmethod
    def get_by_lifecycle(cls, lifecycle: IndicatorLifecycle) -> List[IndicatorDefinition]:
        """Filter indicators by lifecycle stage."""
        cls._ensure_discovered()
        return [
            ind.get_definition()
            for ind in cls._indicators.values()
            if ind.lifecycle == lifecycle
        ]

    @classmethod
    async def sync_to_db(cls, session: AsyncSession) -> None:
        """Upsert all in-memory indicators into research_indicator_definitions table."""
        if session is None:
            return

        from sqlalchemy import text
        for indicator in cls._indicators.values():
            defn = indicator.get_definition()
            stmt = text("""
                INSERT INTO research_indicator_definitions (
                    indicator_id, name, category, description, author,
                    lifecycle, current_version, supported_timeframes,
                    supported_instruments, formula_summary, parameters_schema,
                    updated_at
                ) VALUES (
                    :indicator_id, :name, :category, :description, :author,
                    :lifecycle, :current_version, CAST(:supported_timeframes AS jsonb),
                    CAST(:supported_instruments AS jsonb), :formula_summary, CAST(:parameters_schema AS jsonb),
                    NOW()
                )
                ON CONFLICT (indicator_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    category = EXCLUDED.category,
                    description = EXCLUDED.description,
                    current_version = EXCLUDED.current_version,
                    supported_timeframes = EXCLUDED.supported_timeframes,
                    supported_instruments = EXCLUDED.supported_instruments,
                    formula_summary = EXCLUDED.formula_summary,
                    parameters_schema = EXCLUDED.parameters_schema,
                    updated_at = NOW();
            """)
            import json
            await session.execute(
                stmt,
                {
                    "indicator_id": defn.indicator_id,
                    "name": defn.name,
                    "category": defn.category.value if isinstance(defn.category, IndicatorCategory) else defn.category,
                    "description": defn.description,
                    "author": defn.author,
                    "lifecycle": defn.lifecycle.value if isinstance(defn.lifecycle, IndicatorLifecycle) else defn.lifecycle,
                    "current_version": defn.current_version,
                    "supported_timeframes": json.dumps(defn.supported_timeframes),
                    "supported_instruments": json.dumps(defn.supported_instruments),
                    "formula_summary": defn.formula_summary,
                    "parameters_schema": json.dumps(defn.parameters_schema),
                }
            )
        await session.commit()
        logger.info("synced_indicators_to_db", count=len(cls._indicators))

    @classmethod
    def clear(cls) -> None:
        """Clear the registry (mainly used in testing)."""
        cls._indicators.clear()


def register_indicator(cls_or_instance):
    """Decorator or helper to register an indicator."""
    if isinstance(cls_or_instance, type) and issubclass(cls_or_instance, IndicatorBase):
        instance = cls_or_instance()
        IndicatorRegistry.register(instance)
        return cls_or_instance
    elif isinstance(cls_or_instance, IndicatorBase):
        IndicatorRegistry.register(cls_or_instance)
        return cls_or_instance
    raise TypeError(f"Expected IndicatorBase subclass or instance, got {type(cls_or_instance)}")
