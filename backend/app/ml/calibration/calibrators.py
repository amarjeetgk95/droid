"""Probability Calibration Engine for DROID ML Engine.

Implements Section 22 of the DROID ML Specification.
Applies Platt scaling (logistic) and Isotonic regression to map raw model
outputs into true empirical probabilities. Computes Expected Calibration Error (ECE)
and Brier scores to ensure probabilities are reliable out-of-sample.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import joblib
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from app.ml.calibration_metrics import brier_score_3class, ece_equal_width


class ProbabilityCalibrator:
    """
    Fits Platt scaling or Isotonic regression on out-of-fold probabilities.
    """
    def __init__(self, method: Literal["platt", "isotonic"] = "platt"):
        self.method = method
        self.calibrator = None
        self.is_fitted = False
        self.ece_score: float = 1.0
        self.brier_score: float = 1.0

    def fit(self, raw_probs: np.ndarray, y_true: np.ndarray) -> ProbabilityCalibrator:
        """
        Fits calibration model on validation set.
        Args:
            raw_probs: 1D array of predicted probabilities [0.0, 1.0]
            y_true: 1D array of binary true labels {0, 1}
        """
        X = np.clip(raw_probs.reshape(-1, 1), 1e-6, 1.0 - 1e-6)
        y = y_true.astype(int)

        if self.method == "platt":
            # Platt scaling: fit logistic regression on logit features
            logits = np.log(X / (1.0 - X))
            self.calibrator = LogisticRegression(C=1.0, solver="lbfgs")
            self.calibrator.fit(logits, y)
            cal_probs = self.calibrator.predict_proba(logits)[:, 1]
        else:
            # Isotonic regression
            self.calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            self.calibrator.fit(raw_probs, y)
            cal_probs = self.calibrator.predict(raw_probs)

        # Compute post-calibration metrics
        self.brier_score = float(np.mean((cal_probs - y) ** 2))
        ece_res = ece_equal_width(y.tolist(), cal_probs.tolist(), n_bins=10)
        self.ece_score = float(ece_res.get("ece", 1.0))
        self.is_fitted = True
        return self

    def calibrate(self, raw_prob: float) -> float:
        """Calibrates a single probability float into an empirical event probability."""
        if not self.is_fitted or self.calibrator is None:
            return raw_prob

        p = float(np.clip(raw_prob, 1e-6, 1.0 - 1e-6))
        if self.method == "platt":
            logit = np.array([[np.log(p / (1.0 - p))]])
            return float(self.calibrator.predict_proba(logit)[0, 1])
        else:
            return float(self.calibrator.predict(np.array([p]))[0])

    def save(self, filepath: Path) -> None:
        bundle = {
            "method": self.method,
            "calibrator": self.calibrator,
            "ece_score": self.ece_score,
            "brier_score": self.brier_score,
            "is_fitted": self.is_fitted,
        }
        joblib.dump(bundle, filepath)

    @classmethod
    def load(cls, filepath: Path) -> ProbabilityCalibrator:
        bundle = joblib.load(filepath)
        inst = cls(method=bundle["method"])
        inst.calibrator = bundle["calibrator"]
        inst.ece_score = bundle["ece_score"]
        inst.brier_score = bundle["brier_score"]
        inst.is_fitted = bundle["is_fitted"]
        return inst
