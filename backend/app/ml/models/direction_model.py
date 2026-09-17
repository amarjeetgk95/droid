"""Multi-Horizon Direction Model for DROID ML Engine.

Implements Section 11 of the DROID ML Specification.
Predicts directional class probabilities:
    P(down), P(neutral), P(up)
across horizons H=5m, 15m, 30m, 60m using regularized GBDTs & Logistic ensembles.
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

DIRECTIONS = ["BEARISH", "NEUTRAL", "BULLISH"]


class DirectionModel:
    def __init__(self, horizon_minutes: int = 15):
        self.horizon_minutes = horizon_minutes
        self.lgb_model = None
        self.xgb_model = None
        self.logistic_model = None
        self.meta: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        prefix = f"direction_h{self.horizon_minutes}"
        # Prefer challenger over champion in testing
        base_dir = CHALLENGER_DIR if (CHALLENGER_DIR / f"{prefix}_lgb.joblib").exists() else CHAMPION_DIR

        lgb_p = base_dir / f"{prefix}_lgb.joblib"
        meta_p = base_dir / f"{prefix}_meta.json"

        if lgb_p.exists() and meta_p.exists():
            try:
                self.lgb_model = joblib.load(lgb_p)
                self.meta = json.loads(meta_p.read_text())
            except Exception:
                self.lgb_model = None

    def predict_direction(self, feature_vector: List[float]) -> Dict[str, Any]:
        """
        Predicts directional probabilities for the configured horizon.
        """
        if self.lgb_model is None:
            # Deterministic indicator-based fallback
            ret_5m = feature_vector[2] if len(feature_vector) > 2 else 0.0
            st_dir = feature_vector[12] if len(feature_vector) > 12 else 0.0

            if st_dir > 0 and ret_5m > 0:
                probs = [0.15, 0.25, 0.60]
            elif st_dir < 0 and ret_5m < 0:
                probs = [0.60, 0.25, 0.15]
            else:
                probs = [0.25, 0.50, 0.25]

            bias = DIRECTIONS[int(np.argmax(probs))]
            return {
                "horizon_minutes": self.horizon_minutes,
                "p_down": round(probs[0], 3),
                "p_neutral": round(probs[1], 3),
                "p_up": round(probs[2], 3),
                "predicted_bias": bias,
                "confidence": round(float(np.max(probs)), 3),
                "is_fallback": True,
                "model_version": "heuristic_direction_baseline",
            }

        X = np.array(feature_vector).reshape(1, -1)
        probs_arr = self.lgb_model.predict_proba(X)[0]
        p_down = float(probs_arr[0])
        p_neutral = float(probs_arr[1])
        p_up = float(probs_arr[2])

        bias = DIRECTIONS[int(np.argmax(probs_arr))]
        return {
            "horizon_minutes": self.horizon_minutes,
            "p_down": round(p_down, 4),
            "p_neutral": round(p_neutral, 4),
            "p_up": round(p_up, 4),
            "predicted_bias": bias,
            "confidence": round(float(max(p_down, p_neutral, p_up)), 4),
            "is_fallback": False,
            "model_version": self.meta.get("model_version", f"direction_h{self.horizon_minutes}_v1"),
        }


direction_model_h15 = DirectionModel(horizon_minutes=15)
direction_model_h5 = DirectionModel(horizon_minutes=5)
direction_model_h60 = DirectionModel(horizon_minutes=60)
