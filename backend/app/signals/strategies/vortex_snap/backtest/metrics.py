"""
Institutional Performance & Research Metrics (§35).

Computes comprehensive risk-adjusted performance metrics, drawdown analysis,
friction drag, and exit attribution.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class BacktestTradeRecord:
    """Record of a single simulated trade execution."""
    trade_id: int
    instrument: str
    direction: str  # "LONG_CALL" or "LONG_PUT"
    direction_sign: int  # +1 or -1
    entry_time_ms: int
    exit_time_ms: int
    entry_price: float
    exit_price: float
    quantity: int
    gross_pnl_points: float
    gross_pnl_rupees: float
    net_pnl_rupees: float
    friction_rupees: float
    exit_reason: str  # "TARGET_1", "TARGET_2", "STOP_LOSS", "TIME_DECAY", "PRESSURE_COLLAPSE", "SQUARE_OFF"
    holding_bars: int
    holding_minutes: float
    signal_confidence: float
    reason_codes: List[str] = field(default_factory=list)


@dataclass
class BacktestMetricsSummary:
    """Comprehensive institutional backtesting metrics (§35)."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    scratch_trades: int
    win_rate_pct: float
    loss_rate_pct: float
    gross_pnl_rupees: float
    net_pnl_rupees: float
    total_friction_rupees: float
    cost_drag_pct: float
    profit_factor: float
    gross_expectancy_points: float
    net_expectancy_points: float
    average_win_rupees: float
    average_loss_rupees: float
    win_loss_ratio: float
    max_drawdown_rupees: float
    max_drawdown_pct: float
    max_drawdown_duration_bars: int
    annualized_sharpe: float
    annualized_sortino: float
    calmar_ratio: float
    recovery_factor: float
    avg_holding_minutes: float
    median_holding_minutes: float
    p95_holding_minutes: float
    exit_reasons_breakdown: Dict[str, int]
    reason_code_win_rates: Dict[str, Dict[str, Any]]
    equity_curve: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "scratch_trades": self.scratch_trades,
            "win_rate_pct": round(self.win_rate_pct, 2),
            "loss_rate_pct": round(self.loss_rate_pct, 2),
            "gross_pnl_rupees": round(self.gross_pnl_rupees, 2),
            "net_pnl_rupees": round(self.net_pnl_rupees, 2),
            "total_friction_rupees": round(self.total_friction_rupees, 2),
            "cost_drag_pct": round(self.cost_drag_pct, 2),
            "profit_factor": round(self.profit_factor, 2),
            "gross_expectancy_points": round(self.gross_expectancy_points, 2),
            "net_expectancy_points": round(self.net_expectancy_points, 2),
            "average_win_rupees": round(self.average_win_rupees, 2),
            "average_loss_rupees": round(self.average_loss_rupees, 2),
            "win_loss_ratio": round(self.win_loss_ratio, 2),
            "max_drawdown_rupees": round(self.max_drawdown_rupees, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "max_drawdown_duration_bars": self.max_drawdown_duration_bars,
            "annualized_sharpe": round(self.annualized_sharpe, 2),
            "annualized_sortino": round(self.annualized_sortino, 2),
            "calmar_ratio": round(self.calmar_ratio, 2),
            "recovery_factor": round(self.recovery_factor, 2),
            "avg_holding_minutes": round(self.avg_holding_minutes, 1),
            "median_holding_minutes": round(self.median_holding_minutes, 1),
            "p95_holding_minutes": round(self.p95_holding_minutes, 1),
            "exit_reasons_breakdown": self.exit_reasons_breakdown,
            "reason_code_win_rates": self.reason_code_win_rates,
        }


def calculate_metrics(
    trades: List[BacktestTradeRecord],
    initial_capital: float = 500000.0,
    annual_trading_days: int = 250,
) -> BacktestMetricsSummary:
    """Calculates full institutional metrics from a list of completed trades."""
    if not trades:
        return BacktestMetricsSummary(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            scratch_trades=0,
            win_rate_pct=0.0,
            loss_rate_pct=0.0,
            gross_pnl_rupees=0.0,
            net_pnl_rupees=0.0,
            total_friction_rupees=0.0,
            cost_drag_pct=0.0,
            profit_factor=0.0,
            gross_expectancy_points=0.0,
            net_expectancy_points=0.0,
            average_win_rupees=0.0,
            average_loss_rupees=0.0,
            win_loss_ratio=0.0,
            max_drawdown_rupees=0.0,
            max_drawdown_pct=0.0,
            max_drawdown_duration_bars=0,
            annualized_sharpe=0.0,
            annualized_sortino=0.0,
            calmar_ratio=0.0,
            recovery_factor=0.0,
            avg_holding_minutes=0.0,
            median_holding_minutes=0.0,
            p95_holding_minutes=0.0,
            exit_reasons_breakdown={},
            reason_code_win_rates={},
            equity_curve=[initial_capital],
        )

    n_trades = len(trades)
    winning = [t for t in trades if t.net_pnl_rupees > 0]
    losing = [t for t in trades if t.net_pnl_rupees < 0]
    scratch = [t for t in trades if t.net_pnl_rupees == 0]

    win_rate = (len(winning) / n_trades) * 100.0
    loss_rate = (len(losing) / n_trades) * 100.0

    gross_pnl = sum(t.gross_pnl_rupees for t in trades)
    net_pnl = sum(t.net_pnl_rupees for t in trades)
    total_friction = sum(t.friction_rupees for t in trades)

    cost_drag = (total_friction / gross_pnl * 100.0) if gross_pnl > 0 else 100.0

    gross_win_sum = sum(t.gross_pnl_rupees for t in winning)
    gross_loss_sum = abs(sum(t.gross_pnl_rupees for t in losing))
    profit_factor = (gross_win_sum / gross_loss_sum) if gross_loss_sum > 0 else (99.0 if gross_win_sum > 0 else 0.0)

    gross_expectancy_pts = sum(t.gross_pnl_points for t in trades) / n_trades
    net_expectancy_pts = sum(t.net_pnl_rupees / (t.quantity or 1) for t in trades) / n_trades

    avg_win = (sum(t.net_pnl_rupees for t in winning) / len(winning)) if winning else 0.0
    avg_loss = (abs(sum(t.net_pnl_rupees for t in losing)) / len(losing)) if losing else 0.0
    win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0

    # Drawdown & Equity curve calculation
    equity = initial_capital
    peak = initial_capital
    max_dd = 0.0
    max_dd_pct = 0.0
    equity_curve = [initial_capital]
    dd_duration = 0
    max_dd_duration = 0

    net_returns: List[float] = []

    for t in trades:
        equity += t.net_pnl_rupees
        equity_curve.append(round(equity, 2))
        net_returns.append(t.net_pnl_rupees / initial_capital)

        if equity > peak:
            peak = equity
            dd_duration = 0
        else:
            current_dd = peak - equity
            current_dd_pct = (current_dd / peak) * 100.0 if peak > 0 else 0.0
            if current_dd > max_dd:
                max_dd = current_dd
            if current_dd_pct > max_dd_pct:
                max_dd_pct = current_dd_pct
            dd_duration += t.holding_bars
            if dd_duration > max_dd_duration:
                max_dd_duration = dd_duration

    # Sharpe & Sortino (annualized based on 250 trading days, assuming ~5 trades/day = 1250 trades/year)
    mean_ret = sum(net_returns) / n_trades if n_trades > 0 else 0.0
    var_ret = sum((r - mean_ret) ** 2 for r in net_returns) / (n_trades - 1) if n_trades > 1 else 0.0
    std_ret = math.sqrt(var_ret) if var_ret > 0 else 0.0

    downside_returns = [min(r, 0.0) for r in net_returns]
    downside_var = sum(r ** 2 for r in downside_returns) / (n_trades - 1) if n_trades > 1 else 0.0
    downside_std = math.sqrt(downside_var) if downside_var > 0 else 0.0

    # Annualization factor (assume 250 trading days, min 100 periods)
    ann_factor = math.sqrt(250 * 5)
    sharpe = (mean_ret / std_ret * ann_factor) if std_ret > 0 else 0.0
    sortino = (mean_ret / downside_std * ann_factor) if downside_std > 0 else 0.0

    # Calmar & Recovery Factor
    ann_return_pct = (net_pnl / initial_capital) * 100.0
    calmar = (ann_return_pct / max_dd_pct) if max_dd_pct > 0 else 0.0
    recovery_factor = (net_pnl / max_dd) if max_dd > 0 else 0.0

    # Holding times
    durations = sorted(t.holding_minutes for t in trades)
    avg_dur = sum(durations) / n_trades
    median_dur = durations[n_trades // 2]
    p95_dur = durations[int(n_trades * 0.95)]

    # Exit reason breakdown
    exit_breakdown: Dict[str, int] = {}
    for t in trades:
        exit_breakdown[t.exit_reason] = exit_breakdown.get(t.exit_reason, 0) + 1

    # Reason code breakdown
    reason_stats: Dict[str, Dict[str, Any]] = {}
    for t in trades:
        is_win = t.net_pnl_rupees > 0
        for rc in t.reason_codes:
            if rc not in reason_stats:
                reason_stats[rc] = {"count": 0, "wins": 0, "win_rate": 0.0, "net_pnl": 0.0}
            reason_stats[rc]["count"] += 1
            if is_win:
                reason_stats[rc]["wins"] += 1
            reason_stats[rc]["net_pnl"] += t.net_pnl_rupees

    for rc, st in reason_stats.items():
        st["win_rate"] = round((st["wins"] / st["count"]) * 100.0, 1)
        st["net_pnl"] = round(st["net_pnl"], 2)

    return BacktestMetricsSummary(
        total_trades=n_trades,
        winning_trades=len(winning),
        losing_trades=len(losing),
        scratch_trades=len(scratch),
        win_rate_pct=win_rate,
        loss_rate_pct=loss_rate,
        gross_pnl_rupees=gross_pnl,
        net_pnl_rupees=net_pnl,
        total_friction_rupees=total_friction,
        cost_drag_pct=cost_drag,
        profit_factor=profit_factor,
        gross_expectancy_points=gross_expectancy_pts,
        net_expectancy_points=net_expectancy_pts,
        average_win_rupees=avg_win,
        average_loss_rupees=avg_loss,
        win_loss_ratio=win_loss_ratio,
        max_drawdown_rupees=max_dd,
        max_drawdown_pct=max_dd_pct,
        max_drawdown_duration_bars=max_dd_duration,
        annualized_sharpe=sharpe,
        annualized_sortino=sortino,
        calmar_ratio=calmar,
        recovery_factor=recovery_factor,
        avg_holding_minutes=avg_dur,
        median_holding_minutes=median_dur,
        p95_holding_minutes=p95_dur,
        exit_reasons_breakdown=exit_breakdown,
        reason_code_win_rates=reason_stats,
        equity_curve=equity_curve,
    )
