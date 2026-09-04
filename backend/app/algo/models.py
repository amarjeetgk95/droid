"""
SQLAlchemy ORM models for algo trading — mirrors 006_algo_trading.sql
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, Any
from uuid import UUID, uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, Date, func, Numeric
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base  # reuse Base


# ── Algo Accounts ───────────────────────────────────────────────────
class AlgoAccount(Base):
    __tablename__ = "algo_accounts"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(Text, default="OFF")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AlgoCapitalConfig(Base):
    __tablename__ = "algo_capital_config"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("algo_accounts.id", ondelete="CASCADE"), unique=True, nullable=False)
    investment_limit: Mapped[Any] = mapped_column(Numeric(18,2), default=3000)
    max_capital_per_trade: Mapped[Any] = mapped_column(Numeric(18,2), default=1000)
    max_daily_loss: Mapped[Any] = mapped_column(Numeric(18,2), default=500)
    max_loss_per_trade: Mapped[Any] = mapped_column(Numeric(18,2), default=200)
    max_open_positions: Mapped[int] = mapped_column(Integer, default=5)
    max_trades_per_day: Mapped[int] = mapped_column(Integer, default=20)
    max_position_quantity: Mapped[int] = mapped_column(Integer, default=500)
    max_slippage_pct: Mapped[Any] = mapped_column(Numeric(8,4), default=0.3)
    max_spread_pct: Mapped[Any] = mapped_column(Numeric(8,4), default=0.5)
    portfolio_gross_exposure_limit: Mapped[Optional[Any]] = mapped_column(Numeric(18,2), nullable=True)
    portfolio_net_exposure_limit: Mapped[Optional[Any]] = mapped_column(Numeric(18,2), nullable=True)
    portfolio_margin_limit_pct: Mapped[Optional[Any]] = mapped_column(Numeric(8,2), default=80.0)
    portfolio_var_limit: Mapped[Optional[Any]] = mapped_column(Numeric(18,2), nullable=True)
    portfolio_stress_limit: Mapped[Optional[Any]] = mapped_column(Numeric(18,2), nullable=True)
    portfolio_delta_limit: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    portfolio_gamma_limit: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    portfolio_vega_limit: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    underlying_concentration_pct: Mapped[Optional[Any]] = mapped_column(Numeric(8,2), default=30.0)
    strategy_concentration_pct: Mapped[Optional[Any]] = mapped_column(Numeric(8,2), default=40.0)
    expiry_concentration_pct: Mapped[Optional[Any]] = mapped_column(Numeric(8,2), default=50.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AlgoCapitalReservation(Base):
    __tablename__ = "algo_capital_reservations"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("algo_accounts.id", ondelete="CASCADE"), nullable=False)
    reservation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), unique=True, nullable=False)
    client_order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    amount: Mapped[Any] = mapped_column(Numeric(18,2), nullable=False)
    status: Mapped[str] = mapped_column(Text, default="RESERVED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AlgoPositionDB(Base):
    __tablename__ = "algo_positions"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("algo_accounts.id", ondelete="CASCADE"), nullable=False)
    position_id: Mapped[str] = mapped_column(Text, nullable=False)
    instrument_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    underlying: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    lot_size: Mapped[int] = mapped_column(Integer, default=1)
    average_entry: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    current_price: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    stop_price: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    target_price: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    trailing_stop: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    strategy_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signal_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    capital_allocated: Mapped[Optional[Any]] = mapped_column(Numeric(18,2), nullable=True)
    unrealized_pnl: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), default=0)
    realized_pnl: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), default=0)
    margin_used: Mapped[Optional[Any]] = mapped_column(Numeric(18,2), default=0)
    greeks: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    exit_state: Mapped[str] = mapped_column(Text, default="NONE")
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AlgoOrderDB(Base):
    __tablename__ = "algo_orders"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("algo_accounts.id", ondelete="CASCADE"), nullable=False)
    client_order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    broker_order_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signal_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    strategy_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    spread_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    instrument_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    trigger_price: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    order_type: Mapped[str] = mapped_column(Text, default="LIMIT")
    product: Mapped[str] = mapped_column(Text, default="INTRADAY")
    status: Mapped[str] = mapped_column(Text, default="CREATED")
    execution_mode: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    leg_risk_policy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expected_price: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    fill_price: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    fill_quantity: Mapped[int] = mapped_column(Integer, default=0)
    slippage: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    broker_response: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reconciled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AlgoSignalDB(Base):
    __tablename__ = "algo_signals"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    signal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), unique=True, nullable=False)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("algo_accounts.id", ondelete="CASCADE"), nullable=False)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    instrument_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    market_snapshot_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    technical_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    mtf_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    fo_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    regime: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    score: Mapped[Optional[Any]] = mapped_column(Numeric(8,2), nullable=True)
    confidence: Mapped[Optional[Any]] = mapped_column(Numeric(8,4), nullable=True)
    invalidation_conditions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlgoKillSwitch(Base):
    __tablename__ = "algo_kill_switch"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("algo_accounts.id", ondelete="CASCADE"), unique=True, nullable=False)
    is_killed: Mapped[bool] = mapped_column(Boolean, default=False)
    kill_level: Mapped[str] = mapped_column(Text, default="NONE")
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_by: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AlgoConsent(Base):
    __tablename__ = "algo_consent"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("algo_accounts.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    disclosure_version: Mapped[str] = mapped_column(Text, nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlgoRiskDecision(Base):
    __tablename__ = "algo_risk_decisions"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    signal_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    client_order_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failed_check: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checks: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    portfolio_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlgoAuditLog(Base):
    __tablename__ = "algo_audit_log"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signal_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    symbol: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    instrument_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    market_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    technical_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    mtf_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    fo_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ai_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signal: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    trigger: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trade_risk_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    portfolio_risk_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_checks: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    capital_limit: Mapped[Optional[Any]] = mapped_column(Numeric(18,2), nullable=True)
    reservation_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    client_order_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    broker_order_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    expected_price: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    trigger_price: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    actual_fill: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    slippage: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    realized_pnl: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    portfolio_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reconciliation_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_health_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlgoReconciliationLog(Base):
    __tablename__ = "algo_reconciliation_log"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reconciliation_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    internal_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    broker_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    discrepancy: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    magnitude: Mapped[Optional[Any]] = mapped_column(Numeric(18,4), nullable=True)
    affected_order_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    affected_position_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlgoDailyRiskState(Base):
    __tablename__ = "algo_daily_risk_state"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    realized_pnl: Mapped[Any] = mapped_column(Numeric(18,2), default=0)
    trade_count: Mapped[int] = mapped_column(Integer, default=0)
    loss_limit_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AlgoStrategy(Base):
    __tablename__ = "algo_strategies"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("algo_accounts.id", ondelete="CASCADE"), nullable=False)
    strategy_id: Mapped[str] = mapped_column(Text, nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parameters: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    weights: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ai_mode: Mapped[str] = mapped_column(Text, default="AI_OPTIONAL")
    entry_order_type: Mapped[str] = mapped_column(Text, default="LIMIT")
    exit_order_type: Mapped[str] = mapped_column(Text, default="MARKETABLE_LIMIT")
    emergency_exit_type: Mapped[str] = mapped_column(Text, default="MARKET")
    max_slippage_pct: Mapped[Optional[Any]] = mapped_column(Numeric(8,4), nullable=True)
    max_price_deviation_pct: Mapped[Optional[Any]] = mapped_column(Numeric(8,4), nullable=True)
    target_delta: Mapped[Optional[Any]] = mapped_column(Numeric(8,4), default=0.60)
    expiry_policy: Mapped[Optional[str]] = mapped_column(Text, default="WEEKLY")
    liquidity_thresholds: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    conflict_policy: Mapped[str] = mapped_column(Text, default="REJECT_BOTH_AND_ALERT")
    priority_rank: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(Text, default="PAPER")
    backtest_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_by: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
