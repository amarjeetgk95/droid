from datetime import datetime, date
from typing import Optional, Any, Dict
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


# ============================================================
# Profile schemas
# ============================================================

class ProfileBase(BaseModel):
    display_name: Optional[str] = None

class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None

class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    display_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ============================================================
# User settings schemas
# ============================================================

class UserSettingsBase(BaseModel):
    theme: str = "dark"
    default_symbol: str = "NIFTY"
    default_timeframe: str = "5m"
    default_expiry: Optional[str] = None
    preferred_market_provider: str = "fyers"
    preferred_ai_provider: str = "gemini"
    preferred_ai_model: Optional[str] = None
    notification_enabled: bool = True

class UserSettingsUpdate(BaseModel):
    theme: Optional[str] = None
    default_symbol: Optional[str] = None
    default_timeframe: Optional[str] = None
    default_expiry: Optional[str] = None
    preferred_market_provider: Optional[str] = None
    preferred_ai_provider: Optional[str] = None
    preferred_ai_model: Optional[str] = None
    notification_enabled: Optional[bool] = None
    # Full AppSettings JSON — RECTIFY: enable Supabase as primary store
    app_settings: Optional[Dict[str, Any]] = None

class UserSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    theme: str
    default_symbol: str
    default_timeframe: str
    default_expiry: Optional[str] = None
    preferred_market_provider: str
    preferred_ai_provider: str
    preferred_ai_model: Optional[str] = None
    notification_enabled: bool
    app_settings: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


# ============================================================
# Watchlist schemas
# ============================================================

class WatchlistCreate(BaseModel):
    name: str = Field(default="My Watchlist", min_length=1, max_length=100)

class WatchlistUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)

class WatchlistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    name: str
    created_at: datetime
    updated_at: datetime


# ============================================================
# Watchlist item schemas
# ============================================================

class WatchlistItemCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=50)
    instrument_id: Optional[int] = None
    display_order: int = 0

class WatchlistItemUpdate(BaseModel):
    display_order: Optional[int] = None
    symbol: Optional[str] = Field(default=None, min_length=1, max_length=50)

class WatchlistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    watchlist_id: UUID
    instrument_id: Optional[int] = None
    symbol: str
    display_order: int
    created_at: datetime


# ============================================================
# Instrument schemas
# ============================================================

class InstrumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    symbol: str
    display_name: str
    exchange: str
    instrument_type: str
    underlying: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ============================================================
# Expiry schemas
# ============================================================

class ExpiryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    instrument_id: Optional[int] = None
    expiry_date: date
    expiry_datetime: Optional[datetime] = None
    expiry_type: str
    is_active: bool
    metadata_source: Optional[str] = None
    effective_from: Optional[date] = None
    effective_until: Optional[date] = None
    created_at: datetime
    updated_at: datetime
