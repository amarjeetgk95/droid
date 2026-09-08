from datetime import datetime
from pydantic import BaseModel, Field
from typing import Literal


class MLFeatureContribution(BaseModel):
    feature_name: str
    value: float
    contribution: float  # -1.0 (strongly bearish) to +1.0 (strongly bullish)
    description: str


class MLPredictionResponse(BaseModel):
    symbol: str
    timestamp: datetime
    spot_price: float
    bullish_pct: float = Field(ge=0.0, le=100.0)
    neutral_pct: float = Field(ge=0.0, le=100.0)
    bearish_pct: float = Field(ge=0.0, le=100.0)
    trend_strength: float = Field(ge=0.0, le=100.0)
    confidence_score: float = Field(ge=0.0, le=100.0)
    predicted_bias: Literal["BULLISH", "NEUTRAL", "BEARISH"]
    market_regime: str
    top_features: list[MLFeatureContribution] = Field(default_factory=list)
    model_version: str = "XGBoost-LightGBM-Ensemble-v1.0"
    # Phase 0 multi-horizon fields: WHAT horizon the label covers, HOW the
    # label is defined, and WHETHER any trained model backs this horizon.
    horizon_minutes: int = 15
    target_spec_version: str = "v1-atr-band"
    model_source: Literal["xgboost_lightgbm_ensemble", "heuristic_ensemble"] = "heuristic_ensemble"
    calibrated: bool = False
    # ATR at prediction time — required input for later outcome labeling
    # (neutral band = 0.25 x ATR). 0.0 means unavailable (unsettllable).
    atr_at_t: float = 0.0
