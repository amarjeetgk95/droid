"""Pydantic data models for the Chart Intelligence & Indicator Research Laboratory."""

from datetime import date, datetime
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.research.enums import (
    DataQualityStatus,
    Direction,
    ExperimentStatus,
    ExpiryBucket,
    ForecastHorizon,
    IndicatorCategory,
    IndicatorLifecycle,
    MarketRegime,
    MarketSession,
)


class IndicatorDefinition(BaseModel):
    """Registry entry for an indicator (§13)."""
    indicator_id: str
    name: str
    category: IndicatorCategory
    description: Optional[str] = None
    author: str = "system"
    lifecycle: IndicatorLifecycle = IndicatorLifecycle.EXPERIMENTAL
    current_version: str = "0.1.0"
    supported_timeframes: list[str] = Field(default_factory=lambda: ["1m", "5m", "15m", "1h", "1D"])
    supported_instruments: list[str] = Field(default_factory=lambda: ["NIFTY 50", "BANKNIFTY", "SENSEX"])
    formula_summary: Optional[str] = None
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class IndicatorVersion(BaseModel):
    """Version tracking for indicator calculation logic (§14)."""
    version_id: Optional[str] = None
    indicator_id: str
    version: str
    changelog: Optional[str] = None
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    code_hash: Optional[str] = None
    created_at: Optional[datetime] = None


class IndicatorContext(BaseModel):
    """Analytical context passed into indicator.calculate(context)."""
    instrument: str
    timeframe: str
    timestamp: datetime
    candles: list[dict[str, Any]]  # List of OHLCV dicts (ascending time)
    current_price: float
    options_context: Optional[dict[str, Any]] = None
    market_regime: Optional[MarketRegime] = None
    session: Optional[MarketSession] = None
    features: Optional[dict[str, Any]] = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class IndicatorOutput(BaseModel):
    """Standard Indicator Output Contract (§46).
    
    Every research indicator must output this exact structure.
    Enables plug-and-play comparison, ranking, and validation.
    """
    indicator_id: str
    version: str
    timestamp: datetime
    instrument: str
    timeframe: str
    direction: Direction
    score: float = Field(ge=-100.0, le=100.0, description="Normalized score between -100 and +100")
    confidence: float = Field(ge=0.0, le=1.0, description="Analytical confidence between 0.0 and 1.0")
    raw_value: Optional[Any] = None
    normalized_value: Optional[float] = None
    component_values: dict[str, Any] = Field(default_factory=dict, description="§17: Full transparency breakdown")
    regime_context: Optional[str] = None
    horizon: ForecastHorizon = ForecastHorizon.HORIZON_15M
    horizon_candles: int = 5
    target_price: Optional[float] = None
    invalidation_price: Optional[float] = None
    data_quality: DataQualityStatus = DataQualityStatus.LIVE
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchSnapshot(BaseModel):
    """Point-in-time capture of full market state (§25)."""
    snapshot_id: str
    instrument: str
    timeframe: str
    timestamp: datetime
    price: float
    regime: Optional[str] = None
    session: Optional[str] = None
    features: dict[str, Any] = Field(default_factory=dict)
    options_context: Optional[dict[str, Any]] = None
    data_quality: DataQualityStatus = DataQualityStatus.LIVE
    created_at: Optional[datetime] = None


class ResearchPrediction(BaseModel):
    """Immutable prediction record (§26, N5).
    
    Once inserted, this record is permanent and can never be updated.
    """
    prediction_id: str
    indicator_id: str
    indicator_version: str
    instrument: str
    timeframe: str
    timestamp: datetime
    current_price: float
    direction: Direction
    score: float = Field(ge=-100.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0)
    raw_value: Optional[Any] = None
    normalized_value: Optional[float] = None
    component_values: dict[str, Any] = Field(default_factory=dict)
    forecast_horizon: ForecastHorizon = ForecastHorizon.HORIZON_15M
    horizon_candles: int = 5
    target_price: Optional[float] = None
    invalidation_price: Optional[float] = None
    snapshot_id: Optional[str] = None
    created_at: Optional[datetime] = None


class PredictionOutcome(BaseModel):
    """Separate append-only outcome record (§26, N5).
    
    Created only after the forecast horizon has elapsed.
    """
    outcome_id: str
    prediction_id: str
    actual_direction: Direction
    actual_price_move: float
    actual_pct_move: float
    entry_price: float
    exit_price: float
    mfe: float  # Maximum Favorable Excursion
    mae: float  # Maximum Adverse Excursion
    target_hit: bool = False
    stop_hit: bool = False
    time_to_target_sec: Optional[float] = None
    is_correct: bool
    evaluated_at: Optional[datetime] = None


class ExperimentDefinition(BaseModel):
    """Configuration for an offline validation experiment (§19, §39)."""
    experiment_id: str
    name: str
    description: Optional[str] = None
    indicator_id: str
    indicator_version: str
    instrument: str
    timeframe: str
    forecast_horizon: ForecastHorizon = ForecastHorizon.HORIZON_15M
    start_date: date
    end_date: date
    parameters: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class ExperimentRun(BaseModel):
    """Run execution state and summary metrics for an experiment."""
    run_id: str
    experiment_id: str
    status: ExperimentStatus = ExperimentStatus.PENDING
    sample_count: int = 0
    metrics: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ValidationReport(BaseModel):
    """Statistical validation report with confidence intervals and baseline comparison (§21)."""
    sample_size: int
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    mfe_mean: float
    mae_mean: float
    win_loss_ratio: float
    baseline_accuracy: float
    excess_accuracy: float
    confidence_interval_95: tuple[float, float]
    p_value: float
    is_statistically_significant: bool
    regime_breakdown: dict[str, dict[str, float]] = Field(default_factory=dict)
    session_breakdown: dict[str, dict[str, float]] = Field(default_factory=dict)


class ComparisonResult(BaseModel):
    """Comparative benchmarking results for multiple indicators (§30, §31)."""
    comparison_id: str
    name: str
    indicators: list[str]
    instrument: str
    timeframe: str
    rankings: list[dict[str, Any]] = Field(default_factory=list)
    correlation_matrix: dict[str, dict[str, float]] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class ResearchAnnotation(BaseModel):
    """Chart annotation and qualitative note (§47)."""
    annotation_id: str
    instrument: str
    timeframe: str
    timestamp: datetime
    title: str
    notes: str
    author: str = "researcher"
    tags: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
