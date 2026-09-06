"""
Options Intelligence Module
Provides Black-Scholes Greeks, IV solving, path-dependent option simulation,
and quantitative strike/expiry selection for Indian index options.
"""
from app.signals.options_intelligence.greeks import (
    BlackScholesGreeks,
    GreeksResult,
    norm_cdf,
    norm_pdf,
)
from app.signals.options_intelligence.path_simulator import (
    PathDependentOptionSimulator,
    PathSimulationReport,
    ScenarioOutcome,
    IndianOptionCosts,
)
from app.signals.options_intelligence.selector import (
    QuantitativeContractSelector,
    StrikeSelectionResult,
    EvaluatedStrikeCandidate,
    quantitative_contract_selector,
)
from app.signals.expected_move import (
    ExpectedMoveEngine,
    ExpectedMoveProjection,
    TradingHorizon,
    DirectionalBias,
    expected_move_engine,
)

__all__ = [
    "BlackScholesGreeks",
    "GreeksResult",
    "norm_cdf",
    "norm_pdf",
    "PathDependentOptionSimulator",
    "PathSimulationReport",
    "ScenarioOutcome",
    "IndianOptionCosts",
    "QuantitativeContractSelector",
    "StrikeSelectionResult",
    "EvaluatedStrikeCandidate",
    "quantitative_contract_selector",
    "ExpectedMoveEngine",
    "ExpectedMoveProjection",
    "TradingHorizon",
    "DirectionalBias",
    "expected_move_engine",
]
