"""Prediction Engine interface (spec §13, §14, §31).

Stable interface over DROID's existing prediction subsystem:
  Feature Store → Regime Classifier → ML ensemble (XGBoost/LightGBM)
  → deterministic evidence/scenario engine.

Honesty contract:
  * ML probabilities are published ONLY when the trained, calibrated ensemble
    for that exact horizon produced them (`model_source ==
    "xgboost_lightgbm_ensemble"` and `calibrated is True`).
  * Otherwise probabilities are `None` / `UNAVAILABLE` and `model_source` says
    exactly which deterministic evidence produced the direction.
  * Calibration metrics are surfaced only when they exist in the model
    artifact — never asserted from a hardcoded number.
"""
from __future__ import annotations

import structlog

from app.copilot.enums import CALIBRATION_VERSION, HORIZON_MINUTES, PREDICTION_ENGINE_VERSION
from app.copilot.models import (
    ConfidenceBlock,
    ConfluenceResult,
    Factor,
    LevelsBlock,
    MarketContext,
    PredictionResult,
    Scenario,
)
from app.copilot.scenarios import build_scenarios, expected_range

logger = structlog.get_logger()

DETERMINISTIC_SOURCE = "deterministic_evidence_scenario_engine"
ML_SOURCE = "xgboost_lightgbm_ensemble"


def regime_stability(ctx: MarketContext) -> float | None:
    """Deterministic 0-1 stability score for the classified regime.

    Built from the regime classifier's own confidence plus trend/volatility
    coherence — a documented heuristic, never a probability claim.
    """
    if ctx.regime.name == "UNKNOWN":
        return None
    base = (
        ctx.regime.classification_confidence / 100.0
        if ctx.regime.classification_confidence is not None
        else 0.55
    )
    adx = ctx.regime.adx
    if adx is not None:
        if adx >= 25:
            base += 0.12
        elif adx < 18:
            base -= 0.08
    if ctx.regime.name == "COMPRESSION_SQUEEZE":
        # A squeeze is inherently unstable — a breakout regime may replace it.
        base -= 0.15
    return round(max(0.0, min(1.0, base)), 4)


class PredictionEngine:
    """Wraps the existing ML predictor behind a stable copilot interface."""

    def __init__(self, predictor: object | None = None) -> None:
        self._predictor = predictor

    async def _ml_probabilities(self, ctx: MarketContext) -> dict | None:
        """Return calibrated ensemble probabilities for this horizon, or None."""
        minutes = HORIZON_MINUTES.get(ctx.horizon)
        if minutes is None:
            return None
        try:
            from app.ml.predictor import MLPredictor
            from app.ml.trainer import load_ensemble

            predictor = self._predictor or MLPredictor()
            prediction = await predictor.predict_probabilities(ctx.symbol, horizon_minutes=minutes)  # type: ignore[attr-defined]
        except Exception as exc:  # ML is optional evidence, never fatal
            logger.info("copilot_ml_unavailable", symbol=ctx.symbol, horizon=ctx.horizon, error=str(exc)[:200])
            return None

        source = getattr(prediction, "model_source", None)
        calibrated = bool(getattr(prediction, "calibrated", False))
        if source != ML_SOURCE or not calibrated:
            # The heuristic ensemble is explicitly NOT a prediction.
            return {
                "accepted": False,
                "reason": f"model_source={source} calibrated={calibrated}",
                "model_version": getattr(prediction, "model_version", None),
            }

        meta: dict = {}
        try:
            _, _, meta = load_ensemble(horizon_minutes=minutes)
        except Exception:
            meta = {}
        return {
            "accepted": True,
            "model_version": getattr(prediction, "model_version", ML_SOURCE),
            "probabilities": {
                "BULL": round(float(getattr(prediction, "bullish_pct", 0.0)) / 100.0, 4),
                "NEUTRAL": round(float(getattr(prediction, "neutral_pct", 0.0)) / 100.0, 4),
                "BEAR": round(float(getattr(prediction, "bearish_pct", 0.0)) / 100.0, 4),
            },
            "horizon_minutes": minutes,
            "meta": meta or {},
        }

    async def predict(
        self,
        ctx: MarketContext,
        levels: LevelsBlock,
        confluence: ConfluenceResult,
        factors: dict[str, Factor] | None = None,
    ) -> tuple[PredictionResult, list[Scenario], list[str]]:
        warnings: list[str] = []
        ml = await self._ml_probabilities(ctx)

        model_probs = None
        probability_source = None
        model_status = "UNAVAILABLE"
        model_version = f"{PREDICTION_ENGINE_VERSION}+evidence"
        model_source = DETERMINISTIC_SOURCE
        calibration: dict = {"available": False, "version": CALIBRATION_VERSION, "metrics": {}}

        if ml and ml.get("accepted"):
            model_probs = ml["probabilities"]
            probability_source = (
                f"ML ensemble ({ml.get('model_version')}, horizon {ml.get('horizon_minutes')}m)"
            )
            model_status = "MEASURED"
            model_version = str(ml.get("model_version") or f"{PREDICTION_ENGINE_VERSION}+ml")
            model_source = ML_SOURCE
            meta = ml.get("meta") or {}
            metrics = {
                key: meta[key]
                for key in ("brier_score", "ece", "calibration_error", "directional_accuracy", "sample_size")
                if isinstance(meta.get(key), (int, float))
            }
            calibration = {
                "available": bool(metrics),
                "version": CALIBRATION_VERSION,
                "metrics": metrics,
                "window": meta.get("evaluation_window"),
                "sample_size": meta.get("sample_size"),
                "model_version": model_version,
            }
        elif ml and ml.get("reason"):
            warnings.append(
                "Trained calibrated ML model is not available for this horizon "
                f"({ml['reason']}); the direction comes from deterministic evidence only and no "
                "probabilities are published."
            )
        else:
            warnings.append(
                "No trained quantitative model covers this horizon; the direction comes from deterministic "
                "evidence and scenario probabilities are unavailable."
            )

        scenarios = build_scenarios(ctx, levels, model_probs, probability_source)
        if model_probs is None:
            warnings.append("Scenario probabilities unavailable — no calibrated model is wired for this horizon.")

        confidence = ConfidenceBlock(
            model=max(model_probs.values()) if model_probs else None,
            model_status=model_status,
            data_quality=ctx.data_quality.overall,
            confluence=confluence.confluence,
            regime_stability=regime_stability(ctx),
        )

        probabilities = dict(model_probs) if model_probs else {"BULL": None, "NEUTRAL": None, "BEAR": None}
        prediction = PredictionResult(
            symbol=ctx.symbol,
            horizon=ctx.horizon,
            direction=confluence.dominant_state,
            expected_return=None,
            expected_range=expected_range(ctx),
            scenarios=scenarios,
            confidence=confidence,
            model_version=model_version,
            model_source=model_source,
            probabilities=probabilities,
            calibration=calibration,
        )
        return prediction, scenarios, warnings


prediction_engine = PredictionEngine()
