from pydantic import BaseModel, Field


class BacktestPayload(BaseModel):
    """Execution parameters for quantitative backtest."""
    strategy_id: str = Field(default="short_straddle")
    underlying: str = Field(default="NIFTY")
    initial_capital: float = Field(default=500000.0, ge=50000.0)
    num_days: int = Field(default=60, ge=5, le=365)
    stop_loss_pct: float = Field(default=25.0, ge=5.0, le=100.0)
    target_pct: float = Field(default=50.0, ge=10.0, le=300.0)
    slippage_pct: float = Field(default=0.001, ge=0.0, le=0.01)
    include_costs: bool = Field(default=True)


class BacktestTradeModel(BaseModel):
    """Simulated trade log item."""
    trade_id: str
    entry_date: str
    exit_date: str
    strategy_name: str
    underlying: str
    legs_description: str
    entry_price: float
    exit_price: float
    quantity: int
    gross_pnl: float
    total_charges: float
    net_pnl: float
    status: str


class EquityPointModel(BaseModel):
    """Equity and drawdown timeseries point."""
    timestamp: str
    equity: float
    drawdown_pct: float
    net_pnl: float


class MonthlyPnlModel(BaseModel):
    """Monthly performance matrix bucket."""
    month_year: str
    net_pnl: float
    trades_count: int
    win_rate_pct: float


class BacktestResult(BaseModel):
    """Comprehensive backtest performance report."""
    initial_capital: float
    final_equity: float
    total_net_pnl: float
    net_roi_percent: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_percent: float
    profit_factor: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_amount: float
    max_drawdown_percent: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    equity_curve: list[EquityPointModel]
    monthly_pnl: list[MonthlyPnlModel]
    trades: list[BacktestTradeModel]


class BacktestPreset(BaseModel):
    """Pre-built institutional strategy preset."""
    id: str
    name: str
    description: str
    category: str
    default_underlying: str
    default_stop_loss_pct: float
    default_target_pct: float
