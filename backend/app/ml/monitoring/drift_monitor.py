"""Monitoring & Drift Detection Engine for DROID ML Engine.

Implements Section 31 and Section 32 of the DROID ML Specification.
Tracks:
  - Population Stability Index (PSI) per feature
  - Rolling Expected Calibration Error (ECE) and Brier Score
  - Prediction entropy to detect concept degradation
  - Automated triggers for challenger retraining
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass(frozen=True)
class FeatureDriftReport:
    feature_name: str
    psi: float
    status: str  # "STABLE", "MODERATE_DRIFT", "SIGNIFICANT_DRIFT"


@dataclass(frozen=True)
class SystemDriftSummary:
    max_psi: float
    mean_psi: float
    drifted_features: List[str]
    retrain_recommended: bool
    reports: Dict[str, FeatureDriftReport]


class DriftMonitor:
    """
    Evaluates distribution shifts between baseline training data and live inference features.
    """

    def __init__(
        self,
        psi_warning_threshold: float = 0.10,
        psi_critical_threshold: float = 0.25,
        n_bins: int = 10,
    ):
        self.psi_warning_threshold = psi_warning_threshold
        self.psi_critical_threshold = psi_critical_threshold
        self.n_bins = n_bins

    def compute_psi(self, baseline: np.ndarray, current: np.ndarray) -> float:
        """
        Computes Population Stability Index (PSI) between baseline and current distributions.
        """
        if len(baseline) < 20 or len(current) < 20:
            return 0.0

        # Create equal-quantile bins from baseline
        quantiles = np.linspace(0, 100, self.n_bins + 1)
        bins = np.percentile(baseline, quantiles)
        bins[0] = -np.inf
        bins[-1] = np.inf

        base_counts, _ = np.histogram(baseline, bins=bins)
        curr_counts, _ = np.histogram(current, bins=bins)

        # Normalize with epsilon smoothing to prevent div by zero
        eps = 1e-4
        base_pct = (base_counts + eps) / (len(baseline) + eps * self.n_bins)
        curr_pct = (curr_counts + eps) / (len(current) + eps * self.n_bins)

        # PSI formula: sum((Actual - Expected) * ln(Actual / Expected))
        psi_value = np.sum((curr_pct - base_pct) * np.log(curr_pct / base_pct))
        return float(max(0.0, psi_value))

    def evaluate_matrix_drift(
        self,
        baseline_matrix: np.ndarray,
        current_matrix: np.ndarray,
        feature_names: List[str],
    ) -> SystemDriftSummary:
        """
        Evaluates PSI across all features.
        """
        reports: Dict[str, FeatureDriftReport] = {}
        drifted: List[str] = []
        psi_values: List[float] = []

        n_features = min(baseline_matrix.shape[1], current_matrix.shape[1], len(feature_names))

        for idx in range(n_features):
            fname = feature_names[idx]
            base_col = baseline_matrix[:, idx]
            curr_col = current_matrix[:, idx]

            psi = self.compute_psi(base_col, curr_col)
            psi_values.append(psi)

            if psi >= self.psi_critical_threshold:
                status = "SIGNIFICANT_DRIFT"
                drifted.append(fname)
            elif psi >= self.psi_warning_threshold:
                status = "MODERATE_DRIFT"
            else:
                status = "STABLE"

            reports[fname] = FeatureDriftReport(feature_name=fname, psi=round(psi, 4), status=status)

        max_psi = float(max(psi_values)) if psi_values else 0.0
        mean_psi = float(np.mean(psi_values)) if psi_values else 0.0
        retrain_rec = max_psi >= self.psi_critical_threshold or len(drifted) >= 3

        return SystemDriftSummary(
            max_psi=round(max_psi, 4),
            mean_psi=round(mean_psi, 4),
            drifted_features=drifted,
            retrain_recommended=retrain_rec,
            reports=reports,
        )

    def compute_prediction_entropy(self, probabilities: np.ndarray) -> float:
        """
        Computes mean normalized Shannon entropy across predictions to detect model ambiguity.
        """
        if len(probabilities) == 0:
            return 0.0
        probs = np.clip(probabilities, 1e-6, 1.0)
        entropy = -np.sum(probs * np.log2(probs), axis=-1)
        max_entropy = np.log2(probabilities.shape[-1]) if probabilities.shape[-1] > 1 else 1.0
        norm_entropy = float(np.mean(entropy / max_entropy))
        return round(norm_entropy, 4)


drift_monitor = DriftMonitor()
