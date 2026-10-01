"""Auto-discovering indicator registry (§4).

Dropping a new ``indicators/<name>.py`` file that defines a ``BaseIndicator``
subclass is the entire integration step. Discovery walks the package with
``pkgutil`` and registers every concrete subclass it finds, so no import list,
enum, factory or route needs editing.

Explicit registration is also supported (``@register_indicator``) for
indicators that live outside this package — e.g. a strategy-owned indicator or
a test double.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import threading
from typing import Any, Iterable, Iterator, TypeVar

import structlog

from app.indicator_research.enums import IndicatorCategory
from app.indicator_research.indicators.base import BaseIndicator, IndicatorError

logger = structlog.get_logger(__name__)

T = TypeVar("T", bound=type)

#: Modules inside the package that never define indicators.
_SKIP_MODULES = {"base", "registry", "helpers", "__init__"}

_lock = threading.RLock()
_indicators: dict[str, BaseIndicator] = {}
_discovered = False
_registered_classes: set[type] = set()


class IndicatorRegistry:
    """In-memory registry of indicator *instances*, keyed by ``metadata.id``.

    Instances are stateless: ``calculate`` receives candles and params as
    arguments, so one shared instance is safe to reuse across concurrent
    requests. Nothing in an indicator may hold per-run state.
    """

    # -- registration ------------------------------------------------------
    @classmethod
    def register(cls, indicator: BaseIndicator | type) -> BaseIndicator:
        """Register an instance or class. Later registration wins (override)."""
        instance = cls._instantiate(indicator)
        with _lock:
            existing = _indicators.get(instance.indicator_id)
            if existing is not None and type(existing) is not type(instance):
                logger.warning(
                    "indicator_override",
                    indicator_id=instance.indicator_id,
                    previous=type(existing).__name__,
                    replacement=type(instance).__name__,
                )
            _indicators[instance.indicator_id] = instance
            _registered_classes.add(type(instance))
        return instance

    @staticmethod
    def _instantiate(indicator: BaseIndicator | type) -> BaseIndicator:
        if isinstance(indicator, type):
            if not issubclass(indicator, BaseIndicator):
                raise IndicatorError(
                    f"{indicator.__name__} is not a BaseIndicator subclass"
                )
            if inspect.isabstract(indicator):
                raise IndicatorError(
                    f"{indicator.__name__} is abstract (calculate not implemented)"
                )
            return indicator()
        if isinstance(indicator, BaseIndicator):
            return indicator
        raise IndicatorError(
            f"Expected a BaseIndicator instance or subclass, got {type(indicator).__name__}"
        )

    # -- discovery ---------------------------------------------------------
    @classmethod
    def discover(cls, force: bool = False) -> None:
        """Import every module in the package and register what it defines."""
        global _discovered
        with _lock:
            if _discovered and not force:
                return
            package = importlib.import_module("app.indicator_research.indicators")
            for module_info in pkgutil.iter_modules(package.__path__):
                name = module_info.name
                if name in _SKIP_MODULES or name.startswith("_"):
                    continue
                module_path = f"{package.__name__}.{name}"
                try:
                    module = importlib.import_module(module_path)
                except Exception as e:  # a broken indicator must not hide the rest
                    logger.error(
                        "indicator_module_import_failed",
                        module=module_path,
                        error=str(e)[:300],
                    )
                    continue
                if force:
                    module = importlib.reload(module)
                cls._register_from_module(module)
            _discovered = True

    @classmethod
    def _register_from_module(cls, module: Any) -> None:
        found: list[type] = []
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseIndicator)
                and obj is not BaseIndicator
                and not inspect.isabstract(obj)
                and obj.__module__ == module.__name__
            ):
                found.append(obj)
        # Deterministic order so the UI list is stable between restarts.
        for klass in sorted(found, key=lambda k: k.METADATA.name.lower()):
            if klass in _registered_classes:
                continue
            try:
                cls.register(klass)
            except Exception as e:
                logger.error(
                    "indicator_registration_failed",
                    indicator=klass.__name__,
                    error=str(e)[:300],
                )

    # -- lookup ------------------------------------------------------------
    @classmethod
    def get(cls, indicator_id: str) -> BaseIndicator | None:
        cls.discover()
        with _lock:
            return _indicators.get(indicator_id)

    @classmethod
    def get_or_raise(cls, indicator_id: str) -> BaseIndicator:
        indicator = cls.get(indicator_id)
        if indicator is None:
            available = sorted(cls.ids())
            raise IndicatorError(
                f"Unknown indicator '{indicator_id}'. Registered: {available}"
            )
        return indicator

    @classmethod
    def all(cls) -> list[BaseIndicator]:
        """Every registered indicator, ordered by category then display name."""
        cls.discover()
        with _lock:
            values = list(_indicators.values())
        order = {c: i for i, c in enumerate(IndicatorCategory.ui_order())}
        return sorted(
            values,
            key=lambda i: (order.get(i.category, 99), i.name.lower()),
        )

    @classmethod
    def ids(cls) -> tuple[str, ...]:
        cls.discover()
        with _lock:
            return tuple(sorted(_indicators))

    @classmethod
    def metadata(cls) -> list[dict[str, Any]]:
        """Serialisable metadata for every indicator — drives the whole UI."""
        return [indicator.metadata.to_dict() for indicator in cls.all()]

    @classmethod
    def by_category(cls, category: IndicatorCategory) -> list[BaseIndicator]:
        return [i for i in cls.all() if i.category is category]

    @classmethod
    def categories(cls) -> list[dict[str, Any]]:
        """Declared categories with their indicator counts (UI filter rail)."""
        counts: dict[IndicatorCategory, int] = {}
        for indicator in cls.all():
            counts[indicator.category] = counts.get(indicator.category, 0) + 1
        return [
            {"id": c.value, "label": c.value, "count": counts.get(c, 0)}
            for c in IndicatorCategory.ui_order()
        ]

    @classmethod
    def default_rules(cls, indicator_id: str) -> dict[str, Any] | None:
        indicator = cls.get(indicator_id)
        if indicator is None:
            return None
        rules = indicator.DEFAULT_RULES
        return dict(rules) if rules else None

    # -- test / admin hooks ------------------------------------------------
    @classmethod
    def clear(cls) -> None:
        """Drop all registrations (tests only)."""
        global _discovered
        with _lock:
            _indicators.clear()
            _registered_classes.clear()
            _discovered = False


def register_indicator(cls_or_instance: T) -> T:
    """Decorator / helper for explicit registration.

    ``@register_indicator`` on a class registers an instance of it; calling it
    with an instance registers that instance directly.
    """
    if isinstance(cls_or_instance, type):
        IndicatorRegistry.register(cls_or_instance)
        return cls_or_instance
    IndicatorRegistry.register(cls_or_instance)
    return cls_or_instance  # type: ignore[return-value]


def iter_indicators() -> Iterator[BaseIndicator]:
    """Iterate registered indicators (convenience for callers/tests)."""
    yield from IndicatorRegistry.all()


def indicators_for(*, categories: Iterable[IndicatorCategory] | None = None) -> list[BaseIndicator]:
    """Filter the registry by category."""
    if categories is None:
        return IndicatorRegistry.all()
    wanted = set(categories)
    return [i for i in IndicatorRegistry.all() if i.category in wanted]


__all__ = ["IndicatorRegistry", "iter_indicators", "indicators_for", "register_indicator"]
