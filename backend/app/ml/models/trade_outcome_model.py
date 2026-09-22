"""Trade Outcome Meta-Label Model for DROID ML Engine.

Implements Section 14 and Section 15 of the DROID ML Specification.
The primary trade-level decision model predicting:
    P(T1 before SL)
    P(SL before T1)
    P(TIMEOUT)
and estimating expected adverse/favorable excursions:
    Expected MAE, Expected MFE (in R-multiples).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np

ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts"
CHALLENGER_DIR = ARTIFACTS_DIR / "challenger"
CHAMPION_DIR = ARTIFACTS_DIR / "champion"


class TradeOutcomeModel:
    def __init__(self, model_path: Optional[Path] = None, meta_path: Optional[Path] = None):
        self.classifier = None
        self.mfe_regressor = None
        self.mae_regressor = None
        self.calibrator = None
        self.meta: Dict[str, Any] = {}
        self._load(model_path, meta_path)

    def _load(self, model_path: Optional[Path], meta_path: Optional[Path]) -> None:
        target_model = model_path or (CHALLENGER_DIR / "trade_outcome_model.joblib")
        target_meta = meta_path or (CHALLENGER_DIR / "trade_outcome_meta.json")

        if not target_model.exists() and (CHAMPION_DIR / "trade_outcome_model.joblib").exists():
            target_model = CHAMPION_DIR / "trade_outcome_model.joblib"
            target_meta = CHAMPION_DIR / "trade_outcome_meta.json"

        if target_model.exists() and target_meta.exists():
            try:
                bundle = joblib.load(target_model)
                if isinstance(bundle, dict):
                    self.classifier = bundle.get("classifier")
                    self.mfe_regressor = bundle.get("mfe_regressor")
                    self.mae_regressor = bundle.get("mae_regressor")
                else:
                    self.classifier = bundle
                self.meta = json.loads(target_meta.read_text())

                cal_file = target_model.parent / "calibrator_trade_outcome.joblib"
                if cal_file.exists():
                    from app.ml.calibration.calibrators import ProbabilityCalibrator
                    self.calibrator = ProbabilityCalibrator.load(cal_file)
            except Exception:
                self.classifier = None

    def predict_trade_outcome(
        self,
        feature_vector: List[float],
        direction_prob: float = 0.50,
        breakout_prob: float = 0.50,
        risk_points: float = 25.0,
    ) -> Dict[str, Any]:
        """
        Predicts calibrated probability of Target 1 hit vs Stop Loss hit.

        Fail-closed honesty: unfitted returns status="fallback" with NULL
        probs (never blended heuristic). Callers MUST check
        `status`/`is_fallback`.
        """
        if self.classifier is None:
            # No trained model: fail-closed, never blend from direction/breakout.
            return {
                "p_target_before_stop": None,
                "p_stop_before_target": None,
                "p_timeout": None,
                "expected_mfe_r": None,
                "expected_mae_r": None,
                "is_fallback": True,
                "status": "fallback",
                "reason": "trade-outcome-model-unfitted-no-artifact",
                "model_version": "heuristic_outcome_baseline",
            }

        # Model input: feature vector augmented with upstream model signals
        augmented_vec = list(feature_vector) + [direction_prob, breakout_prob]
        X = np.array(augmented_vec).reshape(1, -1)

        probs = self.classifier.predict_proba(X)[0]
        # Class 0: STOP_FIRST, Class 1: TIMEOUT, Class 2: TARGET_FIRST
        p_sl = float(probs[0])
        p_timeout = float(probs[1]) if len(probs) > 1 else 0.0
        p_t1 = float(probs[2]) if len(probs) > 2 else float(probs[1])

        # Apply calibration if available
        if self.calibrator is not None and getattr(self.calibrator, "is_fitted", False):
            p_t1 = float(self.calibrator.calibrate(p_t1))
            rem = max(0.0, 1.0 - p_t1)
            sum_other = p_sl + p_timeout
            if sum_other > 0:
                p_sl = rem * (p_sl / sum_other)
                p_timeout = rem * (p_timeout / sum_other)
            else:
                p_sl = rem
                p_timeout = 0.0

        # Excursion estimates
        mfe_r = float(self.mfe_regressor.predict(X)[0]) if self.mfe_regressor else (p_t1 * 2.0)
        mae_r = float(self.mae_regressor.predict(X)[0]) if self.mae_regressor else (p_sl * 1.0)

        return {
            "p_target_before_stop": round(p_t1, 4),
            "p_stop_before_target": round(p_sl, 4),
            "p_timeout": round(p_timeout, 4),
            "expected_mfe_r": round(max(0.0, mfe_r), 2),
            "expected_mae_r": round(max(0.0, mae_r), 2),
            "is_fallback": False,
            "is_calibrated": bool(self.calibrator is not None and getattr(self.calibrator, "is_fitted", False)),
            "model_version": self.meta.get("model_version", "trade_outcome_v1"),
        }


trade_outcome_model = TradeOutcomeModel()
