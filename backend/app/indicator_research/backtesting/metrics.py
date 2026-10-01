"""Performance, risk and trade statistics.

Everything here is a pure function over trades and an equity curve, so a metric
can be unit-tested against a hand-computed fixture rather than trusted.

Honesty rules baked in:

- Gross and net are always both present, and ``cost_drag_pct`` is the literal
  difference, not a footnote.
- Ratio metrics derived from intraday bars (Sharpe, Sortino) are annualised with
  a stated factor and carry ``annualization_assumption`` next to them. Bar
  returns understate overnight risk, so the annualised figure is optimistic by
  construction and says so.
- Any metric that cannot be computed (single trade, zero variance, no losses)
  is reported as ``None`` with an ``undefined_metrics`` list rather than as a
  misleading number such as an infinite profit factor.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from app.indicator_research.backtesting.models import EquityPoint, Trade

#: NSE regular session is 09:15-15:30 = 375 minutes.
SESSION_MINUTES = 375.0
TRADING_DAYS_PER_YEAR = 250.0

_TIMEFRAME_MINUTES: dict[str, float] = {
    "1m": 1.0,
    "2m": 2.0,
    "3m": 3.0,
    "5m": 5.0,
    "10m": 10.0,
    "15m": 15.0,
    "30m": 30.0,
    "60m": 60.0,
    "1h": 60.0,
    "1d": SESSION_MINUTES,
    "1D": SESSION_MINUTES,
}


def bars_per_year(timeframe: str) -> float:
    """Approximate bars in one trading year for a timeframe.

    Used only to annualise ratio metrics. Unknown timeframes fall back to the
    daily rate (250), which is the conservative choice: it under-annualises a
    misunderstood intraday series instead of inventing a large factor.
    """
    minutes = _TIMEFRAME_MINUTES.get(timeframe) or _TIMEFRAME_MINUTES.get(timeframe.lower())
    if not minutes:
        return TRADING_DAYS_PER_YEAR
    return (SESSION_MINUTES / minutes) * TRADING_DAYS_PER_YEAR


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _stdev(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def max_drawdown(equity: Sequence[float]) -> tuple[float, float, int, int]:
    """Return ``(max_dd_pct, max_dd_abs, peak_index, trough_index)``.

    Percentage drawdown is measured from the running peak, which is what a
    trader experiences; a drawdown measured from the initial capital would
    understate a loss taken after a large gain.
    """
    peak = equity[0] if equity else 0.0
    peak_index = 0
    best_dd_pct = 0.0
    best_dd_abs = 0.0
    best_peak = 0
    best_trough = 0
    for i, value in enumerate(equity):
        if value > peak:
            peak = value
            peak_index = i
        if peak > 0:
            dd_pct = (peak - value) / peak
            if dd_pct > best_dd_pct:
                best_dd_pct = dd_pct
                best_dd_abs = peak - value
                best_peak = peak_index
                best_trough = i
    return best_dd_pct, best_dd_abs, best_peak, best_trough


def _streaks(trades: Sequence[Trade]) -> tuple[int, int]:
    """Longest run of consecutive wins and of consecutive losses."""
    best_win = best_loss = 0
    run = 0
    for trade in trades:
        if trade.net_pnl > 0:
            run = run + 1 if run >= 0 else 1
            best_win = max(best_win, run)
        elif trade.net_pnl < 0:
            run = run - 1 if run <= 0 else -1
            best_loss = max(best_loss, -run)
        else:
            run = 0
    return best_win, best_loss


def compute_metrics(
    trades: Sequence[Trade],
    equity_curve: Sequence[EquityPoint],
    *,
    initial_capital: float,
    timeframe: str,
    total_bars: int,
) -> dict[str, Any]:
    """Full metric block for one backtest run."""
    undefined: list[str] = []
    final_equity = equity_curve[-1].equity if equity_curve else initial_capital
    net_profit = final_equity - initial_capital

    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl < 0]
    flats = [t for t in trades if t.net_pnl == 0]

    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = sum(-t.net_pnl for t in losses)
    total_costs = sum(t.costs for t in trades)
    gross_profit_before_costs = sum(t.gross_pnl for t in trades)

    profit_factor: float | None
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = None
        undefined.append("profit_factor (no losing trades — infinite, not reported)")
    else:
        profit_factor = None
        undefined.append("profit_factor (no closed P&L)")

    avg_win = _mean([t.net_pnl for t in wins])
    avg_loss = _mean([-t.net_pnl for t in losses])
    payoff: float | None = None
    if avg_win is not None and avg_loss:
        payoff = avg_win / avg_loss
    elif avg_win is not None and not losses:
        undefined.append("payoff_ratio (no losing trades)")

    expectancy = _mean([t.net_pnl for t in trades])

    exposure_pct = None
    if total_bars > 0 and trades:
        bars_in_market = sum(t.bars_held for t in trades)
        exposure_pct = 100.0 * min(bars_in_market, total_bars) / total_bars

    # ── risk-adjusted ratios from the per-bar equity curve ────────────────
    bar_returns: list[float] = []
    for prev, curr in zip(equity_curve, equity_curve[1:]):
        if prev.equity > 0:
            bar_returns.append(curr.equity / prev.equity - 1.0)
    annual_factor = bars_per_year(timeframe)
    mean_ret = _mean(bar_returns)
    sd = _stdev(bar_returns)
    sharpe: float | None = None
    if mean_ret is not None and sd and sd > 0:
        sharpe = (mean_ret / sd) * math.sqrt(annual_factor)
    elif sd == 0:
        undefined.append("sharpe (zero equity variance)")

    downside = [r for r in bar_returns if r < 0]
    downside_sd = _stdev(downside) if len(downside) >= 2 else None
    sortino: float | None = None
    if mean_ret is not None and downside_sd and downside_sd > 0:
        sortino = (mean_ret / downside_sd) * math.sqrt(annual_factor)
    elif not downside:
        undefined.append("sortino (no negative bar returns)")

    dd_pct, dd_abs, dd_peak, dd_trough = max_drawdown([p.equity for p in equity_curve])
    dd_duration = max(0, dd_trough - dd_peak)

    annualized_return: float | None = None
    if total_bars > 0 and initial_capital > 0 and final_equity > 0:
        years = total_bars / annual_factor if annual_factor else 0.0
        if years > 0:
            annualized_return = ((final_equity / initial_capital) ** (1.0 / years) - 1.0) * 100.0

    calmar: float | None = None
    if annualized_return is not None and dd_pct > 0:
        calmar = annualized_return / (dd_pct * 100.0)

    best_win_streak, best_loss_streak = _streaks(trades)
    bars_held = [t.bars_held for t in trades]

    metrics: dict[str, Any] = {
        "n_trades": len(trades),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "n_breakeven": len(flats),
        "win_rate_pct": _round(100.0 * len(wins) / len(trades), 2) if trades else None,
        "initial_capital": _round(initial_capital, 2),
        "final_equity": _round(final_equity, 2),
        "net_profit": _round(net_profit, 2),
        "total_return_pct": _round(100.0 * net_profit / initial_capital, 4) if initial_capital else None,
        "gross_profit_before_costs": _round(gross_profit_before_costs, 2),
        "total_costs": _round(total_costs, 2),
        "cost_drag_pct": (
            _round(100.0 * total_costs / initial_capital, 4) if initial_capital else None
        ),
        "gross_profit": _round(gross_profit, 2),
        "gross_loss": _round(gross_loss, 2),
        "profit_factor": _round(profit_factor, 4),
        "expectancy_per_trade": _round(expectancy, 2),
        "avg_win": _round(avg_win, 2),
        "avg_loss": _round(avg_loss, 2),
        "payoff_ratio": _round(payoff, 4),
        "largest_win": _round(max((t.net_pnl for t in trades), default=0.0), 2),
        "largest_loss": _round(min((t.net_pnl for t in trades), default=0.0), 2),
        "avg_bars_held": _round(_mean([float(b) for b in bars_held]), 2),
        "median_bars_held": _round(_median([float(b) for b in bars_held]), 2),
        "exposure_pct": _round(exposure_pct, 2),
        "max_drawdown_pct": _round(100.0 * dd_pct, 4),
        "max_drawdown_abs": _round(dd_abs, 2),
        "max_drawdown_duration_bars": dd_duration,
        "sharpe_annualized": _round(sharpe, 4),
        "sortino_annualized": _round(sortino, 4),
        "annualized_return_pct": _round(annualized_return, 4),
        "calmar": _round(calmar, 4),
        "max_consecutive_wins": best_win_streak,
        "max_consecutive_losses": best_loss_streak,
        "avg_mae_pct": _round(_mean([t.mae_pct for t in trades]), 4),
        "avg_mfe_pct": _round(_mean([t.mfe_pct for t in trades]), 4),
        "mfe_mae_ratio": None,
        "long_trades": sum(1 for t in trades if t.side == "LONG"),
        "short_trades": sum(1 for t in trades if t.side == "SHORT"),
        "bars": total_bars,
        "undefined_metrics": undefined,
        "annualization_assumption": {
            "bars_per_year": round(annual_factor, 2),
            "session_minutes": SESSION_MINUTES,
            "trading_days_per_year": TRADING_DAYS_PER_YEAR,
            "note": (
                "Bar returns exclude overnight and weekend gaps, so annualised "
                "ratios are optimistic for intraday timeframes."
            ),
        },
    }

    mae_mean = metrics["avg_mae_pct"]
    mfe_mean = metrics["avg_mfe_pct"]
    if mae_mean and mfe_mean:
        metrics["mfe_mae_ratio"] = _round(mfe_mean / mae_mean, 4)
    elif not mae_mean:
        undefined.append("mfe_mae_ratio (no adverse excursion recorded)")
    return metrics


def group_metrics(
    trades: Sequence[Trade],
    key: str,
    equity_lookup: dict[int, float],
) -> dict[str, dict[str, Any]]:
    """Aggregate trade statistics by a trade attribute.

    Used for regime and time-of-day analysis. Each bucket reports its own trade
    count so a 3-trade "bucket" cannot be read as a finding.
    """
    buckets: dict[str, list[Trade]] = {}
    for trade in trades:
        name = getattr(trade, key, None) or "UNKNOWN"
        buckets.setdefault(str(name), []).append(trade)

    out: dict[str, dict[str, Any]] = {}
    for name, group in buckets.items():
        wins = [t for t in group if t.net_pnl > 0]
        losses = [t for t in group if t.net_pnl < 0]
        gross_profit = sum(t.net_pnl for t in wins)
        gross_loss = sum(-t.net_pnl for t in losses)
        out[name] = {
            "n_trades": len(group),
            "win_rate_pct": _round(100.0 * len(wins) / len(group), 2) if group else None,
            "net_pnl": _round(sum(t.net_pnl for t in group), 2),
            "avg_net_pnl": _round(_mean([t.net_pnl for t in group]), 2),
            "profit_factor": _round(gross_profit / gross_loss, 4) if gross_loss > 0 else None,
            "avg_bars_held": _round(_mean([float(t.bars_held) for t in group]), 2),
            "total_costs": _round(sum(t.costs for t in group), 2),
            "avg_mae_pct": _round(_mean([t.mae_pct for t in group]), 4),
            "avg_mfe_pct": _round(_mean([t.mfe_pct for t in group]), 4),
            "low_sample": len(group) < 20,
        }
    return dict(sorted(out.items()))


def forward_return_stats(
    returns: Sequence[float],
) -> dict[str, Any]:
    """Descriptive statistics for a list of forward returns (percent).

    Deliberately descriptive only: a mean, a spread and a t-statistic against
    zero. No accuracy claim is made, because "the mean forward return after a
    signal was positive" is evidence about a sample, not a probability about
    the next signal.
    """
    n = len(returns)
    if n == 0:
        return {
            "n": 0,
            "mean_pct": None,
            "median_pct": None,
            "stdev_pct": None,
            "t_stat": None,
            "p_value_two_sided": None,
            "positive_rate_pct": None,
            "is_significant_5pct": False,
        }
    mean = sum(returns) / n
    sd = _stdev(returns)
    t_stat = None
    p_value = None
    if sd and sd > 0 and n >= 2:
        t_stat = mean / (sd / math.sqrt(n))
        p_value = _two_sided_p(t_stat, n - 1)
    positives = sum(1 for r in returns if r > 0)
    return {
        "n": n,
        "mean_pct": _round(mean, 4),
        "median_pct": _round(_median(returns), 4),
        "stdev_pct": _round(sd, 4),
        "t_stat": _round(t_stat, 4),
        "p_value_two_sided": _round(p_value, 6),
        "positive_rate_pct": _round(100.0 * positives / n, 2),
        "is_significant_5pct": bool(p_value is not None and p_value < 0.05),
        "low_sample": n < 30,
    }


def _two_sided_p(t_stat: float, df: int) -> float | None:
    """Two-sided p-value for a t statistic.

    Uses scipy when available and a normal approximation otherwise. Student-t
    with large df converges to the normal, so the fallback is close for the
    sample sizes this module accepts, and the approximation is disclosed via
    the caller's metric provenance rather than hidden.
    """
    try:  # pragma: no cover - environment dependent
        from scipy import stats  # type: ignore

        return float(2.0 * stats.t.sf(abs(t_stat), df))
    except Exception:
        pass
    # Normal approximation (Abramowitz & Stegun 26.2.17).
    x = abs(t_stat) / math.sqrt(2.0)
    t = 1.0 / (1.0 + 0.3275911 * x)
    erf = 1.0 - (
        (0.254829592 * t - 0.284496736 * t**2 + 1.421413741 * t**3 - 1.453152027 * t**4 + 1.061405429 * t**5)
        * math.exp(-x * x)
    )
    return float(max(0.0, min(1.0, 1.0 - erf)))


def iter_trade_returns(trades: Iterable[Trade]) -> list[float]:
    return [t.return_pct for t in trades]


__all__ = [
    "SESSION_MINUTES",
    "TRADING_DAYS_PER_YEAR",
    "bars_per_year",
    "compute_metrics",
    "forward_return_stats",
    "group_metrics",
    "iter_trade_returns",
    "max_drawdown",
]
