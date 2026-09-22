"""Breakout Validation & Continuation Model for DROID ML Engine.

Implements Section 12 of the DROID ML Specification.
Answers:
    "Is this apparent breakout likely to continue rather than fail?"
Outputs calibrated probabilities:
    P(valid_breakout) vs P(false_breakout / trap)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np

ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts"
CHALLENGER_DIR = ARTIFACTS_DIR / "challenger"
CHAMPION_DIR = ARTIFACTS_DIR / "champion"


class BreakoutModel:
    def __init__(self, model_path: Optional[Path] = None, meta_path: Optional[Path] = None):
        self.model = None
        self.meta: Dict[str, Any] = {}
        self._load(model_path, meta_path)

    def _load(self, model_path: Optional[Path], meta_path: Optional[Path]) -> None:
        target_model = model_path or (CHALLENGER_DIR / "breakout_model.joblib")
        target_meta = meta_path or (CHALLENGER_DIR / "breakout_meta.json")

        if not target_model.exists() and (CHAMPION_DIR / "breakout_model.joblib").exists():
            target_model = CHAMPION_DIR / "breakout_model.joblib"
            target_meta = CHAMPION_DIR / "breakout_meta.json"

        if target_model.exists() and target_meta.exists():
            try:
                self.model = joblib.load(target_model)
                self.meta = json.loads(target_meta.read_text())
            except Exception:
                self.model = None

    def predict_breakout_quality(
        self,
        feature_vector: List[float],
        direction: str = "LONG_CALL",
        strategy_name: str = "BREAKOUT",
    ) -> Dict[str, Any]:
        """
        Predicts whether a breakout candidate is genuine or an exhaustion trap.

        Fail-closed honesty: unfitted returns status="fallback" with NULL
        probs (never 0.50-based heuristic). Callers MUST check
        `status`/`is_fallback`.
        """
        if self.model is None:
            # No trained model: fail-closed, never fabricate from 0.50.
            return {
                "p_valid_breakout": None,
                "p_false_breakout": None,
                "is_continuation": None,
                "is_fallback": True,
                "status": "fallback",
                "reason": "breakout-model-unfitted-no-artifact",
                "model_version": "heuristic_breakout_baseline",
            }

        X = np.array(feature_vector).reshape(1, -1)
        probs = self.model.predict_proba(X)[0]
        # Class 1 = Valid Breakout, Class 0 = False Breakout
        p_valid = float(probs[1]) if len(probs) > 1 else float(probs[0])
        p_false = 1.0 - p_valid

        return {
            "p_valid_breakout": round(p_valid, 4),
            "p_false_breakout": round(p_false, 4),
            "is_continuation": p_valid >= self.meta.get("decision_threshold", 0.55),
            "is_fallback": False,
            "model_version": self.meta.get("model_version", "breakout_v1"),
        }


breakout_model = BreakoutModel()
