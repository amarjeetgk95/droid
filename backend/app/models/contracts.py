from datetime import datetime, date
from enum import Enum
from pydantic import BaseModel, Field


class ContractType(str, Enum):
    INDEX_OPTION = "INDEX_OPTION"
    STOCK_OPTION = "STOCK_OPTION"
    INDEX_FUTURE = "INDEX_FUTURE"
    STOCK_FUTURE = "STOCK_FUTURE"
    INDEX_SPOT = "INDEX_SPOT"
    EQUITY_SPOT = "EQUITY_SPOT"


class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"


class OptionStyle(str, Enum):
    EUROPEAN = "EUROPEAN"
    AMERICAN = "AMERICAN"


class ExpiryType(str, Enum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    FAR = "FAR"


class SettlementType(str, Enum):
    CASH_SETTLED = "CASH_SETTLED"
    PHYSICAL_DELIVERY = "PHYSICAL_DELIVERY"


class PricingStyle(str, Enum):
    FUTURES_BLACK76 = "FUTURES_BLACK76"
    SPOT_BLACK_SCHOLES = "SPOT_BLACK_SCHOLES"


class ContractStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    SUSPENDED = "SUSPENDED"


class EventPriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ContractMaster(BaseModel):
    """Data-driven contract metadata model.
    
    Adheres strictly to Sections 15, 18, and 19 of the platform spec.
    """
    instrument_token: str
    exchange: str = "NFO"
    symbol: str
    underlying: str
    contract_type: ContractType
    option_type: OptionType | None = None
    option_style: OptionStyle = OptionStyle.EUROPEAN
    strike: float | None = None
    expiry: date | None = None
    expiry_type: ExpiryType = ExpiryType.WEEKLY
    lot_size: int = 25
    tick_size: float = 0.05
    settlement_type: SettlementType = SettlementType.CASH_SETTLED
    pricing_style: PricingStyle = PricingStyle.FUTURES_BLACK76
    contract_status: ContractStatus = ContractStatus.ACTIVE
    effective_from: date
    effective_until: date | None = None
    provider: str = "fyers"


class ExpiryResolution(BaseModel):
    """Dynamic resolution of expiries for an underlying without hardcoded weekdays."""
    underlying: str
    current_expiry: date | None = None
    next_expiry: date | None = None
    weekly_expiries: list[date] = Field(default_factory=list)
    monthly_expiries: list[date] = Field(default_factory=list)
    all_expiries: list[date] = Field(default_factory=list)


class TickEvent(BaseModel):
    """High-frequency market tick event."""
    timestamp: datetime
    symbol: str
    instrument_token: str = ""
    ltp: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int = 0
    open_interest: int | None = None
    bid: float | None = None
    ask: float | None = None
    bid_qty: int | None = None
    ask_qty: int | None = None
    sequence_number: int | None = None
    provider: str = "fyers"
    priority: EventPriority = EventPriority.HIGH
