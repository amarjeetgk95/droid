"""Outcome measurement engine for the Research Laboratory (§26, N5).

Computes forward ground truth (MFE, MAE, realized return, target/stop touches)
from forward market candles once the prediction horizon has elapsed.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
import structlog

from app.research.enums import Direction
from app.research.models import PredictionOutcome, ResearchPrediction

logger = structlog.get_logger(__name__)


class OutcomeMeasurer:
    """Computes exact forward outcomes for predictions."""

    @classmethod
    def evaluate_forward_candles(
        cls,
        prediction: ResearchPrediction,
        forward_candles: List[Dict[str, Any]],
    ) -> PredictionOutcome:
        """Measure realization against the forward sequence of candles."""
        if not forward_candles:
            raise ValueError("forward_candles cannot be empty to evaluate outcome")

        entry_price = float(prediction.current_price)
        exit_price = float(forward_candles[-1]["close"])
        actual_move = round(exit_price - entry_price, 2)
        actual_pct = round((actual_move / entry_price) * 100.0, 3) if entry_price > 0 else 0.0

        if actual_move > 0:
            actual_dir = Direction.BULLISH
        elif actual_move < 0:
            actual_dir = Direction.BEARISH
        else:
            actual_dir = Direction.NEUTRAL

        target_hit = False
        stop_hit = False
        time_to_target_sec: Optional[float] = None

        pred_dir = prediction.direction
        target_p = prediction.target_price
        inval_p = prediction.invalidation_price

        # Calculate MFE (Maximum Favorable Excursion) and MAE (Maximum Adverse Excursion)
        if pred_dir == Direction.BULLISH:
            mfe = max(0.0, max(float(c["high"]) - entry_price for c in forward_candles))
            mae = max(0.0, max(entry_price - float(c["low"]) for c in forward_candles))
        elif pred_dir == Direction.BEARISH:
            mfe = max(0.0, max(entry_price - float(c["low"]) for c in forward_candles))
            mae = max(0.0, max(float(c["high"]) - entry_price for c in forward_candles))
        else:
            mfe = 0.0
            mae = max(0.0, max(abs(float(c["high"]) - entry_price) for c in forward_candles))

        # Check chronological touches for target vs invalidation
        entry_ts = prediction.timestamp
        for idx, candle in enumerate(forward_candles):
            high_c = float(candle["high"])
            low_c = float(candle["low"])

            if target_p is not None and not target_hit and not stop_hit:
                if pred_dir == Direction.BULLISH and high_c >= target_p:
                    target_hit = True
                    time_to_target_sec = (idx + 1) * 60.0  # Approx or candle resolution
                elif pred_dir == Direction.BEARISH and low_c <= target_p:
                    target_hit = True
                    time_to_target_sec = (idx + 1) * 60.0

            if inval_p is not None and not stop_hit:
                if pred_dir == Direction.BULLISH and low_c <= inval_p:
                    stop_hit = True
                elif pred_dir == Direction.BEARISH and high_c >= inval_p:
                    stop_hit = True

        # Correctness determination
        if pred_dir == Direction.NEUTRAL:
            is_correct = abs(actual_pct) < 0.10
        else:
            is_correct = (pred_dir == actual_dir) and (not stop_hit or target_hit)

        outcome_id = f"out_{uuid.uuid4().hex[:12]}"
        return PredictionOutcome(
            outcome_id=outcome_id,
            prediction_id=prediction.prediction_id,
            actual_direction=actual_dir,
            actual_price_move=actual_move,
            actual_pct_move=actual_pct,
            entry_price=round(entry_price, 2),
            exit_price=round(exit_price, 2),
            mfe=round(mfe, 2),
            mae=round(mae, 2),
            target_hit=target_hit,
            stop_hit=stop_hit,
            time_to_target_sec=time_to_target_sec,
            is_correct=is_correct,
            evaluated_at=datetime.now(timezone.utc),
        )
