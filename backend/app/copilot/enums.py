"""Canonical enums for the DROID Market Intelligence Copilot.

Single source of truth for every vocabulary that the API, the quantitative
engines and the frontend all share. Nothing outside this module may invent a
new directional word, horizon name or intent id — that is exactly how the old
UI ended up rendering a red BEARISH badge over a "NEUTRAL — rangebound" text.
"""
from __future__ import annotations

from typing import Literal

# --------------------------------------------------------------------------- #
# Instruments — DROID supports ONLY these three (never silently expand).
# --------------------------------------------------------------------------- #
CopilotSymbol = Literal["NIFTY", "BANKNIFTY", "SENSEX"]
SUPPORTED_SYMBOLS: tuple[str, ...] = ("NIFTY", "BANKNIFTY", "SENSEX")
DEFAULT_SYMBOL = "NIFTY"

# --------------------------------------------------------------------------- #
# Horizons
# --------------------------------------------------------------------------- #
Horizon = Literal[
    "NEXT_15_MIN",
    "NEXT_60_MIN",
    "TODAY",
    "NEXT_SESSION",
    "SWING_3_5_DAYS",
]

HORIZON_LABELS: dict[str, str] = {
    "NEXT_15_MIN": "NEXT 15 MIN",
    "NEXT_60_MIN": "NEXT 60 MIN",
    "TODAY": "TODAY",
    "NEXT_SESSION": "NEXT SESSION",
    "SWING_3_5_DAYS": "SWING 3–5 DAYS",
}

#: Horizons that the ML ensemble / historical analogue engine can be evaluated on.
HORIZON_MINUTES: dict[str, int | None] = {
    "NEXT_15_MIN": 15,
    "NEXT_60_MIN": 60,
    "TODAY": None,
    "NEXT_SESSION": None,
    "SWING_3_5_DAYS": None,
}

# --------------------------------------------------------------------------- #
# Intents (spec §3)
# --------------------------------------------------------------------------- #
CopilotIntent = Literal[
    "NEXT_SESSION_OUTLOOK",
    "INTRADAY_OUTLOOK",
    "MARKET_STATUS",
    "BREAKOUT_ANALYSIS",
    "OPTIONS_ANALYSIS",
    "SUPPORT_RESISTANCE",
    "SIGNAL_VALIDATION",
    "TRADE_SETUP_ANALYSIS",
    "REGIME_ANALYSIS",
    "WHY_MOVE",
    "HISTORICAL_ANALOG",
    "GENERAL_MARKET_QUESTION",
]

AnalysisDepth = Literal["BRIEF", "STANDARD", "DEEP"]

# --------------------------------------------------------------------------- #
# THE canonical directional state (spec §19)
# --------------------------------------------------------------------------- #
DirectionalState = Literal[
    "BULLISH",
    "MILD_BULLISH",
    "NEUTRAL",
    "MILD_BEARISH",
    "BEARISH",
    "NO_SIGNAL",
]

#: Quality/tone token shared with the frontend `badge b-*` classes.
DirectionalTone = Literal["bull", "bear", "neut", "warn"]

DIRECTION_TONE: dict[str, str] = {
    "BULLISH": "bull",
    "MILD_BULLISH": "bull",
    "NEUTRAL": "neut",
    "MILD_BEARISH": "bear",
    "BEARISH": "bear",
    "NO_SIGNAL": "warn",
}

#: Human display label — badges, titles and API `summary.bias` all read this.
DIRECTION_LABEL: dict[str, str] = {
    "BULLISH": "BULLISH",
    "MILD_BULLISH": "MILD BULLISH",
    "NEUTRAL": "NEUTRAL",
    "MILD_BEARISH": "MILD BEARISH",
    "BEARISH": "BEARISH",
    "NO_SIGNAL": "NO SIGNAL",
}

#: Signed weight used by the confluence engine.
DIRECTION_SIGN: dict[str, float] = {
    "BULLISH": 1.0,
    "MILD_BULLISH": 0.5,
    "NEUTRAL": 0.0,
    "MILD_BEARISH": -0.5,
    "BEARISH": -1.0,
    "NO_SIGNAL": 0.0,
}

FactorState = Literal["BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN"]

QualityGrade = Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]

SourceStatus = Literal["FRESH", "STALE", "UNAVAILABLE", "ERROR"]

DataFreshness = Literal["LIVE", "DELAYED", "STALE", "OFFLINE"]

LevelType = Literal[
    "PRIMARY_SUPPORT",
    "SECONDARY_SUPPORT",
    "PRIMARY_RESISTANCE",
    "SECONDARY_RESISTANCE",
]

ScenarioId = Literal["RANGE", "BULL_EXPANSION", "BEAR_EXPANSION"]

ProbabilityStatus = Literal["MODEL", "ESTIMATED", "UNAVAILABLE"]

GateStatus = Literal["PASS", "FAIL", "SKIPPED"]

ValidationVerdict = Literal["APPROVED", "REJECTED", "CONDITIONAL"]

FACTOR_KEYS: tuple[str, ...] = (
    "trend",
    "momentum",
    "volatility",
    "market_structure",
    "options_positioning",
    "futures_positioning",
    "institutional_flow",
    "liquidity",
    "breakout_pressure",
    "mean_reversion_pressure",
)

FACTOR_LABELS: dict[str, str] = {
    "trend": "Trend",
    "momentum": "Momentum",
    "volatility": "Volatility",
    "market_structure": "Structure",
    "options_positioning": "Options",
    "futures_positioning": "Futures",
    "institutional_flow": "Institutional",
    "liquidity": "Liquidity",
    "breakout_pressure": "Breakout",
    "mean_reversion_pressure": "Mean rev.",
}

# --------------------------------------------------------------------------- #
# Versioning (spec §36) — every analysis records what produced it.
# --------------------------------------------------------------------------- #
COPILOT_VERSION = "1.0"
FEATURE_ENGINE_VERSION = "copilot-features-1.0"
PREDICTION_ENGINE_VERSION = "copilot-prediction-1.0"
CALIBRATION_VERSION = "copilot-calibration-1.0"
PROMPT_VERSION = "copilot-explain-1.0"
ANALOG_ENGINE_VERSION = "copilot-analogs-1.0"
GATE_ENGINE_VERSION = "copilot-gates-1.0"
