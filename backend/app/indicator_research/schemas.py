"""Request models for the Indicator Research API.

``extra="forbid"`` everywhere is a research-integrity decision, not pedantry: a
misspelled ``stop_mode`` that silently fell back to "no stop" would produce a
backtest the user did not ask for and would not notice.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

_STRICT = ConfigDict(extra="forbid", populate_by_name=True)

MAX_INDICATORS_PER_RUN = 8


class IndicatorSpecModel(BaseModel):
    """One selected indicator and the parameters to evaluate it with."""

    model_config = _STRICT

    indicator_id: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)


class DataSelection(BaseModel):
    """Which candles the run should read."""

    model_config = _STRICT

    instrument: str = Field(default="NIFTY", min_length=1, max_length=32)
    timeframe: str = Field(default="5m", min_length=1, max_length=8)
    start: date | None = None
    end: date | None = None
    version: str | None = Field(default=None, max_length=32)
    max_bars: int | None = Field(default=None, ge=30, le=250_000)

    @model_validator(mode="after")
    def _check_range(self) -> "DataSelection":
        if self.start and self.end and self.end < self.start:
            raise ValueError("'end' must not be before 'start'")
        return self


class RuleSet(BaseModel):
    """Long and short signal rules as structured JSON.

    ``use_indicator_defaults`` falls back to the primary indicator's shipped
    rules when the caller supplies none — convenient, and the response always
    states which rules actually ran.
    """

    model_config = _STRICT

    long: dict[str, Any] | None = None
    short: dict[str, Any] | None = None
    use_indicator_defaults: bool = False


class ResearchRequest(BaseModel):
    """Shared base: candles to read, indicators to compute."""

    model_config = _STRICT

    data: DataSelection
    indicators: list[IndicatorSpecModel] = Field(
        min_length=1, max_length=MAX_INDICATORS_PER_RUN
    )
    rules: RuleSet = Field(default_factory=RuleSet)


class PreviewRequest(ResearchRequest):
    """Chart payload: candles plus indicator outputs, limited for the wire."""

    model_config = _STRICT

    preview_bars: int = Field(default=1500, ge=50, le=20_000)


class BacktestRequest(ResearchRequest):
    """One full backtest."""

    model_config = _STRICT

    settings: dict[str, Any] = Field(default_factory=dict)
    verify_causality: bool = True
    include_trades: bool = True
    include_equity_curve: bool = True
    max_equity_points: int = Field(default=2000, ge=50, le=20_000)


class OptimizeRequest(ResearchRequest):
    """Parameter grid or random search over the primary indicator."""

    model_config = _STRICT

    settings: dict[str, Any] = Field(default_factory=dict)
    objective: str = Field(default="total_return_pct", max_length=64)
    search_mode: str = Field(default="grid", pattern="^(grid|random)$")
    seed: int = Field(default=42, ge=0)
    max_combinations: int = Field(default=200, ge=1, le=2000)
    min_trades: int = Field(default=5, ge=1, le=1000)
    parameter_overrides: dict[str, list[Any]] = Field(default_factory=dict)


class SelectivityRequest(ResearchRequest):
    """Threshold selectivity sweep across a range of values."""

    model_config = _STRICT

    feature: str = Field(min_length=1, max_length=64)
    operator: str = Field(default=">", max_length=16)
    thresholds: list[float] = Field(min_length=2, max_length=100)
    direction: str = Field(default="long", pattern="^(long|short)$")
    settings: dict[str, Any] = Field(default_factory=dict)
    secondary_rule: dict[str, Any] | None = None
    forward_horizon: int = Field(default=5, ge=1, le=200)
    min_trades: int = Field(default=10, ge=1, le=1000)


class RobustnessRequest(ResearchRequest):
    """Parameter perturbation and cost stress testing."""

    model_config = _STRICT

    settings: dict[str, Any] = Field(default_factory=dict)
    perturbation_pcts: list[float] = Field(
        default_factory=lambda: [-0.20, -0.10, 0.10, 0.20], min_length=1, max_length=20
    )
    cost_multipliers: list[float] = Field(
        default_factory=lambda: [1.0, 1.5, 2.0, 3.0], min_length=1, max_length=10
    )


class AblationRequest(ResearchRequest):
    """Component contribution analysis for multi-indicator setups."""

    model_config = _STRICT

    settings: dict[str, Any] = Field(default_factory=dict)
    objective: str = Field(default="sharpe_annualized", max_length=64)



class WalkForwardRequest(ResearchRequest):
    """Chronological walk-forward with purge."""

    model_config = _STRICT

    settings: dict[str, Any] = Field(default_factory=dict)
    objective: str = Field(default="total_return_pct", max_length=64)
    folds: int = Field(default=5, ge=2, le=20)
    purge_bars: int = Field(default=5, ge=0, le=500)
    max_combinations: int = Field(default=60, ge=1, le=500)
    min_trades: int = Field(default=5, ge=1, le=1000)
    parameter_overrides: dict[str, list[Any]] = Field(default_factory=dict)


class CompareRequest(BaseModel):
    """Run several indicators through one identical harness."""

    model_config = _STRICT

    data: DataSelection
    indicator_ids: list[str] = Field(min_length=2, max_length=12)
    rules: RuleSet = Field(default_factory=RuleSet)
    use_default_rules: bool = True
    settings: dict[str, Any] = Field(default_factory=dict)
    objective: str = Field(default="total_return_pct", max_length=64)


class CompareRulesRequest(BaseModel):
    """One indicator, several signal definitions."""

    model_config = _STRICT

    data: DataSelection
    indicator_id: str = Field(min_length=1, max_length=64)
    rule_sets: list[dict[str, Any]] = Field(min_length=2, max_length=20)
    settings: dict[str, Any] = Field(default_factory=dict)
    objective: str = Field(default="total_return_pct", max_length=64)


class PredictionRequest(BaseModel):
    """Forward-return prediction analysis for one signal definition."""

    model_config = _STRICT

    data: DataSelection
    indicators: list[IndicatorSpecModel] = Field(
        min_length=1, max_length=MAX_INDICATORS_PER_RUN
    )
    rules: RuleSet = Field(default_factory=RuleSet)
    horizons: list[int] = Field(default_factory=lambda: [1, 2, 3, 5, 10, 20])


class SaveExperimentRequest(BaseModel):
    """Persist a research configuration and its result summary."""

    model_config = _STRICT

    name: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    config: dict[str, Any]
    result_summary: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    data_provenance: dict[str, Any] = Field(default_factory=dict)


class RenameExperimentRequest(BaseModel):
    """Rename or re-note an existing experiment."""

    model_config = _STRICT

    name: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=4000)


__all__ = [
    "MAX_INDICATORS_PER_RUN",
    "AblationRequest",
    "BacktestRequest",
    "CompareRequest",
    "CompareRulesRequest",
    "DataSelection",
    "IndicatorSpecModel",
    "OptimizeRequest",
    "PredictionRequest",
    "PreviewRequest",
    "RenameExperimentRequest",
    "ResearchRequest",
    "RobustnessRequest",
    "RuleSet",
    "SaveExperimentRequest",
    "SelectivityRequest",
    "WalkForwardRequest",
]

