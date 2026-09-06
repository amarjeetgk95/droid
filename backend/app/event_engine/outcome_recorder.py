from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Any
from pydantic import BaseModel, Field
import structlog

from app.event_engine.models import CanonicalEvent, ExpectedDirection

logger = structlog.get_logger()


class MonitoringSnapshot(BaseModel):
    interval_label: str  # T-15M, T-5M, T+1M, T+5M, T+15M, T+30M, T+60M, EOD
    timestamp: datetime
    price: float
    iv: Optional[float] = None
    oi: Optional[int] = None
    move_from_baseline_pct: float = 0.0


class EventOutcome(BaseModel):
    outcome_id: str = Field(default_factory=lambda: f"OUT-{uuid.uuid4().hex[:8].upper()}")
    canonical_event_id: str
    measured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    predicted_direction: ExpectedDirection = "UNKNOWN"
    actual_direction: ExpectedDirection = "UNKNOWN"
    prediction_correct: bool = False
    initial_move_pct: float = 0.0
    maximum_move_pct: float = 0.0
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    time_to_peak_min: int = 0
    time_to_reversal_min: Optional[int] = None
    realized_volatility_change: Optional[float] = None
    iv_change_pct: Optional[float] = None
    oi_change_pct: Optional[float] = None
    primary_instrument: str = "BANKNIFTY"
    monitoring_snapshots: list[MonitoringSnapshot] = Field(default_factory=list)
    is_settled: bool = False


class EventOutcomeRecorder:
    """Post-Event Market-Reaction & Quantitative Outcome Engine (§24).
    
    Guarantees:
      1. PREDICTION and OUTCOME remain completely separate immutable entities.
      2. Quantifies MFE, MAE, realized moves, IV crush, and directional accuracy.
    """

    def __init__(self):
        self._outcomes: dict[str, EventOutcome] = {}

    def calculate_reaction(
        self,
        event: CanonicalEvent,
        primary_instrument: str,
        baseline_price: float,
        price_progression: list[tuple[str, datetime, float]],  # list of (interval_label, dt, price)
        pre_iv: Optional[float] = None,
        post_iv: Optional[float] = None,
        pre_oi: Optional[int] = None,
        post_oi: Optional[int] = None,
    ) -> EventOutcome:
        """Compute realized price excursion and post-event reaction (§24)."""
        if baseline_price <= 0:
            baseline_price = 1.0

        snapshots: list[MonitoringSnapshot] = []
        max_favorable = 0.0
        max_adverse = 0.0
        initial_move = 0.0
        max_absolute_move = 0.0
        peak_minute = 0

        predicted_dir = event.expected_direction

        for idx, (label, dt, px) in enumerate(price_progression):
            move_pct = round(((px - baseline_price) / baseline_price) * 100.0, 3)
            snapshots.append(
                MonitoringSnapshot(
                    interval_label=label,
                    timestamp=dt,
                    price=px,
                    iv=post_iv if idx > 0 else pre_iv,
                    oi=post_oi if idx > 0 else pre_oi,
                    move_from_baseline_pct=move_pct,
                )
            )

            if idx == 0:
                initial_move = move_pct

            if abs(move_pct) > abs(max_absolute_move):
                max_absolute_move = move_pct
                # Approximate minute from index if 5m candles
                peak_minute = idx * 5

            # Favorable / Adverse Excursion relative to predicted direction
            if predicted_dir == "BULLISH":
                if move_pct > max_favorable:
                    max_favorable = move_pct
                if move_pct < max_adverse:
                    max_adverse = move_pct
            elif predicted_dir == "BEARISH":
                if -move_pct > max_favorable:
                    max_favorable = -move_pct
                if -move_pct < max_adverse:
                    max_adverse = -move_pct
            else:
                max_favorable = max(max_favorable, abs(move_pct))

        # Determine actual direction based on final/peak move
        if max_absolute_move >= 0.25:
            actual_dir: ExpectedDirection = "BULLISH"
        elif max_absolute_move <= -0.25:
            actual_dir = "BEARISH"
        else:
            actual_dir = "NEUTRAL"

        prediction_correct = False
        if predicted_dir != "UNKNOWN":
            prediction_correct = (predicted_dir == actual_dir)

        # IV and OI changes
        iv_change: Optional[float] = None
        if pre_iv and post_iv and pre_iv > 0:
            iv_change = round(((post_iv - pre_iv) / pre_iv) * 100.0, 2)

        oi_change: Optional[float] = None
        if pre_oi and post_oi and pre_oi > 0:
            oi_change = round(((post_oi - pre_oi) / pre_oi) * 100.0, 2)

        outcome = EventOutcome(
            canonical_event_id=event.canonical_event_id,
            measured_at=datetime.now(timezone.utc),
            predicted_direction=predicted_dir,
            actual_direction=actual_dir,
            prediction_correct=prediction_correct,
            initial_move_pct=initial_move,
            maximum_move_pct=max_absolute_move,
            mfe_pct=round(max_favorable, 3),
            mae_pct=round(abs(max_adverse), 3),
            time_to_peak_min=peak_minute,
            iv_change_pct=iv_change,
            oi_change_pct=oi_change,
            primary_instrument=primary_instrument,
            monitoring_snapshots=snapshots,
            is_settled=True,
        )

        self._outcomes[event.canonical_event_id] = outcome
        logger.info(
            "event_outcome_recorded",
            event_id=event.canonical_event_id,
            actual_direction=actual_dir,
            max_move_pct=max_absolute_move,
            correct=prediction_correct,
        )
        return outcome

    def get_outcome(self, canonical_event_id: str) -> Optional[EventOutcome]:
        return self._outcomes.get(canonical_event_id)

    def get_all_outcomes(self) -> list[EventOutcome]:
        return list(self._outcomes.values())


event_outcome_recorder = EventOutcomeRecorder()
