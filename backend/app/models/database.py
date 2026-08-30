from datetime import datetime
from typing import Optional, Any
from uuid import UUID, uuid4
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, BigInteger,
    Float, UniqueConstraint, Date, func
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ============================================================
# Profiles Table
# ============================================================
class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    settings: Mapped[Optional["UserSettings"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    watchlists: Mapped[list["Watchlist"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    alert_rules: Mapped[list["AlertRuleDB"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    paper_portfolio: Mapped[Optional["PaperPortfolioDB"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


# ============================================================
# User Settings Table
# ============================================================
class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), unique=True, nullable=False)
    theme: Mapped[str] = mapped_column(Text, default="dark")
    default_symbol: Mapped[str] = mapped_column(Text, default="NIFTY")
    default_timeframe: Mapped[str] = mapped_column(Text, default="5m")
    default_expiry: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preferred_market_provider: Mapped[str] = mapped_column(Text, default="mock")
    preferred_ai_provider: Mapped[str] = mapped_column(Text, default="mock_ai")
    preferred_ai_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notification_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["Profile"] = relationship(back_populates="settings")


# ============================================================
# Watchlists Table
# ============================================================
class Watchlist(Base):
    __tablename__ = "watchlists"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_watchlists_user_name"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, default="My Watchlist")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["Profile"] = relationship(back_populates="watchlists")
    items: Mapped[list["WatchlistItem"]] = relationship(back_populates="watchlist", cascade="all, delete-orphan", order_by="WatchlistItem.display_order")


# ============================================================
# Watchlist Items Table
# ============================================================
class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    watchlist_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False)
    instrument_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("instruments.id", ondelete="SET NULL"), nullable=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    watchlist: Mapped["Watchlist"] = relationship(back_populates="items")
    instrument: Mapped[Optional["Instrument"]] = relationship()


# ============================================================
# Instruments Table
# ============================================================
class Instrument(Base):
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("exchange", "symbol", name="uq_instruments_exchange_symbol"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    exchange: Mapped[str] = mapped_column(Text, default="NSE")
    instrument_type: Mapped[str] = mapped_column(Text, default="INDEX")
    underlying: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    expiries: Mapped[list["Expiry"]] = relationship(back_populates="instrument", cascade="all, delete-orphan")


# ============================================================
# Expiries Table
# ============================================================
class Expiry(Base):
    __tablename__ = "expiries"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    instrument_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=True)
    expiry_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    expiry_datetime: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expiry_type: Mapped[str] = mapped_column(Text, default="WEEKLY")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    effective_until: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    instrument: Mapped[Optional["Instrument"]] = relationship(back_populates="expiries")


# ============================================================
# Alert Rules Table
# ============================================================
class AlertRuleDB(Base):
    __tablename__ = "alert_rules"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    condition: Mapped[str] = mapped_column(Text, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    channel: Mapped[str] = mapped_column(Text, default="IN_APP")
    webhook_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["Profile"] = relationship(back_populates="alert_rules")


# ============================================================
# Alert History Table
# ============================================================
class AlertHistoryDB(Base):
    __tablename__ = "alert_history"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    alert_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    alert_name: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    triggered_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    channel_dispatched: Mapped[str] = mapped_column(Text, default="IN_APP")


# ============================================================
# Paper Trading Portfolio Table
# ============================================================
class PaperPortfolioDB(Base):
    __tablename__ = "paper_portfolios"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), unique=True, nullable=False)
    virtual_capital: Mapped[float] = mapped_column(Float, default=1000000.0)
    available_margin: Mapped[float] = mapped_column(Float, default=1000000.0)
    used_margin: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["Profile"] = relationship(back_populates="paper_portfolio")


# ============================================================
# Paper Trading Orders Table
# ============================================================
class PaperOrderDB(Base):
    __tablename__ = "paper_orders"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    underlying: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    order_type: Mapped[str] = mapped_column(Text, default="MARKET")
    product: Mapped[str] = mapped_column(Text, default="INTRADAY")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    trigger_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="FILLED")
    fill_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# Paper Trading Positions Table
# ============================================================
class PaperPositionDB(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (
        UniqueConstraint("user_id", "position_id", name="uq_paper_positions_user_pos"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    position_id: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    underlying: Mapped[str] = mapped_column(Text, nullable=False)
    instrument_type: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    product: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    average_price: Mapped[float] = mapped_column(Float, nullable=False)
    ltp: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    used_margin: Mapped[float] = mapped_column(Float, default=0.0)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ============================================================
# ML Predictions Table
# ============================================================
class MLPredictionDB(Base):
    __tablename__ = "ml_predictions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    spot_price: Mapped[float] = mapped_column(Float, default=0.0)
    bullish_pct: Mapped[float] = mapped_column(Float, nullable=False)
    neutral_pct: Mapped[float] = mapped_column(Float, nullable=False)
    bearish_pct: Mapped[float] = mapped_column(Float, nullable=False)
    trend_strength: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_bias: Mapped[str] = mapped_column(Text, nullable=False)
    market_regime: Mapped[str] = mapped_column(Text, nullable=False)
    top_features: Mapped[Any] = mapped_column(JSONB, default=list)
    model_version: Mapped[str] = mapped_column(Text, default="XGBoost-LightGBM-Ensemble-v1.0")


# ============================================================
# AI Reports Table
# ============================================================
class AIReportDB(Base):
    __tablename__ = "ai_reports"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, default="mock_ai")
    market_bias: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    raw_json: Mapped[Any] = mapped_column(JSONB, default=dict)
    user_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True)
