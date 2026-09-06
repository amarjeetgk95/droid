from datetime import datetime, date
from typing import Optional, Any
from uuid import UUID, uuid4
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, Text,
    Float, UniqueConstraint, Date as SQLDate, func
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.models.database import Base


class MarketEventDB(Base):
    __tablename__ = "market_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_event_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    sub_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    entity_name: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[str] = mapped_column(Text, default="BANKING")
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(Text, default="Asia/Kolkata")
    timestamp_precision: Mapped[str] = mapped_column(Text, default="EXACT")
    verification_status: Mapped[str] = mapped_column(Text, default="UNVERIFIED")
    certainty: Mapped[str] = mapped_column(Text, default="CONFIRMED")
    expected_direction: Mapped[str] = mapped_column(Text, default="UNKNOWN")
    time_horizon: Mapped[str] = mapped_column(Text, default="INTRADAY")
    temporal_phase: Mapped[str] = mapped_column(Text, default="SCHEDULED", index=True)
    processing_flags: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: {
            "discovered": True,
            "verified": False,
            "classified": False,
            "impact_mapped": False,
            "scored": False,
        },
    )
    source_priority: Mapped[str] = mapped_column(Text, default="PRIMARY")
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    sources: Mapped[list["EventSourceDB"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    lifecycle_transitions: Mapped[list["EventLifecycleTransitionDB"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="EventLifecycleTransitionDB.timestamp.desc()"
    )
    impact_mappings: Mapped[list["EventImpactMappingDB"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    scores: Mapped[list["EventScoreDB"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="EventScoreDB.calculated_at.desc()"
    )
    predictions: Mapped[list["EventPredictionSnapshotDB"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="EventPredictionSnapshotDB.prediction_timestamp.desc()"
    )
    comparables: Mapped[list["EventComparableDB"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    alerts: Mapped[list["EventAlertDB"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    outcomes: Mapped[list["EventOutcomeDB"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    shadow_signals: Mapped[list["EventShadowSignalDB"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class EventSourceDB(Base):
    __tablename__ = "event_sources"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_event_id: Mapped[str] = mapped_column(
        Text, ForeignKey("market_events.canonical_event_id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    fetch_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    event: Mapped["MarketEventDB"] = relationship(back_populates="sources")


class EventLifecycleTransitionDB(Base):
    __tablename__ = "event_lifecycle_transitions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_event_id: Mapped[str] = mapped_column(
        Text, ForeignKey("market_events.canonical_event_id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_phase: Mapped[str] = mapped_column(Text, nullable=False)
    to_phase: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, default="EVENT_ENGINE")
    event_version: Mapped[int] = mapped_column(Integer, default=1)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    transition_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    event: Mapped["MarketEventDB"] = relationship(back_populates="lifecycle_transitions")


class EventImpactMappingDB(Base):
    __tablename__ = "event_impact_mappings"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_event_id: Mapped[str] = mapped_column(
        Text, ForeignKey("market_events.canonical_event_id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_symbol: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    impact_strength: Mapped[str] = mapped_column(Text, nullable=False)
    relationship_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    historical_sensitivity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    primary_or_secondary: Mapped[str] = mapped_column(Text, default="PRIMARY")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped["MarketEventDB"] = relationship(back_populates="impact_mappings")


class EventScoreDB(Base):
    __tablename__ = "event_scores"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_event_id: Mapped[str] = mapped_column(
        Text, ForeignKey("market_events.canonical_event_id", ondelete="CASCADE"), nullable=False, index=True
    )
    formula_version: Mapped[str] = mapped_column(Text, default="v3.0.0")
    importance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    importance_breakdown: Mapped[dict] = mapped_column(JSONB, default=dict)
    market_impact_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_impact_status: Mapped[str] = mapped_column(Text, default="INSUFFICIENT_DATA")
    market_impact_breakdown: Mapped[dict] = mapped_column(JSONB, default=dict)
    opportunity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opportunity_status: Mapped[str] = mapped_column(Text, default="INSUFFICIENT_DATA")
    opportunity_breakdown: Mapped[dict] = mapped_column(JSONB, default=dict)
    final_decision: Mapped[str] = mapped_column(Text, default="NO_TRADE")
    gate_evaluation: Mapped[dict] = mapped_column(JSONB, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped["MarketEventDB"] = relationship(back_populates="scores")


class EventPredictionSnapshotDB(Base):
    __tablename__ = "event_prediction_snapshots"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_event_id: Mapped[str] = mapped_column(
        Text, ForeignKey("market_events.canonical_event_id", ondelete="CASCADE"), nullable=False, index=True
    )
    prediction_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    data_cutoff_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    feature_cutoff_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    formula_version: Mapped[str] = mapped_column(Text, nullable=False)
    configuration_version: Mapped[str] = mapped_column(Text, nullable=False)
    importance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_impact_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opportunity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    predicted_direction: Mapped[str] = mapped_column(Text, default="UNKNOWN")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    strategy_state: Mapped[str] = mapped_column(Text, default="NO_SETUP")
    decision: Mapped[str] = mapped_column(Text, default="NO_TRADE")
    snapshot_immutable: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped["MarketEventDB"] = relationship(back_populates="predictions")


class EventComparableDB(Base):
    __tablename__ = "event_comparables"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_event_id: Mapped[str] = mapped_column(
        Text, ForeignKey("market_events.canonical_event_id", ondelete="CASCADE"), nullable=False, index=True
    )
    past_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    past_event_date: Mapped[date] = mapped_column(SQLDate, nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    key_comparison_factor: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    past_market_reaction: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped["MarketEventDB"] = relationship(back_populates="comparables")


class EventAlertDB(Base):
    __tablename__ = "event_alerts"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    alert_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    canonical_event_id: Mapped[str] = mapped_column(
        Text, ForeignKey("market_events.canonical_event_id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, default="MEDIUM")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    dedup_signature: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    status: Mapped[str] = mapped_column(Text, default="PENDING_REVIEW", index=True)
    cooldown_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped["MarketEventDB"] = relationship(back_populates="alerts")


class EventOutcomeDB(Base):
    __tablename__ = "event_outcomes"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    canonical_event_id: Mapped[str] = mapped_column(
        Text, ForeignKey("market_events.canonical_event_id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    predicted_direction: Mapped[str] = mapped_column(Text, nullable=False)
    actual_direction: Mapped[str] = mapped_column(Text, nullable=False)
    prediction_correct: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    initial_move_pct: Mapped[float] = mapped_column(Float, default=0.0)
    maximum_move_pct: Mapped[float] = mapped_column(Float, default=0.0)
    mfe_pct: Mapped[float] = mapped_column(Float, default=0.0)
    mae_pct: Mapped[float] = mapped_column(Float, default=0.0)
    time_to_peak_min: Mapped[int] = mapped_column(Integer, default=0)
    time_to_reversal_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    realized_volatility_change: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    iv_change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    oi_change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    primary_instrument: Mapped[str] = mapped_column(Text, nullable=False)
    monitoring_snapshots: Mapped[list] = mapped_column(JSONB, default=list)
    is_settled: Mapped[bool] = mapped_column(Boolean, default=False)

    event: Mapped["MarketEventDB"] = relationship(back_populates="outcomes")


class EventShadowSignalDB(Base):
    __tablename__ = "event_shadow_signals"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    shadow_signal_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    canonical_event_id: Mapped[str] = mapped_column(
        Text, ForeignKey("market_events.canonical_event_id", ondelete="CASCADE"), nullable=False, index=True
    )
    base_signal_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    underlying: Mapped[str] = mapped_column(Text, nullable=False)
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    execution_mode: Mapped[str] = mapped_column(Text, default="SHADOW_MODE")
    event_importance_score: Mapped[float] = mapped_column(Float, nullable=False)
    event_market_impact_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    event_opportunity_score: Mapped[float] = mapped_column(Float, nullable=False)
    suggested_sizing_factor: Mapped[float] = mapped_column(Float, default=1.0)
    simulated_entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    simulated_exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    simulated_pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    shadow_status: Mapped[str] = mapped_column(Text, default="TRACKING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    event: Mapped["MarketEventDB"] = relationship(back_populates="shadow_signals")
