import uuid
from app.models.backtest import (
    BacktestPayload, BacktestResult, BacktestPreset,
    BacktestTradeModel, EquityPointModel, MonthlyPnlModel
)
from app.quant.backtester import run_strategy_backtest
import structlog

logger = structlog.get_logger()


class BacktestService:
    """Quantitative Strategy Backtesting Service."""

    def __init__(self):
        self._history: list[BacktestResult] = []
        self._presets: list[BacktestPreset] = [
            BacktestPreset(
                id="short_straddle",
                name="9:20 Intraday Short Straddle",
                description="Sell ATM Call & Put at 09:20 IST with 25% individual stop loss. Captures rapid intraday theta decay on NIFTY & BANKNIFTY.",
                category="NON_DIRECTIONAL",
                default_underlying="NIFTY",
                default_stop_loss_pct=25.0,
                default_target_pct=50.0,
            ),
            BacktestPreset(
                id="iron_condor",
                name="Weekly Defined-Risk Iron Condor",
                description="Sell 25-Delta OTM Call/Put spreads on Friday/Monday, expire on Thursday. Captures rangebound premium with defined max loss wings.",
                category="NON_DIRECTIONAL",
                default_underlying="BANKNIFTY",
                default_stop_loss_pct=30.0,
                default_target_pct=60.0,
            ),
            BacktestPreset(
                id="volatility_breakout",
                name="ATM Straddle Volatility Breakout",
                description="Buy ATM Call & Put on Bollinger Squeeze breakouts. Low win-rate with massive asymmetric multi-bagger gamma upside.",
                category="VOLATILITY",
                default_underlying="NIFTY",
                default_stop_loss_pct=35.0,
                default_target_pct=150.0,
            ),
        ]

    def get_presets(self) -> list[BacktestPreset]:
        """Retrieve pre-built strategy templates."""
        return self._presets

    def execute_backtest(self, payload: BacktestPayload) -> BacktestResult:
        """Run quantitative backtest simulation."""
        raw_result = run_strategy_backtest(
            strategy_id=payload.strategy_id,
            underlying=payload.underlying,
            initial_capital=payload.initial_capital,
            num_days=payload.num_days,
            stop_loss_pct=payload.stop_loss_pct,
            target_pct=payload.target_pct,
            slippage_pct=payload.slippage_pct,
            include_costs=payload.include_costs,
        )

        trades = [
            BacktestTradeModel(
                trade_id=t.trade_id,
                entry_date=t.entry_date,
                exit_date=t.exit_date,
                strategy_name=t.strategy_name,
                underlying=t.underlying,
                legs_description=t.legs_description,
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                quantity=t.quantity,
                gross_pnl=t.gross_pnl,
                total_charges=t.total_charges,
                net_pnl=t.net_pnl,
                status=t.status,
            )
            for t in raw_result.trades
        ]

        equity_curve = [
            EquityPointModel(
                timestamp=e.timestamp,
                equity=e.equity,
                drawdown_pct=e.drawdown_pct,
                net_pnl=e.net_pnl,
            )
            for e in raw_result.equity_curve
        ]

        monthly_pnl = [
            MonthlyPnlModel(
                month_year=m.month_year,
                net_pnl=m.net_pnl,
                trades_count=m.trades_count,
                win_rate_pct=m.win_rate_pct,
            )
            for m in raw_result.monthly_pnl
        ]

        result = BacktestResult(
            initial_capital=raw_result.initial_capital,
            final_equity=raw_result.final_equity,
            total_net_pnl=raw_result.total_net_pnl,
            net_roi_percent=raw_result.net_roi_percent,
            total_trades=raw_result.total_trades,
            winning_trades=raw_result.winning_trades,
            losing_trades=raw_result.losing_trades,
            win_rate_percent=raw_result.win_rate_percent,
            profit_factor=raw_result.profit_factor,
            sharpe_ratio=raw_result.sharpe_ratio,
            sortino_ratio=raw_result.sortino_ratio,
            max_drawdown_amount=raw_result.max_drawdown_amount,
            max_drawdown_percent=raw_result.max_drawdown_percent,
            max_consecutive_wins=raw_result.max_consecutive_wins,
            max_consecutive_losses=raw_result.max_consecutive_losses,
            equity_curve=equity_curve,
            monthly_pnl=monthly_pnl,
            trades=trades,
        )

        self._history.insert(0, result)
        self._history = self._history[:10]  # Keep last 10 runs

        return result

    def get_history(self) -> list[BacktestResult]:
        """Retrieve recent backtest runs."""
        return self._history


backtest_service = BacktestService()
