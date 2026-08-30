import math
import random
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from app.quant.costs import calculate_option_costs


class SimulatedTrade(NamedTuple):
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
    status: str  # TARGET_HIT, STOP_LOSS_HIT, EXPIRY_EXIT


class EquityPointData(NamedTuple):
    timestamp: str
    equity: float
    drawdown_pct: float
    net_pnl: float


class MonthlyPnlData(NamedTuple):
    month_year: str
    net_pnl: float
    trades_count: int
    win_rate_pct: float


class BacktestEngineResult(NamedTuple):
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
    equity_curve: list[EquityPointData]
    monthly_pnl: list[MonthlyPnlData]
    trades: list[SimulatedTrade]


def run_strategy_backtest(
    strategy_id: str = "short_straddle",
    underlying: str = "NIFTY",
    initial_capital: float = 500000.0,
    num_days: int = 60,
    stop_loss_pct: float = 25.0,
    target_pct: float = 50.0,
    slippage_pct: float = 0.001,
    include_costs: bool = True,
    seed: int = 42,
) -> BacktestEngineResult:
    """Run quantitative multi-period backtest simulation with Indian F&O costs and risk metrics."""
    rng = random.Random(seed)
    today = datetime.now(timezone.utc).date()
    lot_size = 25 if "BANK" in underlying else 65 if "FIN" in underlying else 75
    quantity = lot_size * 2  # 2 lots default

    current_equity = initial_capital
    peak_equity = initial_capital
    max_drawdown_amount = 0.0
    max_drawdown_percent = 0.0

    trades: list[SimulatedTrade] = []
    equity_curve: list[EquityPointData] = []
    monthly_map: dict[str, list[float]] = {}

    gross_profits = 0.0
    gross_losses = 0.0
    daily_returns: list[float] = []

    consecutive_wins = 0
    consecutive_losses = 0
    max_cons_wins = 0
    max_cons_losses = 0

    base_spot = 24800.0 if "NIFTY" in underlying and "BANK" not in underlying else 52000.0 if "BANK" in underlying else 23500.0

    for i in range(num_days, 0, -1):
        trade_date = today - timedelta(days=i)
        date_str = trade_date.isoformat()
        month_str = trade_date.strftime("%Y-%m")

        # Simulate strategy outcome
        if strategy_id == "short_straddle":
            # 9:20 Intraday Short Straddle (high win rate ~65%, defined theta decay)
            strat_name = "9:20 Intraday Short Straddle"
            legs_desc = f"Sell 1 ATM CE + Sell 1 ATM PE ({quantity} qty)"
            combined_premium = round(base_spot * 0.015, 2)  # ~1.5% premium
            outcome_roll = rng.random()

            if outcome_roll < 0.65:  # Profitable session
                decay_fraction = rng.uniform(0.3, 0.6)
                exit_price = round(combined_premium * (1.0 - decay_fraction), 2)
                status = "TARGET_HIT" if decay_fraction >= (target_pct / 100.0) else "EXPIRY_EXIT"
            else:  # Stop loss triggered on trending day
                exit_price = round(combined_premium * (1.0 + (stop_loss_pct / 100.0)), 2)
                status = "STOP_LOSS_HIT"

            entry_price = combined_premium
            gross = (entry_price - exit_price) * quantity

            # Turnover
            buy_turnover = exit_price * quantity
            sell_turnover = entry_price * quantity
            num_orders = 4  # 2 entry + 2 exit

        elif strategy_id == "iron_condor":
            strat_name = "Weekly Iron Condor"
            legs_desc = f"Sell OTM CE/PE, Buy Wing CE/PE ({quantity} qty)"
            net_credit = round(base_spot * 0.008, 2)
            outcome_roll = rng.random()

            if outcome_roll < 0.72:  # High win rate
                exit_price = round(net_credit * rng.uniform(0.1, 0.4), 2)
                status = "EXPIRY_EXIT"
            else:
                exit_price = round(net_credit * (1.0 + (stop_loss_pct / 100.0)), 2)
                status = "STOP_LOSS_HIT"

            entry_price = net_credit
            gross = (entry_price - exit_price) * quantity
            buy_turnover = exit_price * quantity
            sell_turnover = entry_price * quantity
            num_orders = 8

        else:  # Momentum Breakout / Long Straddle
            strat_name = "ATM Straddle Volatility Breakout"
            legs_desc = f"Buy ATM CE + Buy ATM PE on Breakout ({quantity} qty)"
            entry_price = round(base_spot * 0.012, 2)
            outcome_roll = rng.random()

            if outcome_roll < 0.42:  # Lower win rate, high payoff
                exit_price = round(entry_price * rng.uniform(1.8, 2.5), 2)
                status = "TARGET_HIT"
            else:
                exit_price = round(entry_price * 0.65, 2)
                status = "STOP_LOSS_HIT"

            gross = (exit_price - entry_price) * quantity
            buy_turnover = entry_price * quantity
            sell_turnover = exit_price * quantity
            num_orders = 4

        # Calculate Indian F&O costs
        costs = calculate_option_costs(
            buy_turnover=buy_turnover,
            sell_turnover=sell_turnover,
            num_orders=num_orders,
            slippage_pct=slippage_pct if include_costs else 0.0,
        )
        total_charges = costs.total_cost if include_costs else 0.0
        net = round(gross - total_charges, 2)

        # Update running performance
        current_equity = round(current_equity + net, 2)
        if current_equity > peak_equity:
            peak_equity = current_equity

        dd_amount = peak_equity - current_equity
        dd_pct = round((dd_amount / peak_equity) * 100.0, 2) if peak_equity > 0 else 0.0

        if dd_amount > max_drawdown_amount:
            max_drawdown_amount = round(dd_amount, 2)
        if dd_pct > max_drawdown_percent:
            max_drawdown_percent = dd_pct

        ret = net / initial_capital
        daily_returns.append(ret)

        if net > 0:
            gross_profits += net
            consecutive_wins += 1
            consecutive_losses = 0
            if consecutive_wins > max_cons_wins:
                max_cons_wins = consecutive_wins
        else:
            gross_losses += abs(net)
            consecutive_losses += 1
            consecutive_wins = 0
            if consecutive_losses > max_cons_losses:
                max_cons_losses = consecutive_losses

        # Append trade
        trade = SimulatedTrade(
            trade_id=f"TRD-{i:03d}",
            entry_date=date_str,
            exit_date=date_str,
            strategy_name=strat_name,
            underlying=underlying,
            legs_description=legs_desc,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            gross_pnl=round(gross, 2),
            total_charges=round(total_charges, 2),
            net_pnl=net,
            status=status,
        )
        trades.append(trade)

        equity_curve.append(EquityPointData(
            timestamp=date_str,
            equity=current_equity,
            drawdown_pct=dd_pct,
            net_pnl=net,
        ))

        if month_str not in monthly_map:
            monthly_map[month_str] = []
        monthly_map[month_str].append(net)

    # Performance Ratios
    total_trades = len(trades)
    winning_trades = sum(1 for t in trades if t.net_pnl > 0)
    losing_trades = total_trades - winning_trades
    win_rate = round((winning_trades / total_trades) * 100.0, 2) if total_trades > 0 else 0.0
    profit_factor = round(gross_profits / gross_losses, 2) if gross_losses > 0 else 99.9

    # Annualized Sharpe & Sortino (assuming 6.75% risk-free rate)
    rf_daily = 0.0675 / 252.0
    excess_returns = [r - rf_daily for r in daily_returns]
    mean_excess = sum(excess_returns) / len(excess_returns) if excess_returns else 0.0
    var_returns = sum((r - mean_excess) ** 2 for r in excess_returns) / len(excess_returns) if len(excess_returns) > 1 else 1e-4
    std_returns = math.sqrt(var_returns)

    sharpe = round((mean_excess / std_returns) * math.sqrt(252), 2) if std_returns > 1e-6 else 0.0

    # Sortino (Downside deviation only)
    downside_excess = [min(0.0, r) for r in excess_returns]
    downside_var = sum(r ** 2 for r in downside_excess) / len(downside_excess) if downside_excess else 1e-4
    downside_std = math.sqrt(downside_var)
    sortino = round((mean_excess / downside_std) * math.sqrt(252), 2) if downside_std > 1e-6 else 0.0

    total_net_pnl = round(current_equity - initial_capital, 2)
    net_roi = round((total_net_pnl / initial_capital) * 100.0, 2)

    # Monthly breakdown
    monthly_pnl: list[MonthlyPnlData] = []
    for m, pnls in monthly_map.items():
        m_net = round(sum(pnls), 2)
        m_wins = sum(1 for p in pnls if p > 0)
        m_win_rate = round((m_wins / len(pnls)) * 100.0, 2) if pnls else 0.0
        monthly_pnl.append(MonthlyPnlData(
            month_year=m,
            net_pnl=m_net,
            trades_count=len(pnls),
            win_rate_pct=m_win_rate,
        ))

    return BacktestEngineResult(
        initial_capital=initial_capital,
        final_equity=current_equity,
        total_net_pnl=total_net_pnl,
        net_roi_percent=net_roi,
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate_percent=win_rate,
        profit_factor=profit_factor,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown_amount=max_drawdown_amount,
        max_drawdown_percent=max_drawdown_percent,
        max_consecutive_wins=max_cons_wins,
        max_consecutive_losses=max_cons_losses,
        equity_curve=equity_curve,
        monthly_pnl=monthly_pnl,
        trades=trades,
    )
