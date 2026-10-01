"""HTTP surface for Indicator Research (§2, §43).

Every endpoint in this module is read-only against stored history and
append-only against the experiment directory. None of them can reach a broker,
an order router or a live position; that property is asserted statically by
:mod:`app.indicator_research.safety` and surfaced at ``GET /isolation``.

Responses are plain JSON objects. When data is unavailable the endpoint returns
``ok: false`` with an explicit reason and the data provenance, rather than an
empty success payload that a chart would happily render as "no signals".
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import structlog
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.indicator_research.backtesting.costs import REFERENCE_COSTS_V1, ZERO_COSTS
from app.indicator_research.backtesting.settings import settings_from_payload
from app.indicator_research.data import (
    DEFAULT_MAX_BARS,
    SUPPORTED_INSTRUMENTS,
    SUPPORTED_TIMEFRAMES,
    CandleSeries,
    dataset_catalog,
    load_candles,
)
from app.indicator_research.indicators.helpers import PRICE_COLUMNS
from app.indicator_research.indicators.registry import IndicatorRegistry
from app.indicator_research.presets import get_preset, list_presets
from app.indicator_research.research import ablation as ablation_mod
from app.indicator_research.research import analysis as analysis_mod
from app.indicator_research.research import comparison as comparison_mod
from app.indicator_research.research import experiments as experiments_mod
from app.indicator_research.research import optimizer as optimizer_mod
from app.indicator_research.research import robustness as robustness_mod
from app.indicator_research.research import selectivity as selectivity_mod
from app.indicator_research.research import walkforward as walkforward_mod
from app.indicator_research.research.features import (
    IndicatorSpec,
    available_features,
    build_features,
    default_rule_set,
    operator_catalog,
)
from app.indicator_research.research.runner import run_once
from app.indicator_research.safety import isolation_report
from app.indicator_research.schemas import (
    AblationRequest,
    BacktestRequest,
    CompareRequest,
    CompareRulesRequest,
    DataSelection,
    OptimizeRequest,
    PredictionRequest,
    PreviewRequest,
    RenameExperimentRequest,
    RobustnessRequest,
    SaveExperimentRequest,
    SelectivityRequest,
    WalkForwardRequest,
)

from app.indicator_research.signals.rules import (
    describe_rule,
    normalize_rule,
    unknown_features,
    validate_rule,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/indicator-research", tags=["Indicator Research"])

_ISOLATION_BADGE = {
    "research_only": True,
    "message": "Research only — this module cannot place, modify or close an order.",
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _load(selection: DataSelection) -> CandleSeries:
    return await load_candles(
        selection.instrument,
        selection.timeframe,
        selection.start,
        selection.end,
        version=selection.version,
        max_bars=selection.max_bars or DEFAULT_MAX_BARS,
    )


def _unavailable(series: CandleSeries, **extra: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "error": series.reason or "The requested candle series is unavailable.",
        "data": series.to_dict(),
        **_ISOLATION_BADGE,
        **extra,
    }


def _specs(indicators: Sequence[Any]) -> list[IndicatorSpec]:
    return [
        IndicatorSpec(item.indicator_id, dict(item.params), "primary" if i == 0 else "overlay")
        for i, item in enumerate(indicators)
    ]


def _resolve_rules(
    rules: Any, primary_id: str
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None, str]:
    """Pick the rules to run and say where they came from."""
    if rules.long is not None or rules.short is not None:
        return rules.long, rules.short, "custom"
    if rules.use_indicator_defaults:
        defaults = default_rule_set(primary_id) or {}
        long_rule = defaults.get("long")
        short_rule = defaults.get("short")
        if long_rule is None and short_rule is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"'{primary_id}' ships no default signal rule, so a rule must be "
                    "built before it can be tested."
                ),
            )
        return long_rule, short_rule, "indicator_default"
    raise HTTPException(
        status_code=422,
        detail=(
            "No signal rule was supplied. Build a long/short rule, or set "
            "rules.use_indicator_defaults to use the indicator's shipped defaults."
        ),
    )


def _settings(payload: Mapping[str, Any] | None):
    try:
        return settings_from_payload(payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


def _rule_problems(
    rules: Any, primary_id: str, rules_source: str
) -> dict[str, Any]:
    """Validate both rule halves against the features this run will expose."""
    known = available_features(primary_id)
    return {
        "available_features": known,
        "long": validate_rule(rules[0], known),
        "short": validate_rule(rules[1], known),
        "source": rules_source,
        "long_summary": describe_rule(normalize_rule(rules[0])) if rules[0] else "no rule",
        "short_summary": describe_rule(normalize_rule(rules[1])) if rules[1] else "no rule",
    }


def _resolve_missing_features(
    build: Any, rules: tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]
) -> list[str]:
    """Features a rule references that this indicator set does not produce."""
    known = set(build.features) | set(PRICE_COLUMNS)
    missing: set[str] = set()
    for rule in rules:
        missing.update(unknown_features(rule, known))
    return sorted(missing)


def _assert_rules_resolvable(
    build: Any, rules: tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]
) -> None:
    missing = _resolve_missing_features(build, rules)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=(
                f"The signal rule references feature(s) {missing}, which this indicator "
                f"set does not produce. Available features: {sorted(set(build.features) | set(PRICE_COLUMNS))}"
            ),
        )


def _window(length: int, preview_bars: int) -> tuple[int, int, int]:
    """Most-recent window of at most ``preview_bars`` bars, plus its step."""
    if length <= preview_bars:
        return 0, length, 1
    step = max(1, length // preview_bars)
    start = length - preview_bars * step
    return max(0, start), length, step


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
@router.get("/indicators", summary="List every registered indicator and its metadata")
async def list_indicators() -> dict[str, Any]:
    """Drives the indicator library, parameter controls and operator picker."""
    metadata = IndicatorRegistry.metadata()
    for meta in metadata:
        meta["default_rules"] = default_rule_set(meta["id"])
    return {
        "count": len(metadata),
        "indicators": metadata,
        "categories": IndicatorRegistry.categories(),
        "operators": operator_catalog(),
        "price_columns": list(PRICE_COLUMNS),
        "instruments": list(SUPPORTED_INSTRUMENTS),
        "timeframes": list(SUPPORTED_TIMEFRAMES),
        **_ISOLATION_BADGE,
    }


@router.get("/indicators/{indicator_id}", summary="Metadata for one indicator")
async def get_indicator(indicator_id: str) -> dict[str, Any]:
    indicator = IndicatorRegistry.get(indicator_id)
    if indicator is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown indicator '{indicator_id}'. Registered: "
                f"{list(IndicatorRegistry.ids())}"
            ),
        )
    return {
        "ok": True,
        "metadata": indicator.metadata.to_dict(),
        "default_rules": default_rule_set(indicator_id),
        "parameter_space": optimizer_mod.parameter_space(indicator_id),
        "available_features": available_features(indicator_id),
        **_ISOLATION_BADGE,
    }


@router.get("/catalog", summary="Available historical datasets and reference settings")
async def catalog() -> dict[str, Any]:
    catalog_payload = await dataset_catalog()
    return {
        "ok": True,
        **catalog_payload,
        "reference_costs": REFERENCE_COSTS_V1.to_dict(),
        "zero_costs": ZERO_COSTS.to_dict(),
        "execution_models": [
            {
                "id": "next_open",
                "label": "Signal at close → entry at next open",
                "description": "Default. The only fill model that cannot overstate results.",
            },
            {
                "id": "signal_close",
                "label": "Signal and entry at the signal bar's close",
                "description": (
                    "Optimistic: assumes the close that produced the signal was still "
                    "available to trade. Use only for explicit A/B comparison."
                ),
            },
        ],
        "stop_modes": ["none", "percent", "atr", "points"],
        "objectives": list(optimizer_mod.OBJECTIVE_WHITELIST),
        **_ISOLATION_BADGE,
    }


@router.get("/isolation", summary="Static proof that research cannot reach live trading")
async def isolation() -> dict[str, Any]:
    return isolation_report()


# --------------------------------------------------------------------------- #
# Chart preview
# --------------------------------------------------------------------------- #
@router.post("/features", summary="Candles plus indicator outputs for the research chart")
async def preview_features(request: PreviewRequest) -> dict[str, Any]:
    series = await _load(request.data)
    if not series.available:
        return _unavailable(series)

    specs = _specs(request.indicators)
    build = build_features(series.candles, specs)
    if not build.ok:
        return {
            "ok": False,
            "error": "; ".join(build.errors),
            "data": series.to_dict(),
            "warnings": build.warnings,
            **_ISOLATION_BADGE,
        }

    primary_id = build.primary_id or specs[0].indicator_id
    try:
        long_rule, short_rule, source = _resolve_rules(request.rules, primary_id)
    except HTTPException as e:
        long_rule, short_rule, source = None, None, f"none ({e.detail})"

    from app.indicator_research.signals.rules import evaluate_series

    length = len(series.candles)
    missing = _resolve_missing_features(build, (long_rule, short_rule))
    if missing:
        # A draft rule may legitimately reference a feature the user has not
        # added yet. The chart still renders; the signal layer stays empty and
        # the reason travels with the response.
        long_signals = [False] * length
        short_signals = [False] * length
        build.warnings.append(
            f"Signals not evaluated: the rule references {missing}, which this "
            "indicator set does not produce. Add the missing indicator to the feature set."
        )
    else:
        long_signals = evaluate_series(long_rule, build.features, length)
        short_signals = evaluate_series(short_rule, build.features, length)
        for i in range(min(build.warmup_bars, length)):
            long_signals[i] = False
            short_signals[i] = False

    start, end, step = _window(length, request.preview_bars)
    candles = [
        {
            "index": i,
            "time": series.candles[i].get("timestamp"),
            "open": series.candles[i].get("open"),
            "high": series.candles[i].get("high"),
            "low": series.candles[i].get("low"),
            "close": series.candles[i].get("close"),
            "volume": series.candles[i].get("volume"),
        }
        for i in range(start, end, step)
    ]
    outputs = {name: list(values)[start:end:step] for name, values in build.features.items()}

    return {
        "ok": True,
        "data": series.to_dict(),
        "candles": candles,
        "outputs": outputs,
        "indicators": build.resolved_specs,
        "warmup_bars": build.warmup_bars,
        "pane_map": {
            meta["id"]: {
                "output_type": meta["output_type"],
                "outputs": {
                    out["name"]: {"role": out["role"], "pane": out["pane"]}
                    for out in meta["outputs"]
                },
            }
            for meta in IndicatorRegistry.metadata()
            if meta["id"] in {spec.indicator_id for spec in specs}
        },
        "signals": {
            "long": [i for i in range(start, end, step) if long_signals[i]],
            "short": [i for i in range(start, end, step) if short_signals[i]],
        },
        "rule_summary": {
            "long": describe_rule(normalize_rule(long_rule)) if long_rule else "no rule",
            "short": describe_rule(normalize_rule(short_rule)) if short_rule else "no rule",
            "source": source,
        },
        "rule_problems": _rule_problems((long_rule, short_rule), primary_id, source),
        "window": {"start_index": start, "end_index": end, "step": step, "bars": len(candles)},
        "warnings": build.warnings + series.warnings,
        **_ISOLATION_BADGE,
    }


# --------------------------------------------------------------------------- #
# Backtest
# --------------------------------------------------------------------------- #
@router.post("/backtest", summary="Run one no-lookahead backtest")
async def run_backtest(request: BacktestRequest) -> dict[str, Any]:
    series = await _load(request.data)
    if not series.available:
        return _unavailable(series)

    specs = _specs(request.indicators)
    # Indicators first: "unknown indicator 'nope'" is a more useful complaint
    # than "this indicator ships no default rule".
    _prebuild = build_features(series.candles, specs)
    if not _prebuild.ok:
        return {
            "ok": False,
            "error": "; ".join(_prebuild.errors),
            "data": series.to_dict(),
            **_ISOLATION_BADGE,
        }
    primary_id = request.indicators[0].indicator_id
    long_rule, short_rule, source = _resolve_rules(request.rules, primary_id)
    settings = _settings(request.settings)
    _assert_rules_resolvable(_prebuild, (long_rule, short_rule))

    logger.info(
        "indicator_research_backtest",
        instrument=request.data.instrument,
        timeframe=request.data.timeframe,
        indicator=primary_id,
        bars=series.bars,
        entry_fill=settings.execution.entry_fill,
    )

    outcome = run_once(
        candles=series.candles,
        specs=specs,
        long_rule=long_rule,
        short_rule=short_rule,
        settings=settings,
        instrument=request.data.instrument,
        timeframe=series.timeframe,
        verify_causality=request.verify_causality,
        requested_start=request.data.start.isoformat() if request.data.start else None,
        requested_end=request.data.end.isoformat() if request.data.end else None,
        prebuilt=_prebuild,
    )

    if not outcome.ok or outcome.result is None:
        return {
            "ok": False,
            "error": outcome.error,
            "data": series.to_dict(),
            "feature_build": outcome.feature_build,
            **_ISOLATION_BADGE,
        }

    payload = outcome.result.to_dict(
        include_trades=request.include_trades,
        include_equity_curve=request.include_equity_curve,
        max_equity_points=request.max_equity_points,
    )
    payload.update(
        {
            "data": series.to_dict(),
            "feature_build": outcome.feature_build,
            "rule_source": source,
            "rule_problems": _rule_problems((long_rule, short_rule), primary_id, source),
            "warnings": series.warnings,
            **_ISOLATION_BADGE,
        }
    )
    return payload


# --------------------------------------------------------------------------- #
# Optimization / walk-forward / comparison
# --------------------------------------------------------------------------- #
@router.post("/optimize", summary="Grid-search the primary indicator's parameters")
async def optimize_parameters(request: OptimizeRequest) -> dict[str, Any]:
    series = await _load(request.data)
    if not series.available:
        return _unavailable(series)

    specs = _specs(request.indicators)
    primary_id = request.indicators[0].indicator_id
    long_rule, short_rule, source = _resolve_rules(request.rules, primary_id)
    settings = _settings(request.settings)
    _assert_rules_resolvable(build_features(series.candles, specs), (long_rule, short_rule))
    try:
        result = optimizer_mod.optimize(
            candles=series.candles,
            specs=specs,
            long_rule=long_rule,
            short_rule=short_rule,
            settings=settings,
            objective=request.objective,
            search_mode=request.search_mode,
            seed=request.seed,
            max_combinations=request.max_combinations,
            min_trades=request.min_trades,
            parameter_overrides=request.parameter_overrides,
            instrument=request.data.instrument,
            timeframe=series.timeframe,
        )
    except optimizer_mod.OptimizationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    return {
        "ok": True,
        "data": series.to_dict(),
        "rule_source": source,
        **result,
        **_ISOLATION_BADGE,
    }


@router.post("/selectivity", summary="Threshold selectivity sweep across a range of values")
async def run_selectivity(request: SelectivityRequest) -> dict[str, Any]:
    series = await _load(request.data)
    if not series.available:
        return _unavailable(series)

    specs = _specs(request.indicators)
    build = build_features(series.candles, specs)
    if not build.ok:
        return {"ok": False, "error": "; ".join(build.errors), "data": series.to_dict(), **_ISOLATION_BADGE}

    settings = _settings(request.settings)
    result = selectivity_mod.sweep_selectivity(
        candles=series.candles,
        specs=specs,
        feature=request.feature,
        operator=request.operator,
        thresholds=request.thresholds,
        direction=request.direction,
        settings=settings,
        secondary_rule=request.secondary_rule,
        forward_horizon=request.forward_horizon,
        min_trades=request.min_trades,
        instrument=request.data.instrument,
        timeframe=series.timeframe,
        prebuilt=build,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("error", "Selectivity sweep failed"))

    return {"ok": True, "data": series.to_dict(), **result, **_ISOLATION_BADGE}


@router.post("/robustness", summary="Parameter perturbation and cost stress testing")
async def run_robustness(request: RobustnessRequest) -> dict[str, Any]:
    series = await _load(request.data)
    if not series.available:
        return _unavailable(series)

    specs = _specs(request.indicators)
    primary_id = request.indicators[0].indicator_id
    long_rule, short_rule, source = _resolve_rules(request.rules, primary_id)
    settings = _settings(request.settings)
    _assert_rules_resolvable(build_features(series.candles, specs), (long_rule, short_rule))

    result = robustness_mod.run_robustness_test(
        candles=series.candles,
        specs=specs,
        long_rule=long_rule,
        short_rule=short_rule,
        settings=settings,
        perturbation_pcts=request.perturbation_pcts,
        cost_multipliers=request.cost_multipliers,
        instrument=request.data.instrument,
        timeframe=series.timeframe,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("error", "Robustness test failed"))

    return {"ok": True, "data": series.to_dict(), "rule_source": source, **result, **_ISOLATION_BADGE}


@router.post("/ablation", summary="Component contribution analysis for multi-indicator setups")
async def run_ablation(request: AblationRequest) -> dict[str, Any]:
    series = await _load(request.data)
    if not series.available:
        return _unavailable(series)

    specs = _specs(request.indicators)
    primary_id = request.indicators[0].indicator_id
    long_rule, short_rule, source = _resolve_rules(request.rules, primary_id)
    settings = _settings(request.settings)
    _assert_rules_resolvable(build_features(series.candles, specs), (long_rule, short_rule))

    result = ablation_mod.run_ablation_study(
        candles=series.candles,
        specs=specs,
        long_rule=long_rule,
        short_rule=short_rule,
        settings=settings,
        objective=request.objective,
        instrument=request.data.instrument,
        timeframe=series.timeframe,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("error", "Ablation study failed"))

    return {"ok": True, "data": series.to_dict(), "rule_source": source, **result, **_ISOLATION_BADGE}


@router.get("/presets", summary="List canonical research presets")
async def get_presets() -> dict[str, Any]:
    return {"ok": True, "presets": list_presets(), **_ISOLATION_BADGE}


@router.get("/presets/{preset_id}", summary="Get one canonical research preset")
async def get_preset_by_id(preset_id: str) -> dict[str, Any]:
    preset = get_preset(preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found.")
    return {"ok": True, "preset": preset, **_ISOLATION_BADGE}



@router.post("/walkforward", summary="Chronological walk-forward validation")
async def walk_forward(request: WalkForwardRequest) -> dict[str, Any]:
    series = await _load(request.data)
    if not series.available:
        return _unavailable(series)

    specs = _specs(request.indicators)
    primary_id = request.indicators[0].indicator_id
    long_rule, short_rule, source = _resolve_rules(request.rules, primary_id)
    settings = _settings(request.settings)
    _assert_rules_resolvable(build_features(series.candles, specs), (long_rule, short_rule))
    try:
        result = walkforward_mod.walk_forward(
            candles=series.candles,
            specs=specs,
            long_rule=long_rule,
            short_rule=short_rule,
            settings=settings,
            folds=request.folds,
            purge_bars=request.purge_bars,
            objective=request.objective,
            max_combinations=request.max_combinations,
            min_trades=request.min_trades,
            parameter_overrides=request.parameter_overrides,
            instrument=request.data.instrument,
            timeframe=series.timeframe,
        )
    except optimizer_mod.OptimizationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    return {
        "ok": True,
        "data": series.to_dict(),
        "rule_source": source,
        **result,
        **_ISOLATION_BADGE,
    }


@router.post("/compare", summary="Run several indicators through one harness")
async def compare(request: CompareRequest) -> dict[str, Any]:
    series = await _load(request.data)
    if not series.available:
        return _unavailable(series)

    settings = _settings(request.settings)
    rules = request.rules
    try:
        result = comparison_mod.compare_indicators(
            candles=series.candles,
            indicator_ids=request.indicator_ids,
            settings=settings,
            long_rule=rules.long,
            short_rule=rules.short,
            use_default_rules=request.use_default_rules,
            objective=request.objective,
            instrument=request.data.instrument,
            timeframe=series.timeframe,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    return {"ok": True, "data": series.to_dict(), **result, **_ISOLATION_BADGE}


@router.post("/compare-rules", summary="Compare several signal definitions for one indicator")
async def compare_rules(request: CompareRulesRequest) -> dict[str, Any]:
    series = await _load(request.data)
    if not series.available:
        return _unavailable(series)

    settings = _settings(request.settings)
    try:
        result = comparison_mod.compare_rule_sets(
            candles=series.candles,
            indicator_id=request.indicator_id,
            rule_sets=request.rule_sets,
            settings=settings,
            objective=request.objective,
            instrument=request.data.instrument,
            timeframe=series.timeframe,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

    return {"ok": True, "data": series.to_dict(), **result, **_ISOLATION_BADGE}


# --------------------------------------------------------------------------- #
# Forward-return prediction analysis
# --------------------------------------------------------------------------- #
@router.post("/predict", summary="Forward-return study for a signal definition")
async def predict(request: PredictionRequest) -> dict[str, Any]:
    series = await _load(request.data)
    if not series.available:
        return _unavailable(series)

    specs = _specs(request.indicators)
    build = build_features(series.candles, specs)
    if not build.ok:
        return {
            "ok": False,
            "error": "; ".join(build.errors),
            "data": series.to_dict(),
            **_ISOLATION_BADGE,
        }

    primary_id = build.primary_id or specs[0].indicator_id
    long_rule, short_rule, source = _resolve_rules(request.rules, primary_id)
    _assert_rules_resolvable(build, (long_rule, short_rule))

    from app.indicator_research.signals.rules import evaluate_series

    length = len(series.candles)
    long_signals = evaluate_series(long_rule, build.features, length)
    short_signals = evaluate_series(short_rule, build.features, length)
    for i in range(min(build.warmup_bars, length)):
        long_signals[i] = False
        short_signals[i] = False

    horizons = sorted({int(h) for h in request.horizons if 1 <= int(h) <= 500})
    if not horizons:
        raise HTTPException(status_code=422, detail="At least one horizon between 1 and 500 is required.")

    date_range = {
        "start": series.data_start,
        "end": series.data_end,
        "requested_start": request.data.start.isoformat() if request.data.start else None,
        "requested_end": request.data.end.isoformat() if request.data.end else None,
    }

    studies: dict[str, Any] = {}
    for label, rule, signals, direction in (
        ("long", long_rule, long_signals, 1.0),
        ("short", short_rule, short_signals, -1.0),
    ):
        indices = [i for i, fired in enumerate(signals) if fired]
        if not indices:
            studies[label] = {
                "signal_definition": describe_rule(normalize_rule(rule)) if rule else "no rule",
                "n_signals": 0,
                "horizons": {},
                "note": "This rule produced no signals in the requested range.",
            }
            continue
        studies[label] = analysis_mod.prediction_analysis(
            candles=series.candles,
            signal_indices=indices,
            instrument=request.data.instrument,
            timeframe=series.timeframe,
            signal_definition=describe_rule(normalize_rule(rule)) if rule else "no rule",
            direction=direction,
            horizons=horizons,
            date_range=date_range,
        )
        studies[label]["by_time_of_day"] = analysis_mod.time_of_day_returns(
            series.candles, indices, horizons[0], direction
        )

    return {
        "ok": True,
        "data": series.to_dict(),
        "rule_source": source,
        "rule_summaries": {
            "long": describe_rule(normalize_rule(long_rule)) if long_rule else "no rule",
            "short": describe_rule(normalize_rule(short_rule)) if short_rule else "no rule",
        },
        "studies": studies,
        "disclaimer": analysis_mod.DISCLAIMER,
        **_ISOLATION_BADGE,
    }


# --------------------------------------------------------------------------- #
# Experiments
# --------------------------------------------------------------------------- #
@router.post("/experiments", summary="Save a research configuration and its summary")
async def save_experiment(request: SaveExperimentRequest) -> dict[str, Any]:
    try:
        record = experiments_mod.save_experiment(
            request.config,
            name=request.name,
            notes=request.notes,
            tags=request.tags,
            result_summary=request.result_summary,
            validation=request.validation,
            data_provenance=request.data_provenance,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from None
    return {"ok": True, "experiment": record, **_ISOLATION_BADGE}


@router.get("/experiments", summary="List saved experiments")
async def list_experiments(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    items = experiments_mod.list_experiments(limit)
    return {"ok": True, "count": len(items), "experiments": items, **_ISOLATION_BADGE}


@router.get("/experiments/{experiment_id}", summary="Read one saved experiment")
async def get_experiment(experiment_id: str) -> dict[str, Any]:
    record = experiments_mod.get_experiment(experiment_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' was not found")
    return {"ok": True, "experiment": record, **_ISOLATION_BADGE}


@router.patch("/experiments/{experiment_id}", summary="Rename or annotate an experiment")
async def rename_experiment(
    experiment_id: str, request: RenameExperimentRequest
) -> dict[str, Any]:
    try:
        record = experiments_mod.rename_experiment(experiment_id, request.name, request.notes)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from None
    return {"ok": True, "experiment": record, **_ISOLATION_BADGE}


@router.delete("/experiments/{experiment_id}", summary="Delete a saved experiment")
async def delete_experiment(experiment_id: str) -> dict[str, Any]:
    removed = experiments_mod.delete_experiment(experiment_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' was not found")
    return {"ok": True, "deleted": experiment_id, **_ISOLATION_BADGE}


@router.get("/experiments/{experiment_id}/export", summary="Export an experiment")
async def export_experiment(
    experiment_id: str, format: str = Query("json", pattern="^(json|csv)$")
):
    try:
        content, media_type, filename = experiments_mod.export_experiment(experiment_id, format)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = ["router"]
