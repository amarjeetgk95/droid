"""The indicator contract every research indicator implements (§3, §39).

Adding an indicator is meant to be a one-file change:

1. create ``indicators/<name>.py``
2. subclass :class:`BaseIndicator` and declare ``METADATA``
3. implement ``calculate``

The registry discovers the module automatically, the API exposes the metadata,
the UI renders parameter controls from it, the chart renders the declared
outputs and the backtest engine consumes them. No other file changes.

Causality contract
------------------
``calculate`` receives the *whole* candle series and returns full-length output
series. The value at index ``i`` may depend only on ``candles[0..i]``. That is
what makes a single vectorised pass safe for a strictly sequential backtest:
the engine reads ``output[i]`` when it reaches bar ``i`` and never looks ahead.
``backtesting.validation`` proves the property per indicator by recomputing on
truncated prefixes and comparing, so a centred average or a whole-sample
normalisation is caught rather than silently believed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, ClassVar, Mapping, Sequence

from app.indicator_research.enums import (
    IndicatorCategory,
    OutputRole,
    OutputType,
    PaneHint,
    ParameterType,
)

Candle = Mapping[str, Any]


class IndicatorError(ValueError):
    """Raised for an invalid parameter set or a malformed indicator output."""


class InputRequirement(str, Enum):
    """Data an indicator needs beyond a plain OHLCV candle (extensibility, §39).

    The data adapter reports which requirements the loaded series satisfies, so
    a future order-flow indicator (``DROID Predictive Flow Index``) can declare
    ``ORDER_BOOK`` / ``TRADES`` and be refused with a precise reason instead of
    silently computing on incomplete input.
    """

    OHLCV = "ohlcv"
    VOLUME = "volume"
    VWAP = "vwap"
    TICK = "tick"
    TRADES = "trades"
    ORDER_BOOK = "order_book"
    MARKET_DEPTH = "market_depth"
    OPTIONS = "options"


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ParameterSpec:
    """One auto-generated UI control.

    ``min`` / ``max`` / ``step`` drive the slider bounds; the backend clamps to
    them as well, so an optimizer grid or a hand-written JSON body can never
    put a strategy into an unrepresentable state.
    """

    name: str
    type: ParameterType
    default: Any
    min: float | int | None = None
    max: float | int | None = None
    step: float | int | None = None
    label: str | None = None
    description: str | None = None
    options: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        if self.options is not None:
            d["options"] = list(self.options)
        d["label"] = self.label or self.name
        return d


@dataclass(frozen=True)
class OutputSpec:
    """One declared output series: how to chart it and what it means."""

    name: str
    role: OutputRole = OutputRole.LINE
    pane: PaneHint = PaneHint.SEPARATE
    label: str | None = None
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["role"] = self.role.value
        d["pane"] = self.pane.value
        d["label"] = self.label or self.name
        return d


@dataclass(frozen=True)
class IndicatorMetadata:
    """Everything the UI, chart and engine need, declared once per indicator."""

    id: str
    name: str
    category: IndicatorCategory
    description: str
    output_type: OutputType
    parameters: tuple[ParameterSpec, ...] = ()
    outputs: tuple[OutputSpec, ...] = ()
    requires: tuple[InputRequirement, ...] = (InputRequirement.OHLCV,)
    formula_summary: str = ""
    version: str = "1.0.0"
    tags: tuple[str, ...] = ()
    reference: str | None = None
    supports_backtest: bool = True
    supports_prediction: bool = True
    supports_realtime: bool = True
    warmup_period: int | None = None

    # -- convenience -------------------------------------------------------
    def parameter_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.parameters)

    def output_names(self) -> tuple[str, ...]:
        return tuple(o.name for o in self.outputs)

    def price_overlay_outputs(self) -> tuple[str, ...]:
        return tuple(o.name for o in self.outputs if o.pane is PaneHint.PRICE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "output_type": self.output_type.value,
            "parameters": [p.to_dict() for p in self.parameters],
            "outputs": [o.to_dict() for o in self.outputs],
            "requires": [r.value for r in self.requires],
            "formula_summary": self.formula_summary,
            "version": self.version,
            "tags": list(self.tags),
            "reference": self.reference,
            "supports_backtest": self.supports_backtest,
            "supports_prediction": self.supports_prediction,
            "supports_realtime": self.supports_realtime,
            "warmup_period": self.warmup_period,
            "overlay_or_oscillator": "overlay" if self.output_type.value == "overlay" else "oscillator",
        }


# --------------------------------------------------------------------------- #
# Calculation result
# --------------------------------------------------------------------------- #
@dataclass
class IndicatorResult:
    """Full-length, index-aligned output series for one indicator run."""

    indicator_id: str
    version: str
    params: dict[str, Any]
    outputs: dict[str, list[float | bool | None]]
    length: int
    warmup_bars: int
    warmup_complete: bool = True

    def series(self, name: str) -> list[float | bool | None]:
        if name not in self.outputs:
            raise IndicatorError(
                f"Indicator '{self.indicator_id}' has no output '{name}'. "
                f"Declared outputs: {sorted(self.outputs)}"
            )
        return self.outputs[name]

    def to_dict(self) -> dict[str, Any]:
        return {
            "indicator_id": self.indicator_id,
            "version": self.version,
            "params": dict(self.params),
            "length": self.length,
            "warmup_bars": self.warmup_bars,
            "warmup_complete": self.warmup_complete,
            "outputs": {k: list(v) for k, v in self.outputs.items()},
        }


# --------------------------------------------------------------------------- #
# Base class
# --------------------------------------------------------------------------- #
class BaseIndicator(ABC):
    """Abstract contract for every research indicator.

    Subclasses declare ``METADATA`` at class level and implement ``calculate``.
    ``__init_subclass__`` refuses a concrete subclass with no metadata, which is
    what keeps "add a file and it shows up everywhere" honest: a forgotten
    metadata block fails at import time with a clear message rather than
    producing a control-less, unlabelled indicator in the UI.
    """

    METADATA: ClassVar[IndicatorMetadata]

    #: Optional ready-made signal rules so a new indicator is usable straight
    #: away without the user hand-building a rule set. Shape matches
    #: ``signals.rules`` (see that module's docstring).
    DEFAULT_RULES: ClassVar[dict[str, Any] | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        concrete = not getattr(cls.calculate, "__isabstractmethod__", False)
        if concrete and not isinstance(cls.__dict__.get("METADATA"), IndicatorMetadata):
            raise TypeError(
                f"{cls.__name__} must declare a class-level "
                "METADATA = IndicatorMetadata(...) block"
            )

    # -- metadata ----------------------------------------------------------
    @property
    def metadata(self) -> IndicatorMetadata:
        return self.METADATA

    @property
    def indicator_id(self) -> str:
        return self.METADATA.id

    @property
    def name(self) -> str:
        return self.METADATA.name

    @property
    def version(self) -> str:
        return self.METADATA.version

    @property
    def category(self) -> IndicatorCategory:
        return self.METADATA.category

    @property
    def parameters(self) -> tuple[ParameterSpec, ...]:
        return self.METADATA.parameters

    @property
    def outputs(self) -> tuple[OutputSpec, ...]:
        return self.METADATA.outputs

    # -- parameters --------------------------------------------------------
    def default_params(self) -> dict[str, Any]:
        return {spec.name: spec.default for spec in self.parameters}

    def resolve_params(self, params: Mapping[str, Any] | None) -> dict[str, Any]:
        """Merge, coerce and clamp a user parameter mapping.

        Unknown keys are rejected rather than ignored: silently dropping a typo
        would run a different experiment than the one the user configured, and
        the result would carry the user's label.
        """
        resolved: dict[str, Any] = {}
        provided = dict(params or {})
        known = self.metadata.parameter_names()
        unknown = sorted(set(provided) - set(known))
        if unknown:
            raise IndicatorError(
                f"Unknown parameter(s) for '{self.indicator_id}': {unknown}. "
                f"Accepted: {sorted(known) or 'none'}"
            )
        for spec in self.parameters:
            raw = provided.get(spec.name, spec.default)
            resolved[spec.name] = self._coerce(spec, raw)
        return resolved

    @staticmethod
    def _coerce(spec: ParameterSpec, raw: Any) -> Any:
        try:
            if spec.type is ParameterType.INTEGER:
                value: Any = int(round(float(raw)))
            elif spec.type is ParameterType.NUMBER:
                value = float(raw)
            elif spec.type is ParameterType.BOOLEAN:
                if isinstance(raw, str):
                    value = raw.strip().lower() in {"1", "true", "yes", "on"}
                else:
                    value = bool(raw)
            elif spec.type is ParameterType.CHOICE:
                text = str(raw)
                if spec.options and text not in spec.options:
                    raise IndicatorError(
                        f"Parameter '{spec.name}' must be one of {list(spec.options)}, got '{text}'"
                    )
                value = text
            else:
                value = str(raw)
        except IndicatorError:
            raise
        except (TypeError, ValueError):
            raise IndicatorError(
                f"Parameter '{spec.name}' expects {spec.type.value}, got {raw!r}"
            ) from None

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if spec.min is not None and value < spec.min:
                value = type(value)(spec.min)
            if spec.max is not None and value > spec.max:
                value = type(value)(spec.max)
        return value

    # -- calculation -------------------------------------------------------
    @abstractmethod
    def calculate(
        self,
        candles: Sequence[Candle],
        params: Mapping[str, Any],
    ) -> dict[str, list[Any]]:
        """Return one full-length series per declared output.

        Must be causal: ``series[i]`` may only use ``candles[0..i]``. Use
        ``None`` inside the warm-up window — never ``0``.
        """

    def generate_signals(
        self,
        outputs: Mapping[str, Sequence[Any]],
        params: Mapping[str, Any],
    ) -> dict[str, list[bool]]:
        """Optional built-in signal generation.

        Returns ``{}`` by default. The primary research path is the structured
        signal builder, which composes rules over any declared output; this hook
        exists for signal-only indicators whose definition *is* the signal.
        """
        return {}

    # -- orchestration -----------------------------------------------------
    def compute(
        self,
        candles: Sequence[Candle],
        params: Mapping[str, Any] | None = None,
    ) -> IndicatorResult:
        """Validate, run and package a calculation."""
        resolved = self.resolve_params(params)
        length = len(candles)
        if length == 0:
            return IndicatorResult(
                indicator_id=self.indicator_id,
                version=self.version,
                params=resolved,
                outputs={spec.name: [] for spec in self.outputs},
                length=0,
                warmup_bars=0,
                warmup_complete=False,
            )

        raw = self.calculate(candles, resolved) or {}
        declared = set(self.metadata.output_names())
        produced = set(raw)
        undeclared = sorted(produced - declared)
        if undeclared:
            raise IndicatorError(
                f"'{self.indicator_id}' returned undeclared output(s) {undeclared}; "
                f"declare them in METADATA.outputs: {sorted(declared)}"
            )

        outputs: dict[str, list[Any]] = {}
        for spec in self.outputs:
            values = list(raw.get(spec.name, [None] * length))
            if len(values) != length:
                raise IndicatorError(
                    f"'{self.indicator_id}' output '{spec.name}' has length {len(values)}, "
                    f"expected {length} to align with the candle series"
                )
            outputs[spec.name] = values

        warmup, complete = _warmup_bars(outputs)
        return IndicatorResult(
            indicator_id=self.indicator_id,
            version=self.version,
            params=resolved,
            outputs=outputs,
            length=length,
            warmup_bars=warmup,
            warmup_complete=complete,
        )


def _warmup_bars(outputs: Mapping[str, Sequence[Any]]) -> tuple[int, bool]:
    """First index where every output has a defined value.

    Returns ``(index, complete)``. ``complete`` is False when no bar ever has
    all outputs defined (e.g. a signal-only indicator that is always empty) —
    the caller surfaces that instead of pretending the series is ready.
    """
    if not outputs:
        return 0, False
    length = max(len(v) for v in outputs.values())
    for i in range(length):
        if all(i < len(v) and v[i] is not None for v in outputs.values()):
            return i, True
    return length, False


__all__ = [
    "BaseIndicator",
    "Candle",
    "IndicatorError",
    "IndicatorMetadata",
    "IndicatorResult",
    "InputRequirement",
    "OutputSpec",
    "ParameterSpec",
]
