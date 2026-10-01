"""One shared way to run a single configuration.

The optimizer, walk-forward, comparison and API layers all execute
"indicator specs + rules + settings over this candle slice". Having exactly one
implementation means a result from the optimizer is directly comparable with a
result from the backtest page — they ran the same code with the same defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.indicator_research.backtesting.engine import BacktestEngine
from app.indicator_research.backtesting.models import BacktestResult, BacktestSettings
from app.indicator_research.indicators.base import Candle
from app.indicator_research.indicators.registry import IndicatorRegistry
from app.indicator_research.research.features import (
    FeatureBuild,
    IndicatorSpec,
    build_features,
    make_feature_provider,
)


@dataclass
class RunOutcome:
    """Result of one configuration run, with its feature provenance."""

    ok: bool
    error: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    trade_count: int = 0
    signal_count: int = 0
    validation: dict[str, Any] = field(default_factory=dict)
    features: dict[str, Any] = field(default_factory=dict)
    feature_build: dict[str, Any] = field(default_factory=dict)
    result: BacktestResult | None = None

    def to_summary(self) -> dict[str, Any]:
        """Compact row for ranking tables (no trades, no equity curve)."""
        metrics = self.metrics
        return {
            "ok": self.ok,
            "error": self.error,
            "trade_count": self.trade_count,
            "signal_count": self.signal_count,
            "net_profit": metrics.get("net_profit"),
            "total_return_pct": metrics.get("total_return_pct"),
            "win_rate_pct": metrics.get("win_rate_pct"),
            "profit_factor": metrics.get("profit_factor"),
            "expectancy_per_trade": metrics.get("expectancy_per_trade"),
            "max_drawdown_pct": metrics.get("max_drawdown_pct"),
            "sharpe_annualized": metrics.get("sharpe_annualized"),
            "total_costs": metrics.get("total_costs"),
            "exposure_pct": metrics.get("exposure_pct"),
            "no_lookahead": self.validation.get("no_lookahead"),
        }


def run_once(
    *,
    candles: Sequence[Candle],
    specs: Sequence[IndicatorSpec],
    long_rule: Mapping[str, Any] | None,
    short_rule: Mapping[str, Any] | None,
    settings: BacktestSettings,
    instrument: str = "",
    timeframe: str = "",
    verify_causality: bool = True,
    requested_start: str | None = None,
    requested_end: str | None = None,
    prebuilt: FeatureBuild | None = None,
) -> RunOutcome:
    """Build features and run the engine once.

    ``prebuilt`` lets a caller that has already computed the feature map (for
    rule validation, or to render the chart) reuse it instead of paying for a
    second full indicator pass over the same candles.
    """
    build = prebuilt if prebuilt is not None else build_features(candles, specs)
    if not build.ok:
        return RunOutcome(
            ok=False,
            error="; ".join(build.errors),
            feature_build=build.to_dict(),
        )

    # Order-Flow data provenance guard
    order_flow_ids = {"cvd", "absorption", "dpfi"}
    requested_of = [s.indicator_id for s in specs if s.indicator_id in order_flow_ids]
    if requested_of and candles:
        sample = candles[:50]
        has_flow_data = any(
            c.get("trades") or (c.get("buy_volume") is not None and c.get("sell_volume") is not None) or (c.get("bids") and c.get("asks"))
            for c in sample
        ) or any(c.get("volume") is not None and float(c.get("volume") or 0) > 0 for c in sample)
        if not has_flow_data:
            return RunOutcome(
                ok=False,
                error=(
                    f"Order flow data is UNAVAILABLE for indicator(s) {requested_of}. "
                    "Microstructure analysis requires genuine trade/depth data or proxy volume records."
                ),
                feature_build=build.to_dict(),
            )


    is_primary = bool(build.resolved_specs)
    primary_spec = build.resolved_specs[0] if is_primary else None
    indicator = None
    if verify_causality and primary_spec is not None:
        indicator = IndicatorRegistry.get(primary_spec["indicator_id"])

    result = BacktestEngine().run(
        candles=candles,
        features=build.features,
        long_rule=long_rule,
        short_rule=short_rule,
        settings=settings,
        instrument=instrument,
        timeframe=timeframe,
        indicator_id=primary_spec["indicator_id"] if primary_spec else None,
        indicator_version=primary_spec["version"] if primary_spec else None,
        params=primary_spec["params"] if primary_spec else {},
        output_names=build.primary_outputs,
        warmup_bars=build.warmup_bars,
        requested_start=requested_start,
        requested_end=requested_end,
        indicator=indicator,
        run_indicator_causality_check=verify_causality,
    )

    if not result.ok:
        return RunOutcome(
            ok=False,
            error=result.error,
            feature_build=build.to_dict(),
            result=result,
        )

    # The full feature-recompute check is the strongest proof; use it whenever a
    # provider can rebuild every feature from a prefix (the common case).
    if verify_causality:
        from app.indicator_research.backtesting.validation import validate_backtest

        result.validation = validate_backtest(
            candles=candles,
            features=build.features,
            long_rule=long_rule,
            short_rule=short_rule,
            long_signals=[
                i in set(result.signals.get("long", [])) for i in range(len(candles))
            ],
            short_signals=[
                i in set(result.signals.get("short", [])) for i in range(len(candles))
            ],
            trades=result.trades,
            settings=settings,
            warmup_bars=build.warmup_bars,
            feature_provider=make_feature_provider(specs),
        )

    return RunOutcome(
        ok=True,
        metrics=result.metrics,
        trade_count=len(result.trades),
        signal_count=len(result.signals.get("long", [])) + len(result.signals.get("short", [])),
        validation=result.validation,
        features=build.features,
        feature_build=build.to_dict(),
        result=result,
    )


__all__ = ["RunOutcome", "run_once"]
