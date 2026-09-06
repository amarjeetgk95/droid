"""Cheap Validation Gate for offline indicator backtesting (§19, §20).

Iterates through historical candles with strict Point-in-Time (PIT) integrity,
generates indicator predictions, measures forward outcomes, and evaluates statistical edge.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.research.enums import ExperimentStatus, ForecastHorizon, MarketRegime, MarketSession
from app.research.features import classify_session_ist
from app.research.indicator_base import IndicatorBase
from app.research.models import (
    ExperimentDefinition,
    ExperimentRun,
    IndicatorContext,
    PredictionOutcome,
    ResearchPrediction,
    ValidationReport,
)
from app.research.outcome_measurer import OutcomeMeasurer
from app.research.predictions import PredictionService
from app.research.registry import IndicatorRegistry
from app.research.validation.baseline import NaiveMomentumBaseline
from app.research.validation.statistical_evaluator import StatisticalEvaluator

logger = structlog.get_logger(__name__)


class CheapValidationGate:
    """Offline validation engine for rapid, zero-risk indicator evaluation."""

    @classmethod
    async def run_experiment(
        cls,
        indicator: IndicatorBase,
        candles: List[Dict[str, Any]],
        instrument: str = "NIFTY 50",
        timeframe: str = "5m",
        horizon_candles: int = 5,
        forecast_horizon: ForecastHorizon = ForecastHorizon.HORIZON_15M,
        warmup_period: int = 30,
        stride: int = 5,
        options_ctx: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None,
    ) -> Tuple[ExperimentRun, ValidationReport]:
        """Execute a backtest run over historical candles.
        
        Enforces Point-in-Time (PIT) integrity:
        At decision index t, the indicator can ONLY observe candles[0 : t+1].
        Forward candles[t+1 : t+1+horizon_candles] are strictly quarantined
        until the decision has been logged.
        """
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        exp_id = f"exp_{indicator.indicator_id}_{int(datetime.now(timezone.utc).timestamp())}"
        started_at = datetime.now(timezone.utc)

        total_candles = len(candles)
        if total_candles < (warmup_period + horizon_candles):
            err_msg = f"Insufficient candles: {total_candles} provided, need at least {warmup_period + horizon_candles}"
            return (
                ExperimentRun(
                    run_id=run_id,
                    experiment_id=exp_id,
                    status=ExperimentStatus.FAILED,
                    sample_count=0,
                    error_message=err_msg,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc),
                ),
                StatisticalEvaluator.evaluate([], []),
            )

        predictions: List[ResearchPrediction] = []
        outcomes: List[PredictionOutcome] = []
        regimes: Dict[str, str] = {}
        sessions: Dict[str, str] = {}

        # Run baseline along with indicator to obtain real-world baseline accuracy
        baseline_model = NaiveMomentumBaseline()
        baseline_correct = 0

        logger.info(
            "starting_cheap_validation_gate",
            indicator=indicator.indicator_id,
            candles_count=total_candles,
            stride=stride,
        )

        for t in range(warmup_period, total_candles - horizon_candles, stride):
            past_candles = candles[: t + 1]
            forward_candles = candles[t + 1 : t + 1 + horizon_candles]

            decision_candle = past_candles[-1]
            raw_ts = decision_candle.get("timestamp")
            if isinstance(raw_ts, str):
                try:
                    dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                except Exception:
                    dt = datetime.now(timezone.utc)
            elif isinstance(raw_ts, datetime):
                dt = raw_ts
            else:
                dt = datetime.now(timezone.utc)

            curr_price = float(decision_candle["close"])
            sess = classify_session_ist(dt)

            ctx = IndicatorContext(
                instrument=instrument,
                timeframe=timeframe,
                timestamp=dt,
                candles=past_candles,
                current_price=curr_price,
                options_context=options_ctx,
                market_regime=MarketRegime.RANGING,  # default or dynamic
                session=sess,
            )

            # 1. Indicator computes prediction strictly from past data
            try:
                output = await indicator.calculate(ctx)
            except Exception as e:
                logger.warning("indicator_calc_failed_at_step", t=t, error=str(e))
                continue

            pred_id = f"pred_{uuid.uuid4().hex[:12]}"
            prediction = ResearchPrediction(
                prediction_id=pred_id,
                indicator_id=indicator.indicator_id,
                indicator_version=indicator.version,
                instrument=instrument,
                timeframe=timeframe,
                timestamp=dt,
                current_price=curr_price,
                direction=output.direction,
                score=output.score,
                confidence=output.confidence,
                raw_value=output.raw_value,
                normalized_value=output.normalized_value,
                component_values=output.component_values,
                forecast_horizon=forecast_horizon,
                horizon_candles=horizon_candles,
                target_price=output.target_price,
                invalidation_price=output.invalidation_price,
                created_at=dt,
            )
            predictions.append(prediction)
            regimes[pred_id] = output.regime_context or "UNKNOWN"
            sessions[pred_id] = sess.value

            # 2. Measure actual outcome from strictly quarantined forward data
            outcome = OutcomeMeasurer.evaluate_forward_candles(prediction, forward_candles)
            outcomes.append(outcome)

            # Baseline check
            base_dir = baseline_model.predict(past_candles)
            if base_dir == outcome.actual_direction:
                baseline_correct += 1

        empirical_baseline_acc = (baseline_correct / len(predictions)) if predictions else 0.50

        # 3. Statistical evaluation
        report = StatisticalEvaluator.evaluate(
            predictions=predictions,
            outcomes=outcomes,
            baseline_accuracy=empirical_baseline_acc,
            regimes=regimes,
            sessions=sessions,
        )

        completed_at = datetime.now(timezone.utc)
        run_record = ExperimentRun(
            run_id=run_id,
            experiment_id=exp_id,
            status=ExperimentStatus.COMPLETED,
            sample_count=len(predictions),
            metrics=report.model_dump(),
            started_at=started_at,
            completed_at=completed_at,
            created_at=completed_at,
        )

        logger.info(
            "validation_experiment_completed",
            samples=len(predictions),
            accuracy=report.accuracy,
            baseline=report.baseline_accuracy,
            p_value=report.p_value,
            significant=report.is_statistically_significant,
        )

        return run_record, report
