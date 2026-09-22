"""Market Regime Model for DROID ML Engine.

Implements Section 10 of the DROID ML Specification.
Classifies the market environment into:
    TREND_UP, TREND_DOWN, RANGE, HIGH_VOL, LOW_VOL, VOL_EXPANSION
Provides calibrated class probability distributions for downstream models.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np

from app.ml.features.schema import FEATURE_NAMES_V3

REGIME_CLASSES = [
    "TREND_UP",
    "TREND_DOWN",
    "RANGE",
    "HIGH_VOL",
    "LOW_VOL",
    "VOL_EXPANSION",
]

ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts"
CHALLENGER_DIR = ARTIFACTS_DIR / "challenger"
CHAMPION_DIR = ARTIFACTS_DIR / "champion"


class RegimeModel:
    def __init__(self, model_path: Optional[Path] = None, meta_path: Optional[Path] = None):
        self.model = None
        self.meta: Dict[str, Any] = {}
        self._load(model_path, meta_path)

    def _load(self, model_path: Optional[Path], meta_path: Optional[Path]) -> None:
        target_model = model_path or (CHALLENGER_DIR / "regime_model.joblib")
        target_meta = meta_path or (CHALLENGER_DIR / "regime_meta.json")

        if not target_model.exists() and (CHAMPION_DIR / "regime_model.joblib").exists():
            target_model = CHAMPION_DIR / "regime_model.joblib"
            target_meta = CHAMPION_DIR / "regime_meta.json"

        if target_model.exists() and target_meta.exists():
            try:
                self.model = joblib.load(target_model)
                self.meta = json.loads(target_meta.read_text())
            except Exception:
                self.model = None

    def predict_regime(self, feature_vector: List[float]) -> Dict[str, Any]:
        """
        Predicts regime distribution and primary regime.

        Fail-closed honesty: unfitted returns status="fallback" with NULL
        regime/probabilities (never 50/10 heuristic). Callers MUST check
        `status`/`is_fallback` — a fallback is not a prediction.
        """
        if self.model is None:
            # No trained model: fail-closed, never fabricate 50/10 probs.
            return {
                "regime": None,
                "probabilities": None,
                "is_fallback": True,
                "status": "fallback",
                "reason": "regime-model-unfitted-no-artifact",
                "model_version": "heuristic_baseline",
            }

        X = np.array(feature_vector).reshape(1, -1)
        probs_arr = self.model.predict_proba(X)[0]
        probs = {REGIME_CLASSES[i]: float(probs_arr[i]) for i in range(len(REGIME_CLASSES))}
        top_regime = REGIME_CLASSES[int(np.argmax(probs_arr))]

        return {
            "regime": top_regime,
            "probabilities": probs,
            "is_fallback": False,
            "model_version": self.meta.get("model_version", "regime_v1"),
        }


regime_model = RegimeModel()
