"""
Machine Learning Candidate Validator & Safety Guard (§25).

Enforces strict ML role restrictions:
- ML is NEVER a generator.
- Evaluates candidate trades emitted by deterministic FSM.
- Computes calibrated probability of Target 1 hit.
- Vetoes candidates with sub-threshold probability (< 0.50).
- Graceful fail-safe fallback: If model fails or file is missing,
  passes candidate without boost to prevent production downtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any
import joblib
import numpy as np
import structlog

from app.signals.strategies.vortex_snap.types import (
    Candle,
    EventType,
    StructuralLevel,
    VortexFeatureSnapshot,
)
from app.signals.strategies.vortex_snap.session import MarketSessionInfo
from app.signals.strategies.vortex_snap.ml.features import (
    extract_features,
    MLFeatureVector,
    FEATURE_NAMES,
)
from app.signals.strategies.vortex_snap.ml.calibrator import ProbabilityCalibrator

logger = structlog.get_logger(__name__)


@dataclass
class ValidationDecision:
    """Outcome of ML validation."""
    is_accepted: bool
    calibrated_probability: float
    confidence_boost: float
    veto_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_accepted": self.is_accepted,
            "calibrated_probability": round(self.calibrated_probability, 4),
            "confidence_boost": round(self.confidence_boost, 4),
            "veto_reason": self.veto_reason,
        }


class VortexMLValidator:
    """Independent ML validator acting strictly as a gate/filter."""

    def __init__(
        self,
        artifact_path: Optional[Path | str] = "artifacts/vortex_snap_ml_validator.joblib",
        acceptance_threshold: float = 0.50,
        enabled: bool = True,
    ):
        self.artifact_path = Path(artifact_path) if artifact_path else None
        self.acceptance_threshold = acceptance_threshold
        self.enabled = enabled
        self._model = None
        self._calibrator: Optional[ProbabilityCalibrator] = None
        self._is_loaded = False

        if self.enabled and self.artifact_path and self.artifact_path.exists():
            self._load_artifact()

    def _load_artifact(self) -> bool:
        """Loads model bundle from disk."""
        try:
            bundle = joblib.load(self.artifact_path)
            self._model = bundle["model"]
            self._calibrator = bundle["calibrator"]
            self._is_loaded = True
            logger.info("vortex_ml_validator_loaded", path=str(self.artifact_path))
            return True
        except Exception as e:
            logger.warning("vortex_ml_validator_load_failed", error=str(e), fallback="fail_open")
            self._is_loaded = False
            return False

    def validate(
        self,
        snapshot: VortexFeatureSnapshot,
        current_candle: Candle,
        session_info: MarketSessionInfo,
        interacted_level: Optional[StructuralLevel] = None,
        event_type: EventType = EventType.CONTINUATION,
        direction: int = 1,
    ) -> ValidationDecision:
        """Validates a candidate signal emitted by the deterministic engine.
        
        Returns:
            ValidationDecision with acceptance verdict and calibrated probability.
        """
        # Fail-safe: if validator disabled or model not loaded, accept without boost
        if not self.enabled or not self._is_loaded or self._model is None:
            return ValidationDecision(
                is_accepted=True,
                calibrated_probability=0.50,
                confidence_boost=0.0,
                veto_reason=None,
            )

        try:
            feat_vec = extract_features(
                snapshot=snapshot,
                current_candle=current_candle,
                session_info=session_info,
                interacted_level=interacted_level,
                event_type=event_type,
                direction=direction,
            )
            X = feat_vec.to_array().reshape(1, -1)

            # Raw prediction
            raw_p = self._model.predict_proba(X)[:, 1]

            # Calibrate
            if self._calibrator is not None:
                cal_p = float(self._calibrator.calibrate(raw_p)[0])
            else:
                cal_p = float(raw_p[0])

            # Veto gate
            if cal_p < self.acceptance_threshold:
                return ValidationDecision(
                    is_accepted=False,
                    calibrated_probability=cal_p,
                    confidence_boost=0.0,
                    veto_reason=f"ML probability ({cal_p:.2f}) below threshold ({self.acceptance_threshold:.2f})",
                )

            # Accept with confidence boost
            boost = (cal_p - 0.50) * 0.15  # Up to +7.5% boost for high probability
            return ValidationDecision(
                is_accepted=True,
                calibrated_probability=cal_p,
                confidence_boost=round(boost, 4),
                veto_reason=None,
            )

        except Exception as e:
            logger.warning("vortex_ml_validation_exception", error=str(e), fallback="fail_open")
            # Fail-open safety guard (§25)
            return ValidationDecision(
                is_accepted=True,
                calibrated_probability=0.50,
                confidence_boost=0.0,
                veto_reason=None,
            )
