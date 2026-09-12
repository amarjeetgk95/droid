from datetime import datetime
from pydantic import BaseModel, Field
from typing import Literal


class ClientCategoryPosition(BaseModel):
    category: Literal["FII", "DII", "PRO", "CLIENT"]
    index_futures_long: int
    index_futures_short: int
    index_futures_net: int
    long_short_ratio: float
    index_call_long: int
    index_put_long: int
    sentiment: Literal["BULLISH", "MILD_BULLISH", "NEUTRAL", "MILD_BEARISH", "BEARISH"]


class CashMarketFlow(BaseModel):
    category: Literal["FII", "DII"]
    buy_value_crores: float
    sell_value_crores: float
    net_value_crores: float
    date: str


class FIIDIIOverviewResponse(BaseModel):
    timestamp: datetime
    # Provenance — truth-of-wall: no live FII/DII feed is wired (NSE publishes
    # daily files; FYERS has no FII/DII endpoint). Values are a static snapshot
    # unless source == "live". Consumers must not present these as live flow.
    source: str = Field(default="static_snapshot", description="live | static_snapshot")
    as_of: str = Field(default="2026-08-29", description="Session date the snapshot values belong to")
    live_available: bool = Field(default=False, description="True only when backed by a live feed")
    fii_long_short_ratio: float = Field(description="FII Index Futures Long/Short ratio e.g. 1.25")
    fii_futures_net_contracts: int
    dii_futures_net_contracts: int
    client_futures_net_contracts: int
    pro_futures_net_contracts: int
    fii_cash_net_crores: float
    dii_cash_net_crores: float
    institutional_sentiment: Literal["STRONG_BULLISH", "MILD_BULLISH", "NEUTRAL", "MILD_BEARISH", "STRONG_BEARISH"]
    breakdown_by_category: list[ClientCategoryPosition] = Field(default_factory=list)
    recent_cash_flows: list[CashMarketFlow] = Field(default_factory=list)
