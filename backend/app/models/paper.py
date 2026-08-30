from typing import Literal
from pydantic import BaseModel, Field

OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT", "SL_MARKET", "SL_LIMIT"]
ProductType = Literal["INTRADAY", "CARRYFORWARD"]
OrderStatus = Literal["PENDING", "FILLED", "CANCELLED", "REJECTED"]


class OrderPayload(BaseModel):
    """Payload for placing a single virtual order."""
    symbol: str
    underlying: str
    side: OrderSide
    order_type: OrderType = "MARKET"
    product: ProductType = "INTRADAY"
    quantity: int = Field(gt=0)
    price: float = Field(default=0.0, ge=0.0)
    trigger_price: float | None = None


class BasketOrderPayload(BaseModel):
    """Payload for executing a multi-leg strategy basket."""
    name: str = "Strategy Basket"
    orders: list[OrderPayload] = Field(min_length=1)


class VirtualOrder(BaseModel):
    """Executed or pending virtual order."""
    order_id: str
    timestamp: str
    symbol: str
    underlying: str
    side: OrderSide
    order_type: OrderType
    product: ProductType
    quantity: int
    price: float
    trigger_price: float | None = None
    status: OrderStatus = "FILLED"
    fill_price: float | None = None
    rejection_reason: str | None = None


class VirtualPosition(BaseModel):
    """Open or closed virtual trading position."""
    position_id: str
    symbol: str
    underlying: str
    instrument_type: str
    side: OrderSide
    product: ProductType
    quantity: int
    average_price: float
    ltp: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    used_margin: float = 0.0
    is_open: bool = True


class PortfolioSummary(BaseModel):
    """Virtual account summary with margin & real-time MTM."""
    virtual_capital: float = 1000000.0
    available_margin: float = 1000000.0
    used_margin: float = 0.0
    margin_utilization_pct: float = 0.0
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_portfolio_pnl: float = 0.0
    open_positions_count: int = 0
