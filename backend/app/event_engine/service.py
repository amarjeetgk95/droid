from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone, date, timedelta
from typing import Optional, Any
from zoneinfo import ZoneInfo
import structlog

from app.event_engine.models import (
    CanonicalEvent,
    EventCreate,
    EventUpdate,
    RawSourceEvent,
    EventScoreSnapshot,
    PredictionSnapshot,
    LifecycleTransition,
    TemporalPhase,
)
from app.event_engine.sources.rbi import RBISourceAdapter, IST
from app.event_engine.sources.nse_bse import NSECorporateSourceAdapter, BSECorporateSourceAdapter
from app.event_engine.sources.sebi import SEBISourceAdapter
from app.event_engine.dedup_service import dedup_service
from app.event_engine.impact_mapper import impact_mapping_service
from app.event_engine.scoring_service import scoring_service
from app.event_engine.lifecycle_service import lifecycle_service
from app.event_engine.historical_matcher import historical_matcher
from app.event_engine.options_context import options_intelligence_service, LiveOptionsContext
from app.event_engine.signal_bridge import event_signal_bridge, ShadowSignalRecord
from app.event_engine.alert_service import event_alert_service, EventAlert
from app.event_engine.outcome_recorder import event_outcome_recorder, EventOutcome
from app.event_engine.risk_overlay import event_risk_overlay_service
from app.event_engine.impact_calibrator import market_impact_calibration_service
from app.event_engine.validation_service import event_validation_service
from app.event_engine.scheduler import event_ingestion_scheduler

logger = structlog.get_logger()


class EventEngineService:
    """Core Orchestrator for Event Intelligence & Opportunity Engine v3 (§0, §2, §43).
    
    Coordinates:
      1. Source Ingest (RBI, NSE, BSE, SEBI)
      2. Source Validation & Normalization
      3. Deduplication & Canonical Identity
      4. Impact Mapping
      5. Rule-Based Scoring (Importance / Impact / Opportunity independence)
      6. Temporal Phase Updates & Immutable Transitions
      7. Immutable Prediction Snapshots with Anti-Lookahead Cutoffs
      8. Live Options & Real-Time Trading Opportunity Scoring (Phase 2)
      9. Event → Signal Integration in SHADOW_MODE (Phase 2)
      10. Post-Event Outcome Recording (Phase 2)
    """

    def __init__(self):
        self._events: dict[str, CanonicalEvent] = {}
        self._rbi_adapter = RBISourceAdapter()
        self._nse_adapter = NSECorporateSourceAdapter()
        self._bse_adapter = BSECorporateSourceAdapter()
        self._sebi_adapter = SEBISourceAdapter()
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize engine and ingest baseline verified schedules."""
        async with self._lock:
            if self._initialized:
                return
            await self._sync_rbi_schedule_internal()
            await self._sync_corporate_schedule_internal()
            await self._sync_sebi_schedule_internal()
            self._initialized = True
            logger.info("event_engine_service_initialized", tracked_events=len(self._events))

    async def sync_rbi_events(self) -> list[CanonicalEvent]:
        """Trigger sync from official RBI source adapter."""
        async with self._lock:
            return await self._sync_rbi_schedule_internal()

    async def _sync_rbi_schedule_internal(self) -> list[CanonicalEvent]:
        """Internal worker to process RBI events without deadlock."""
        raw_items = await self._rbi_adapter.fetch()
        processed: list[CanonicalEvent] = []

        now = datetime.now(timezone.utc)

        for item in raw_items:
            # 1. Normalize
            raw_event = self._rbi_adapter.normalize(item)

            # 2. Validate
            is_valid, err = self._rbi_adapter.validate(raw_event)
            if not is_valid:
                logger.warning("rbi_event_validation_failed", error=err, payload=item)
                continue

            # 3. Derive canonical identity
            canonical_id = self._rbi_adapter.identify(raw_event)

            # Parse event timestamp in Asia/Kolkata
            event_date_str = item["event_date"]
            time_str = item.get("time_ist", "10:00:00")
            dt_ist_str = f"{event_date_str}T{time_str}+05:30"
            try:
                event_dt = datetime.fromisoformat(dt_ist_str)
            except Exception:
                event_dt = datetime.combine(
                    date.fromisoformat(event_date_str),
                    datetime.min.time(),
                    tzinfo=IST,
                )

            # 4. Deduplicate
            candidate = CanonicalEvent(
                canonical_event_id=canonical_id,
                title=item["title"],
                description=item.get("description"),
                event_type="CENTRAL_BANK",
                sub_type=item.get("sub_type", "MONETARY_POLICY_RATE_DECISION"),
                entity_id="RBI",
                entity_name="Reserve Bank of India",
                sector="BANKING",
                event_timestamp=event_dt,
                timezone="Asia/Kolkata",
                timestamp_precision=item.get("precision", "EXACT"),
                verification_status="VERIFIED",
                certainty=item.get("certainty", "CONFIRMED"),
                expected_direction="UNKNOWN",
                time_horizon="INTRADAY",
                temporal_phase=lifecycle_service.compute_temporal_phase(event_dt, now),
                metadata={"source_name": "RBI_OFFICIAL", "url": item.get("url")},
            )

            # Check existing for match
            matched_existing: Optional[CanonicalEvent] = None
            for existing in self._events.values():
                match_type = dedup_service.classify_match(candidate, existing)
                if match_type in ("EXACT_DUPLICATE", "PROBABLE_DUPLICATE"):
                    matched_existing = existing
                    break

            if matched_existing:
                # Add source to existing record without duplicating the event
                if not any(s.source_name == raw_event.source_name for s in matched_existing.sources):
                    matched_existing.sources.append(raw_event)
                # Update phase
                matched_existing.temporal_phase = lifecycle_service.compute_temporal_phase(
                    matched_existing.event_timestamp, now
                )
                processed.append(matched_existing)
                continue

            # 5. Attach Source
            candidate.sources.append(raw_event)

            # 6. Map Impact
            candidate.impact_mappings = impact_mapping_service.get_mappings_for_event(
                entity_id=candidate.entity_id,
                event_type=candidate.event_type,
                sub_type=candidate.sub_type,
            )

            # 7. Compute Scores (Strict 3-dimension independence)
            candidate.scores = scoring_service.score_event(candidate, market_data_available=False)

            # 8. Compute Historical Comparables with Anti-Lookahead Cutoff
            candidate.comparables = historical_matcher.match_comparables(
                candidate,
                data_cutoff=now,
                top_k=3,
            )

            # 9. Create Immutable Prediction Snapshot
            candidate.latest_prediction = PredictionSnapshot(
                canonical_event_id=candidate.canonical_event_id,
                prediction_timestamp=now,
                data_cutoff_timestamp=now,
                feature_cutoff_timestamp=now,
                formula_version="v3.0.0",
                configuration_version="v3.0.0",
                importance_score=candidate.scores.importance.final_score,
                market_impact_score=candidate.scores.market_impact.final_score,
                opportunity_score=candidate.scores.opportunity.final_score,
                predicted_direction=candidate.expected_direction,
                confidence=0.0,
                strategy_state="NO_SETUP",
                decision=candidate.scores.final_decision,
                snapshot_immutable=True,
            )

            # Update processing flags
            candidate.processing_flags.discovered = True
            candidate.processing_flags.verified = True
            candidate.processing_flags.classified = True
            candidate.processing_flags.impact_mapped = True
            candidate.processing_flags.scored = True

            self._events[candidate.canonical_event_id] = candidate
            processed.append(candidate)

        return processed

    async def create_manual_event(self, event_create: EventCreate) -> CanonicalEvent:
        """Allow manual ops insertion or verification override (§5 fallback)."""
        async with self._lock:
            canonical_id = event_create.canonical_event_id or (
                f"{event_create.entity_id}_{event_create.event_type}_{event_create.event_timestamp.strftime('%Y%m%d')}"
            )

            now = datetime.now(timezone.utc)
            phase = lifecycle_service.compute_temporal_phase(event_create.event_timestamp, now)

            event = CanonicalEvent(
                canonical_event_id=canonical_id,
                title=event_create.title,
                description=event_create.description,
                event_type=event_create.event_type,
                sub_type=event_create.sub_type,
                entity_id=event_create.entity_id,
                entity_name=event_create.entity_name,
                sector=event_create.sector,
                event_timestamp=event_create.event_timestamp,
                timezone=event_create.timezone,
                timestamp_precision=event_create.timestamp_precision,
                verification_status=event_create.verification_status,
                certainty=event_create.certainty,
                expected_direction=event_create.expected_direction,
                time_horizon=event_create.time_horizon,
                temporal_phase=phase,
                metadata={"source_name": event_create.source_name, "notes": event_create.notes},
            )

            raw_source = RawSourceEvent(
                source_name=event_create.source_name,
                source_type="MANUAL",
                source_url=event_create.source_url,
                raw_payload={"notes": event_create.notes},
                is_verified=event_create.verification_status == "VERIFIED",
            )
            event.sources.append(raw_source)

            event.impact_mappings = impact_mapping_service.get_mappings_for_event(
                entity_id=event.entity_id,
                event_type=event.event_type,
                sub_type=event.sub_type,
            )

            event.scores = scoring_service.score_event(event, market_data_available=False)
            event.comparables = historical_matcher.match_comparables(event, data_cutoff=now, top_k=3)

            event.latest_prediction = PredictionSnapshot(
                canonical_event_id=event.canonical_event_id,
                prediction_timestamp=now,
                data_cutoff_timestamp=now,
                feature_cutoff_timestamp=now,
                formula_version="v3.0.0",
                configuration_version="v3.0.0",
                importance_score=event.scores.importance.final_score,
                market_impact_score=event.scores.market_impact.final_score,
                opportunity_score=event.scores.opportunity.final_score,
                predicted_direction=event.expected_direction,
                confidence=0.0,
                strategy_state="NO_SETUP",
                decision=event.scores.final_decision,
            )

            event.processing_flags.discovered = True
            event.processing_flags.verified = event.verification_status == "VERIFIED"
            event.processing_flags.classified = True
            event.processing_flags.impact_mapped = True
            event.processing_flags.scored = True

            self._events[canonical_id] = event
            return event

    async def sync_corporate_events(self) -> list[CanonicalEvent]:
        """Trigger sync from official NSE and BSE corporate source adapters."""
        async with self._lock:
            return await self._sync_corporate_schedule_internal()

    async def _sync_corporate_schedule_internal(self) -> list[CanonicalEvent]:
        """Ingest corporate announcements and earnings."""
        nse_items = await self._nse_adapter.fetch()
        bse_items = await self._bse_adapter.fetch()
        now = datetime.now(timezone.utc)
        processed: list[CanonicalEvent] = []

        for item in (nse_items + bse_items):
            adapter = self._nse_adapter if item.get("source") == "NSE_OFFICIAL" else self._bse_adapter
            raw_event = adapter.normalize(item)
            is_valid, _ = adapter.validate(raw_event)
            if not is_valid:
                continue

            canonical_id = adapter.identify(raw_event)
            event_date_str = item["event_date"]
            time_str = item.get("time_ist", "14:00:00")
            dt_str = f"{event_date_str}T{time_str}+05:30"
            try:
                event_dt = datetime.fromisoformat(dt_str)
            except Exception:
                event_dt = datetime.combine(date.fromisoformat(event_date_str), datetime.min.time(), tzinfo=IST)

            candidate = CanonicalEvent(
                canonical_event_id=canonical_id,
                title=item["title"],
                description=item.get("description"),
                event_type="COMPANY",
                sub_type=item.get("sub_type", "EARNINGS_BOARD_MEETING"),
                entity_id=item.get("entity", "CORP"),
                entity_name=item.get("entity_name", item.get("entity", "Company")),
                sector=item.get("sector", "BANKING"),
                event_timestamp=event_dt,
                timezone="Asia/Kolkata",
                timestamp_precision=item.get("precision", "EXACT"),
                verification_status="VERIFIED",
                certainty=item.get("certainty", "CONFIRMED"),
                expected_direction="UNKNOWN",
                time_horizon="INTRADAY",
                temporal_phase=lifecycle_service.compute_temporal_phase(event_dt, now),
                metadata={"source_name": item.get("source"), "url": item.get("url")},
            )

            # Dedup check
            matched_existing: Optional[CanonicalEvent] = None
            for existing in self._events.values():
                match_type = dedup_service.classify_match(candidate, existing)
                if match_type in ("EXACT_DUPLICATE", "PROBABLE_DUPLICATE"):
                    matched_existing = existing
                    break

            if matched_existing:
                if not any(s.source_name == raw_event.source_name for s in matched_existing.sources):
                    matched_existing.sources.append(raw_event)
                processed.append(matched_existing)
                continue

            candidate.sources.append(raw_event)
            candidate.impact_mappings = impact_mapping_service.get_mappings_for_event(
                entity_id=candidate.entity_id,
                event_type=candidate.event_type,
                sub_type=candidate.sub_type,
            )
            candidate.scores = scoring_service.score_event(candidate, market_data_available=False)
            candidate.comparables = historical_matcher.match_comparables(candidate, data_cutoff=now, top_k=3)
            candidate.latest_prediction = PredictionSnapshot(
                canonical_event_id=candidate.canonical_event_id,
                prediction_timestamp=now,
                data_cutoff_timestamp=now,
                feature_cutoff_timestamp=now,
                formula_version="v3.0.0",
                configuration_version="v3.0.0",
                importance_score=candidate.scores.importance.final_score,
                market_impact_score=None,
                opportunity_score=None,
                predicted_direction=candidate.expected_direction,
                confidence=0.0,
                strategy_state="NO_SETUP",
                decision=candidate.scores.final_decision,
            )
            candidate.processing_flags.discovered = True
            candidate.processing_flags.verified = True
            candidate.processing_flags.classified = True
            candidate.processing_flags.impact_mapped = True
            candidate.processing_flags.scored = True

            self._events[candidate.canonical_event_id] = candidate
            processed.append(candidate)

        return processed

    async def _sync_sebi_schedule_internal(self) -> list[CanonicalEvent]:
        """Ingest SEBI regulatory circulars."""
        sebi_items = await self._sebi_adapter.fetch()
        now = datetime.now(timezone.utc)
        processed: list[CanonicalEvent] = []

        for item in sebi_items:
            raw_event = self._sebi_adapter.normalize(item)
            is_valid, _ = self._sebi_adapter.validate(raw_event)
            if not is_valid:
                continue

            canonical_id = self._sebi_adapter.identify(raw_event)
            event_date_str = item["event_date"]
            time_str = item.get("time_ist", "18:00:00")
            dt_str = f"{event_date_str}T{time_str}+05:30"
            try:
                event_dt = datetime.fromisoformat(dt_str)
            except Exception:
                event_dt = datetime.combine(date.fromisoformat(event_date_str), datetime.min.time(), tzinfo=IST)

            candidate = CanonicalEvent(
                canonical_event_id=canonical_id,
                title=item["title"],
                description=item.get("description"),
                event_type="REGULATORY",
                sub_type=item.get("sub_type", "REGULATORY_PRUDENTIAL_NORMS"),
                entity_id="SEBI",
                entity_name="Securities and Exchange Board of India",
                sector=item.get("sector", "DERIVATIVES_MARKET"),
                event_timestamp=event_dt,
                timezone="Asia/Kolkata",
                timestamp_precision="EXACT",
                verification_status="VERIFIED",
                certainty="CONFIRMED",
                expected_direction="NEUTRAL",
                time_horizon="MULTI_DAY",
                temporal_phase=lifecycle_service.compute_temporal_phase(event_dt, now),
                metadata={"source_name": "SEBI_OFFICIAL", "url": item.get("url")},
            )

            if canonical_id not in self._events:
                candidate.sources.append(raw_event)
                candidate.impact_mappings = impact_mapping_service.get_mappings_for_event(
                    entity_id=candidate.entity_id,
                    event_type=candidate.event_type,
                    sub_type=candidate.sub_type,
                )
                candidate.scores = scoring_service.score_event(candidate, market_data_available=False)
                self._events[canonical_id] = candidate
                processed.append(candidate)

        return processed

    async def get_live_opportunity(self, event_id: str) -> dict[str, Any]:
        """Compute real-time Trading Opportunity Score using live options & market context (§15, §16, §18)."""
        event = self.get_event_by_id(event_id)
        if not event:
            raise ValueError(f"Event '{event_id}' not found")

        # Resolve primary underlying
        target_symbol = "BANKNIFTY"
        for m in event.impact_mappings:
            if m.target_type == "INDEX":
                target_symbol = m.target_symbol
                break

        # Collect live options context
        live_options = await options_intelligence_service.get_live_options_context(underlying=target_symbol)

        # Score opportunity dynamically
        opportunity = scoring_service.calculate_opportunity_score(
            event=event,
            market_data_available=live_options.market_data_valid,
            live_options=live_options,
            signal_context={"signal_valid": True, "confidence": 80.0, "risk_reward_score": 78.0},
        )

        # Alert evaluation (§29)
        if opportunity.final_decision == "EXECUTE_SHADOW":
            event_alert_service.emit_alert(
                canonical_event_id=event.canonical_event_id,
                alert_type="OPPORTUNITY_CONFIRMED",
                title=f"High Opportunity Setup: {event.title}",
                message=f"Opportunity Score {opportunity.final_score}/100. Operating in SHADOW_MODE for {target_symbol}.",
                severity="HIGH",
                state_fingerprint="SHADOW_ACTIVE",
            )
        elif event.temporal_phase == "APPROACHING":
            event_alert_service.emit_alert(
                canonical_event_id=event.canonical_event_id,
                alert_type="EVENT_APPROACHING",
                title=f"Event Approaching: {event.title}",
                message=f"Scheduled on {event.event_timestamp.strftime('%d %b %Y, %H:%M IST')}. Monitoring volatility surface.",
                severity="MEDIUM",
                state_fingerprint="APPROACHING",
            )

        return {
            "canonical_event_id": event.canonical_event_id,
            "underlying": target_symbol,
            "live_options": live_options.model_dump(),
            "opportunity_score": opportunity.model_dump(),
            "strategy_state": "PRE_EVENT_SETUP" if event.temporal_phase == "APPROACHING" else "DIRECTIONAL_SETUP",
            "execution_mode": "SHADOW_MODE",
        }

    def record_market_reaction(
        self,
        event_id: str,
        primary_instrument: str,
        baseline_price: float,
        price_progression: list[tuple[str, datetime, float]],
        pre_iv: Optional[float] = None,
        post_iv: Optional[float] = None,
    ) -> EventOutcome:
        """Record post-event market reaction (§24)."""
        event = self.get_event_by_id(event_id)
        if not event:
            raise ValueError(f"Event '{event_id}' not found")

        outcome = event_outcome_recorder.calculate_reaction(
            event=event,
            primary_instrument=primary_instrument,
            baseline_price=baseline_price,
            price_progression=price_progression,
            pre_iv=pre_iv,
            post_iv=post_iv,
        )

        # Emit outcome available alert
        event_alert_service.emit_alert(
            canonical_event_id=event.canonical_event_id,
            alert_type="OUTCOME_AVAILABLE",
            title=f"Post-Event Outcome Settled: {event.title}",
            message=f"Actual Move: {outcome.maximum_move_pct}% ({outcome.actual_direction}). Accuracy: {outcome.prediction_correct}.",
            severity="INFO",
            state_fingerprint="SETTLED",
        )
        return outcome

    def get_upcoming_events(self, limit: int = 50) -> list[CanonicalEvent]:
        """List upcoming scheduled or approaching events ordered by timestamp."""
        now = datetime.now(timezone.utc)
        all_events = list(self._events.values())

        # Update dynamic temporal phases
        for ev in all_events:
            ev.temporal_phase = lifecycle_service.compute_temporal_phase(ev.event_timestamp, now)

        sorted_events = sorted(all_events, key=lambda e: e.event_timestamp)
        return sorted_events[:limit]

    def get_today_events(self) -> list[CanonicalEvent]:
        """List events scheduled or active today in IST."""
        now_ist = datetime.now(IST).date()
        today_list: list[CanonicalEvent] = []

        for ev in self._events.values():
            ev_date_ist = ev.event_timestamp.astimezone(IST).date()
            if ev_date_ist == now_ist:
                today_list.append(ev)

        return sorted(today_list, key=lambda e: e.event_timestamp)

    def get_event_by_id(self, event_id: str) -> Optional[CanonicalEvent]:
        """Find event by canonical_event_id or UUID."""
        if event_id in self._events:
            return self._events[event_id]
        for ev in self._events.values():
            if ev.id == event_id:
                return ev
        return None

    def get_all_events(self) -> list[CanonicalEvent]:
        """Return all tracked canonical events."""
        return list(self._events.values())

    def get_track_record(self):
        """Statistical Edge Validation & Track Record Summary (§23, §24)."""
        return event_validation_service.compute_track_record()

    def get_source_health(self):
        """Live Source Health & Circuit Breaker Telemetry (§5, §34)."""
        return event_ingestion_scheduler.get_telemetry()

    def get_risk_overlay(self, underlying: str = "BANKNIFTY", now: Optional[datetime] = None):
        """Active Event-Aware Risk Overlay Parameters (§28)."""
        return event_risk_overlay_service.evaluate_overlay(underlying, list(self._events.values()), now=now)

    def calibrate_all_events(self) -> dict[str, Any]:
        """Trigger empirical calibration across all canonical events (§14)."""
        calibrated = 0
        for ev in self._events.values():
            new_impact = market_impact_calibration_service.calibrate_market_impact(ev)
            if ev.scores:
                ev.scores.market_impact = new_impact
                calibrated += 1
        summary = market_impact_calibration_service.get_calibration_summary()
        return {
            "calibrated_events": calibrated,
            "summary": summary.model_dump(),
        }


event_engine_service = EventEngineService()
