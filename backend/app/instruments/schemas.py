from pydantic import BaseModel, Field
from typing import Literal

AssetClass = Literal["INDEX", "EQUITY", "CRYPTO", "COMMODITY", "FX", "ETF"]
InstrumentType = Literal["INDEX", "SPOT", "FUTURES", "OPTIONS", "EQUITY", "ETF"]
ExchangeLiteral = str

class InstrumentConfig(BaseModel):
    symbol: str = Field(description="Canonical symbol, e.g. BANKNIFTY")
    display_name: str
    aliases: list[str] = Field(default_factory=list)
    asset_class: AssetClass
    exchange: str
    data_provider_symbol: str
    instrument_type: InstrumentType
    currency: str = "INR"
    price_precision: int = 2
    supported_timeframes: list[str] = Field(default_factory=lambda: ["1m", "5m", "15m", "1h"])
    fno_available: bool = False
    options_available: bool = False
    futures_available: bool = False
    trading_session: str = "NSE_0915_1530"
    timezone: str = "Asia/Kolkata"

class InstrumentSearchResult(BaseModel):
    display_name: str
    symbol: str
    asset_class: str
    exchange: str
    instrument_type: str
    fno_available: bool
    options_available: bool = False
    futures_available: bool = False
    supported_timeframes: list[str] = Field(default_factory=list)
    data_provider_symbol: str | None = None
    current_status: str = "ACTIVE"

class InstrumentSearchResponse(BaseModel):
    query: str
    results: list[InstrumentSearchResult]
    total: int
