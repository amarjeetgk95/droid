"""Feature composition.

An experiment is not one indicator: the spec's own example rule is "Fisher
crosses above its signal **AND** close is above VWAP", and an ATR-based stop
needs an ATR series. So a research run carries a *set* of indicators — a primary
one plus any overlays — and this module merges their outputs into a single
index-aligned feature map for the rule engine and the backtester.

Collisions are resolved deterministically (first spec wins) and reported, never
silently overwritten, because two indicators producing a differently-defined
``signal`` column is exactly the kind of ambiguity that makes a saved
experiment unreproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.indicator_research.indicators.base import Candle
from app.indicator_research.indicators.helpers import PRICE_COLUMNS, ohlcv_features
from app.indicator_research.indicators.registry import IndicatorRegistry


@dataclass
class IndicatorSpec:
    """One indicator plus the parameters it should be evaluated with."""

    indicator_id: str
    params: dict[str, Any] = field(default_factory=dict)
    role: str = "overlay"  # "primary" | "overlay"

    def to_dict(self) -> dict[str, Any]:
        return {"indicator_id": self.indicator_id, "params": dict(self.params), "role": self.role}


@dataclass
class FeatureBuild:
    """Result of merging one or more indicator output sets."""

    features: dict[str, list[Any]] = field(default_factory=dict)
    resolved_specs: list[dict[str, Any]] = field(default_factory=list)
    owners: dict[str, str] = field(default_factory=dict)
    warmup_bars: int = 0
    primary_id: str | None = None
    primary_outputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolved_specs": self.resolved_specs,
            "owners": self.owners,
            "warmup_bars": self.warmup_bars,
            "primary_id": self.primary_id,
            "primary_outputs": list(self.primary_outputs),
            "features": sorted(self.features),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def build_features(
    candles: Sequence[Candle],
    specs: Sequence[IndicatorSpec],
) -> FeatureBuild:
    """Evaluate every spec and merge outputs into one feature map."""
    build = FeatureBuild()
    if not candles:
        build.errors.append("No candles were supplied, so no features could be built.")
        return build
    if not specs:
        build.errors.append("At least one indicator must be selected.")
        return build

    for position, spec in enumerate(specs):
        try:
            indicator = IndicatorRegistry.get_or_raise(spec.indicator_id)
        except Exception as e:
            build.errors.append(str(e))
            continue
        try:
            result = indicator.compute(candles, spec.params)
        except Exception as e:
            build.errors.append(
                f"Indicator '{spec.indicator_id}' failed: {type(e).__name__}: {e}"
            )
            continue

        if position == 0 and build.primary_id is None:
            build.primary_id = indicator.indicator_id
            build.primary_outputs = list(result.outputs)

        build.warmup_bars = max(build.warmup_bars, result.warmup_bars)
        if not result.warmup_complete:
            build.warnings.append(
                f"'{indicator.indicator_id}' produced no defined value for any bar "
                "with these parameters — its outputs cannot drive a rule."
            )
        build.resolved_specs.append(
            {
                "indicator_id": indicator.indicator_id,
                "version": indicator.version,
                "name": indicator.name,
                "category": indicator.category.value,
                "role": "primary" if position == 0 else "overlay",
                "params": result.params,
                "outputs": list(result.outputs),
            }
        )
        for name, values in result.outputs.items():
            if name in build.features:
                build.warnings.append(
                    f"Output '{name}' from '{indicator.indicator_id}' was ignored because "
                    f"'{build.owners.get(name)}' already defines it."
                )
                continue
            build.features[name] = list(values)
            build.owners[name] = indicator.indicator_id

    if not build.features and not build.errors:
        build.errors.append("No indicator outputs were produced.")
    return build


def make_feature_provider(
    specs: Sequence[IndicatorSpec],
) -> Any:
    """Build a callable that re-derives the full feature map from any candles.

    Handed to the causality checker so it can prove feature values — not just
    rule evaluation — are reproducible without future bars.
    """

    def provider(subset_candles: Sequence[Candle]) -> dict[str, Sequence[Any]]:
        merged: dict[str, Sequence[Any]] = dict(ohlcv_features(subset_candles))
        rebuilt = build_features(subset_candles, specs)
        merged.update(rebuilt.features)
        return merged

    return provider


def available_features(indicator_id: str) -> list[str]:
    """Feature names a rule may reference when this indicator is primary."""
    names = list(PRICE_COLUMNS)
    indicator = IndicatorRegistry.get(indicator_id)
    if indicator is not None:
        names.extend(indicator.metadata.output_names())
    names.extend(["atr", "vwap"])
    seen: list[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return seen


def operator_catalog() -> list[dict[str, Any]]:
    """Operator metadata for the visual rule builder (§8)."""
    from app.indicator_research.signals.rules import OPERATOR_DOCS

    return [
        {
            "name": doc.name,
            "label": doc.label,
            "description": doc.description,
            "operands": doc.operands,
            "takes_range": doc.takes_range,
        }
        for doc in OPERATOR_DOCS
    ]


def default_rule_set(indicator_id: str) -> dict[str, Any] | None:
    """The indicator's shipped default rules, if it has any."""
    rules = IndicatorRegistry.default_rules(indicator_id)
    if not rules:
        return None
    return rules


def match_mapping(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Reserved for future order-flow indicators (§39). Currently identity."""
    return dict(payload or {})


__all__ = [
    "FeatureBuild",
    "IndicatorSpec",
    "available_features",
    "build_features",
    "default_rule_set",
    "make_feature_provider",
    "operator_catalog",
]
