"""Abstract base class for all indicators in the Research Laboratory (§46)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from app.research.enums import IndicatorCategory, IndicatorLifecycle
from app.research.models import IndicatorContext, IndicatorDefinition, IndicatorOutput


@dataclass(frozen=True)
class IndicatorMetadata:
    """Data-driven identity/classification declared once per indicator class.

    Concrete indicators set a single class-level ``METADATA`` instance;
    :class:`IndicatorBase` exposes the historical per-field read-only
    properties (``indicator_id`` / ``name`` / ``version`` / ``category`` /
    ``lifecycle``) so registry, API and tests keep the same surface.
    """

    indicator_id: str
    name: str
    version: str
    category: IndicatorCategory
    lifecycle: IndicatorLifecycle = IndicatorLifecycle.EXPERIMENTAL


class IndicatorBase(ABC):
    """Abstract contract that every research indicator must implement.
    
    Adhering to this contract ensures:
    1. Consistent output format across all indicators
    2. Seamless evaluation in the cheap validation gate
    3. Plug-and-play inclusion in the comparison laboratory
    4. Deterministic backtesting without future leakages
    """

    METADATA: ClassVar[IndicatorMetadata]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # The five metadata fields are declared exactly once via METADATA;
        # concrete subclasses (those that implement calculate) must provide it.
        if not getattr(cls.calculate, "__isabstractmethod__", False) and not isinstance(
            cls.__dict__.get("METADATA"), IndicatorMetadata
        ):
            raise TypeError(
                f"{cls.__name__} must declare class-level METADATA = IndicatorMetadata(...)"
            )

    @property
    def indicator_id(self) -> str:
        """Unique machine-readable identifier (e.g., 'ompi', 'rsi', 'macd')."""
        return self.METADATA.indicator_id

    @property
    def name(self) -> str:
        """Human-readable display name."""
        return self.METADATA.name

    @property
    def version(self) -> str:
        """Semver string (e.g., '0.1.0')."""
        return self.METADATA.version

    @property
    def category(self) -> IndicatorCategory:
        """Indicator classification category."""
        return self.METADATA.category

    @property
    def lifecycle(self) -> IndicatorLifecycle:
        """Current maturity stage."""
        return self.METADATA.lifecycle

    @property
    def description(self) -> str:
        """Detailed analytical description."""
        return ""

    @property
    def author(self) -> str:
        """Indicator author or origin."""
        return "system"

    @property
    def supported_timeframes(self) -> list[str]:
        """Supported candle resolutions."""
        return ["1m", "5m", "15m", "1h", "1D"]

    @property
    def supported_instruments(self) -> list[str]:
        """Supported instruments."""
        return ["NIFTY 50", "BANKNIFTY", "SENSEX"]

    @property
    def formula_summary(self) -> str:
        """Mathematical or logical summary of the formula."""
        return ""

    @property
    def default_parameters(self) -> dict[str, Any]:
        """Default parameter values."""
        return {}

    def get_parameters_schema(self) -> dict[str, Any]:
        """Schema describing configurable parameters."""
        return {
            k: {"type": type(v).__name__, "default": v}
            for k, v in self.default_parameters.items()
        }

    def get_definition(self) -> IndicatorDefinition:
        """Return the registration definition for this indicator."""
        return IndicatorDefinition(
            indicator_id=self.indicator_id,
            name=self.name,
            category=self.category,
            description=self.description,
            author=self.author,
            lifecycle=self.lifecycle,
            current_version=self.version,
            supported_timeframes=self.supported_timeframes,
            supported_instruments=self.supported_instruments,
            formula_summary=self.formula_summary,
            parameters_schema=self.get_parameters_schema(),
        )

    @abstractmethod
    async def calculate(self, context: IndicatorContext) -> IndicatorOutput:
        """Compute indicator output from the given analytical context.
        
        Must adhere to PIT (Point-In-Time) integrity:
        Do not access any data timestamped after context.timestamp.
        """
        pass
