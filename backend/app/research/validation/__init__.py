"""Validation package for the Research Laboratory.

Includes the Cheap Validation Gate, Statistical Evaluator, and Baseline Models.
"""

from app.research.validation.backtest_engine import (
    CheapValidationGate,
    WalkForwardGate,
    brier_score_3class,
    ece_equal_width,
    log_loss_3class,
)
from app.research.validation.baseline import (
    BaselineModel,
    BuyAndHoldBaseline,
    NaiveMomentumBaseline,
    RandomBaseline,
)
from app.research.validation.report import format_validation_markdown
from app.research.validation.statistical_evaluator import StatisticalEvaluator

__all__ = [
    "CheapValidationGate",
    "WalkForwardGate",
    "brier_score_3class",
    "log_loss_3class",
    "ece_equal_width",
    "StatisticalEvaluator",
    "BaselineModel",
    "RandomBaseline",
    "NaiveMomentumBaseline",
    "BuyAndHoldBaseline",
    "format_validation_markdown",
]
