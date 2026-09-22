"""
Probability Calibration Engine & Brier Score Diagnostics (§27).

Implements:
- Platt Scaling (Parametric Logistic Calibrator)
- Isotonic Regression (Non-parametric Piecewise Calibrator)
- Expected Calibration Error (ECE) and Maximum Calibration Error (MCE)
- Brier Score scoring rule evaluation
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression


@dataclass
class CalibrationDiagnostics:
    """Quantitative calibration quality diagnostics."""
    brier_score_uncalibrated: float
    brier_score_calibrated: float
    brier_skill_score: float  # Improvement over baseline
    expected_calibration_error: float  # ECE
    max_calibration_error: float  # MCE
    bin_confidences: List[float] = field(default_factory=list)
    bin_accuracies: List[float] = field(default_factory=list)
    bin_counts: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brier_score_uncalibrated": round(self.brier_score_uncalibrated, 4),
            "brier_score_calibrated": round(self.brier_score_calibrated, 4),
            "brier_skill_score": round(self.brier_skill_score, 4),
            "expected_calibration_error": round(self.expected_calibration_error, 4),
            "max_calibration_error": round(self.max_calibration_error, 4),
            "bin_confidences": [round(c, 3) for c in self.bin_confidences],
            "bin_accuracies": [round(a, 3) for a in self.bin_accuracies],
            "bin_counts": self.bin_counts,
        }


class ProbabilityCalibrator:
    """Calibrates model probability estimates into true empirical frequencies."""

    def __init__(self, method: str = "sigmoid"):
        """
        Args:
            method: 'sigmoid' (Platt scaling) or 'isotonic'.
        """
        self.method = method.lower()
        self.is_fitted = False
        if self.method == "isotonic":
            self._calibrator = IsotonicRegression(out_of_bounds="clip")
        else:
            self._calibrator = LogisticRegression(C=1.0, solver="lbfgs")

    def fit(self, raw_probs: np.ndarray, y_true: np.ndarray) -> ProbabilityCalibrator:
        """Fit calibrator on validation probabilities."""
        p = np.clip(np.asarray(raw_probs).ravel(), 1e-6, 1.0 - 1e-6)
        y = np.asarray(y_true).ravel()

        if len(np.unique(y)) < 2:
            self.is_fitted = False
            return self

        try:
            if self.method == "isotonic":
                self._calibrator.fit(p, y)
            else:
                # Platt scaling: train logistic regression on log-odds
                log_odds = np.log(p / (1.0 - p)).reshape(-1, 1)
                self._calibrator.fit(log_odds, y)
            self.is_fitted = True
        except Exception:
            self.is_fitted = False

        return self

    def calibrate(self, raw_probs: np.ndarray) -> np.ndarray:
        """Convert raw probabilities into calibrated probabilities."""
        p = np.clip(np.asarray(raw_probs).ravel(), 1e-6, 1.0 - 1e-6)
        if not self.is_fitted:
            return p

        if self.method == "isotonic":
            cal_p = self._calibrator.predict(p)
        else:
            log_odds = np.log(p / (1.0 - p)).reshape(-1, 1)
            cal_p = self._calibrator.predict_proba(log_odds)[:, 1]

        return np.clip(cal_p, 0.0, 1.0)

    @staticmethod
    def compute_diagnostics(
        raw_probs: np.ndarray,
        calibrated_probs: np.ndarray,
        y_true: np.ndarray,
        n_bins: int = 10,
    ) -> CalibrationDiagnostics:
        """Compute Brier Score, ECE, and reliability diagram bins."""
        y = np.asarray(y_true).ravel()
        p_raw = np.asarray(raw_probs).ravel()
        p_cal = np.asarray(calibrated_probs).ravel()
        N = len(y)

        # Brier scores
        bs_raw = float(np.mean((p_raw - y) ** 2))
        bs_cal = float(np.mean((p_cal - y) ** 2))
        bs_baseline = float(np.mean((np.mean(y) - y) ** 2)) if N > 0 else 1.0
        bss = 1.0 - (bs_cal / max(bs_baseline, 1e-6))

        # Reliability diagram and ECE
        bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
        bin_confs: List[float] = []
        bin_accs: List[float] = []
        bin_counts: List[int] = []

        ece = 0.0
        mce = 0.0

        for i in range(n_bins):
            low, high = bin_edges[i], bin_edges[i + 1]
            in_bin = (p_cal >= low) & (p_cal < high if i < n_bins - 1 else p_cal <= high)
            count = int(np.sum(in_bin))
            bin_counts.append(count)

            if count > 0:
                conf = float(np.mean(p_cal[in_bin]))
                acc = float(np.mean(y[in_bin]))
                bin_confs.append(conf)
                bin_accs.append(acc)
                err = abs(acc - conf)
                ece += (count / N) * err
                if err > mce:
                    mce = err
            else:
                bin_confs.append((low + high) / 2.0)
                bin_accs.append(0.0)

        return CalibrationDiagnostics(
            brier_score_uncalibrated=bs_raw,
            brier_score_calibrated=bs_cal,
            brier_skill_score=bss,
            expected_calibration_error=ece,
            max_calibration_error=mce,
            bin_confidences=bin_confs,
            bin_accuracies=bin_accs,
            bin_counts=bin_counts,
        )
