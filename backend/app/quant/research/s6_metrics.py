"""S6 Research Metrics & Performance Diagnostics (S6SPEC_v1.3).

Computes:
- Net & Gross Expectancy in cost-inclusive R
- Profit Factor and Max Drawdown in R
- MFE and MAE diagnostics (in R and points)
- Statutory Cost and Slippage Drag in R
- Full Event Conversion Funnel (Compression -> Breakout -> Failure -> Candidate -> Trade)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import numpy as np

from app.quant.execution.s6_simulator import S6Trade


@dataclass(frozen=True)
class S6MetricsReport:
    instrument: str
    track: str
    variant: str
    compression_episodes: int
    raw_breakouts: int
    failures: int
    total_candidates: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    gross_expectancy_R: float
    net_expectancy_R: float
    profit_factor: float
    max_drawdown_R: float
    average_MFE_R: float
    average_MAE_R: float
    cost_drag_R: float
    slippage_drag_R: float
    compression_to_breakout_rate: float
    breakout_to_trade_rate: float
    breakout_to_failure_rate: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instrument": self.instrument,
            "track": self.track,
            "variant": self.variant,
            "compression_episodes": self.compression_episodes,
            "raw_breakouts": self.raw_breakouts,
            "failures": self.failures,
            "total_candidates": self.total_candidates,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 4),
            "gross_expectancy_R": round(self.gross_expectancy_R, 4),
            "net_expectancy_R": round(self.net_expectancy_R, 4),
            "profit_factor": round(self.profit_factor, 2) if not math.isinf(self.profit_factor) else 999.0,
            "max_drawdown_R": round(self.max_drawdown_R, 4),
            "average_MFE_R": round(self.average_MFE_R, 4),
            "average_MAE_R": round(self.average_MAE_R, 4),
            "cost_drag_R": round(self.cost_drag_R, 4),
            "slippage_drag_R": round(self.slippage_drag_R, 4),
            "compression_to_breakout_rate": round(self.compression_to_breakout_rate, 4),
            "breakout_to_trade_rate": round(self.breakout_to_trade_rate, 4),
            "breakout_to_failure_rate": round(self.breakout_to_failure_rate, 4),
        }


def calculate_s6_metrics(
    trades: List[S6Trade],
    total_candidates: int,
    compression_count: int,
    breakout_count: int,
    failure_count: int,
    instrument: str = "NIFTY",
    track: str = "S6A_T1",
    variant: str = "S6-A",
) -> S6MetricsReport:
    """Calculates all canonical S6 research metrics from simulated trades and event counts."""
    n_trades = len(trades)
    
    comp_to_bo = (breakout_count / max(1, compression_count)) if compression_count > 0 else 0.0
    bo_to_trade = (n_trades / max(1, breakout_count)) if breakout_count > 0 else 0.0
    bo_to_fail = (failure_count / max(1, breakout_count)) if breakout_count > 0 else 0.0

    if n_trades == 0:
        return S6MetricsReport(
            instrument=instrument,
            track=track,
            variant=variant,
            compression_episodes=compression_count,
            raw_breakouts=breakout_count,
            failures=failure_count,
            total_candidates=total_candidates,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            gross_expectancy_R=0.0,
            net_expectancy_R=0.0,
            profit_factor=0.0,
            max_drawdown_R=0.0,
            average_MFE_R=0.0,
            average_MAE_R=0.0,
            cost_drag_R=0.0,
            slippage_drag_R=0.0,
            compression_to_breakout_rate=comp_to_bo,
            breakout_to_trade_rate=bo_to_trade,
            breakout_to_failure_rate=bo_to_fail,
        )

    net_Rs = np.array([t.net_R for t in trades], dtype=np.float64)
    gross_Rs = np.array([t.gross_R for t in trades], dtype=np.float64)
    mfes = np.array([t.mfe_R for t in trades], dtype=np.float64)
    maes = np.array([t.mae_R for t in trades], dtype=np.float64)
    cost_drags = np.array([t.cost_drag_R for t in trades], dtype=np.float64)
    slip_drags = np.array([t.slippage_drag_R for t in trades], dtype=np.float64)

    wins = net_Rs[net_Rs > 0]
    losses = net_Rs[net_Rs <= 0]
    n_wins = len(wins)
    n_losses = len(losses)
    win_rate = n_wins / n_trades

    gross_exp = float(gross_Rs.mean())
    net_exp = float(net_Rs.mean())

    total_win_R = float(wins.sum()) if n_wins > 0 else 0.0
    total_loss_R = float(abs(losses.sum())) if n_losses > 0 else 0.0

    if total_loss_R > 1e-6:
        pf = total_win_R / total_loss_R
    elif total_win_R > 0:
        pf = 999.0
    else:
        pf = 0.0

    # Max Drawdown in R
    cum_R = np.cumsum(net_Rs)
    running_max = np.maximum.accumulate(cum_R)
    drawdowns = running_max - cum_R
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    return S6MetricsReport(
        instrument=instrument,
        track=track,
        variant=variant,
        compression_episodes=compression_count,
        raw_breakouts=breakout_count,
        failures=failure_count,
        total_candidates=total_candidates,
        total_trades=n_trades,
        winning_trades=n_wins,
        losing_trades=n_losses,
        win_rate=win_rate,
        gross_expectancy_R=gross_exp,
        net_expectancy_R=net_exp,
        profit_factor=pf,
        max_drawdown_R=max_dd,
        average_MFE_R=float(mfes.mean()),
        average_MAE_R=float(maes.mean()),
        cost_drag_R=float(cost_drags.mean()),
        slippage_drag_R=float(slip_drags.mean()),
        compression_to_breakout_rate=comp_to_bo,
        breakout_to_trade_rate=bo_to_trade,
        breakout_to_failure_rate=bo_to_fail,
    )
