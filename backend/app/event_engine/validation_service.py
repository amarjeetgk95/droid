from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Any, Literal
from pydantic import BaseModel, Field
import structlog

from app.event_engine.outcome_recorder import EventOutcome, event_outcome_recorder
from app.event_engine.signal_bridge import ShadowSignalRecord, event_signal_bridge

logger = structlog.get_logger()


class EventTrackRecord(BaseModel):
    total_events_evaluated: int
    settled_events_count: int
    shadow_trades_count: int
    directional_accuracy_pct: float
    shadow_win_rate_pct: float
    profit_factor: float
    average_expectancy_r: float
    average_mfe_pct: float
    average_mae_pct: float
    average_realized_iv_crush_pct: float
    sample_size_gate_passed: bool
    minimum_sample_required: int = 30
    recommendation: Literal["ACCUMULATE_MORE_EVENTS", "CALIBRATION_STABLE", "READY_FOR_PAPER_PILOT"]
    breakdown_by_event_type: dict[str, Any] = Field(default_factory=dict)
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventValidationService:
    """Statistical Edge Validation & Performance Benchmarking Engine (§23, §24).
    
    Validates whether the Event Intelligence Engine generates measurable statistical edge:
      1. Tracks directional accuracy between immutable prediction snapshots and actual moves.
      2. Measures realized MFE (Maximum Favorable Excursion) vs MAE (Adverse Excursion).
      3. Aggregates shadow signal simulation win-rate and profit factors.
      4. Strictly enforces N >= 30 minimum sample threshold before paper pilot authorization.
    """

    def __init__(self, min_sample_threshold: int = 30):
        self.min_sample_threshold = min_sample_threshold

    def compute_track_record(
        self,
        outcomes: Optional[list[EventOutcome]] = None,
        shadow_records: Optional[list[ShadowSignalRecord]] = None,
    ) -> EventTrackRecord:
        """Compute aggregate performance statistics across all historical event cycles."""
        all_outcomes = outcomes if outcomes is not None else event_outcome_recorder.get_all_outcomes()
        all_shadows = shadow_records if shadow_records is not None else event_signal_bridge.get_shadow_records()

        total_evaluated = len(all_outcomes)
        settled_outcomes = [o for o in all_outcomes if o.is_settled]
        settled_count = len(settled_outcomes)

        # 1. Directional Accuracy
        correct_predictions = sum(1 for o in settled_outcomes if o.prediction_correct)
        directional_acc = round((correct_predictions / settled_count) * 100.0, 1) if settled_count > 0 else 0.0

        # 2. MFE / MAE Averages
        avg_mfe = round(sum(o.mfe_pct for o in settled_outcomes) / settled_count, 2) if settled_count > 0 else 0.0
        avg_mae = round(sum(o.mae_pct for o in settled_outcomes) / settled_count, 2) if settled_count > 0 else 0.0

        # 3. IV Crush Realized
        crush_values = [o.iv_change_pct for o in settled_outcomes if o.iv_change_pct is not None]
        avg_iv_crush = round(sum(crush_values) / len(crush_values), 1) if crush_values else 0.0

        # 4. Shadow Trades Performance
        shadow_count = len(all_shadows)
        wins = 0
        losses = 0
        gross_profit = 0.0
        gross_loss = 0.0

        for sig in all_shadows:
            pnl = sig.simulated_pnl_pct
            if pnl is not None:
                if pnl > 0:
                    wins += 1
                    gross_profit += pnl
                elif pnl < 0:
                    losses += 1
                    gross_loss += abs(pnl)

        closed_shadows = wins + losses
        win_rate = round((wins / closed_shadows) * 100.0, 1) if closed_shadows > 0 else 0.0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (2.5 if gross_profit > 0 else 1.0)
        expectancy_r = round((gross_profit - gross_loss) / closed_shadows, 2) if closed_shadows > 0 else 0.0

        # 5. Statistical Sample Gate (§23)
        sample_gate_passed = settled_count >= self.min_sample_threshold
        if not sample_gate_passed:
            recommendation = "ACCUMULATE_MORE_EVENTS"
        elif win_rate >= 55.0 and profit_factor >= 1.4:
            recommendation = "READY_FOR_PAPER_PILOT"
        else:
            recommendation = "CALIBRATION_STABLE"

        return EventTrackRecord(
            total_events_evaluated=total_evaluated,
            settled_events_count=settled_count,
            shadow_trades_count=shadow_count,
            directional_accuracy_pct=directional_acc,
            shadow_win_rate_pct=win_rate,
            profit_factor=profit_factor,
            average_expectancy_r=expectancy_r,
            average_mfe_pct=avg_mfe,
            average_mae_pct=avg_mae,
            average_realized_iv_crush_pct=avg_iv_crush,
            sample_size_gate_passed=sample_gate_passed,
            minimum_sample_required=self.min_sample_threshold,
            recommendation=recommendation,
            breakdown_by_event_type={
                "CENTRAL_BANK": {"count": sum(1 for o in settled_outcomes if "RBI" in o.canonical_event_id)},
                "CORPORATE": {"count": sum(1 for o in settled_outcomes if "CORP" in o.canonical_event_id or "NSE" in o.canonical_event_id)},
                "REGULATORY": {"count": sum(1 for o in settled_outcomes if "SEBI" in o.canonical_event_id)},
            },
        )


event_validation_service = EventValidationService()
