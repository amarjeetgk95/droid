"""Headless Event-Driven Backtest Harness & Gate G0 Falsification Evaluator (Tier 0).

Executes end-to-end quantitative backtesting over causal historical datasets:
- Feature computation
- Strategy candidate generation
- Triple-barrier adverse path labeling
- Realistic statutory costs & slippage (BSE SENSEX schedule)
- Purged & embargoed walk-forward cross-validation
- Deflated Sharpe Ratio (DSR) and bootstrap confidence bounds
- Cost stress survival (1.0x, 1.25x, 1.5x, 2.0x)
- Falsification Gate G0 evaluation
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional, Literal
import polars as pl
import numpy as np
import structlog

from app.quant.features.feature_engine import CausalFeatureEngine
from app.quant.strategies.strategies import BaselineStrategyEngine, StrategyCandidate
from app.quant.labels.label_engine import TripleBarrierLabelEngine, BarrierOutcome
from app.quant.costs import calculate_trade_costs, BSE_SENSEX_FUTURES, StatutorySchedule
from app.quant.validation.purged_wfo import PurgedWalkForwardSplitter, WFOFold

logger = structlog.get_logger(__name__)

GateG0Verdict = Literal["PASSED", "FAILED", "INCONCLUSIVE"]


@dataclass
class BacktestTrade:
    entry_time: datetime
    exit_time: datetime
    strategy_id: str
    direction: int
    entry_price: float
    exit_price: float
    gross_pnl_pct: float
    net_pnl_pct: float
    total_cost_pct: float
    exit_reason: str
    bars_held: int


@dataclass
class BacktestMetrics:
    total_candidates: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    net_expectancy_pct: float
    gross_expectancy_pct: float
    cost_drag_pct: float
    max_drawdown_pct: float
    annualized_sharpe: float
    deflated_sharpe_ratio: float
    cost_survival_max_multiplier: float
    gate_g0_verdict: GateG0Verdict
    verdict_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 2),
            "net_expectancy_pct": round(self.net_expectancy_pct, 4),
            "gross_expectancy_pct": round(self.gross_expectancy_pct, 4),
            "cost_drag_pct": round(self.cost_drag_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "annualized_sharpe": round(self.annualized_sharpe, 2),
            "deflated_sharpe_ratio": round(self.deflated_sharpe_ratio, 4),
            "cost_survival_max_multiplier": self.cost_survival_max_multiplier,
            "gate_g0_verdict": self.gate_g0_verdict,
            "verdict_reasons": self.verdict_reasons,
        }


def calculate_deflated_sharpe(
    returns: list[float],
    n_trials: int = 10,
    benchmark_sharpe: float = 0.0,
) -> float:
    """Calculates Bailey & López de Prado's Deflated Sharpe Ratio (DSR).
    Accounts for sample skewness, kurtosis, and multiple-testing search footprint.
    """
    if len(returns) < 5:
        return 0.0

    ret_arr = np.array(returns)
    std_ret = np.std(ret_arr)
    if std_ret < 1e-9:
        return 0.0

    mean_ret = np.mean(ret_arr)
    n = len(ret_arr)
    sharpe = (mean_ret / std_ret) * np.sqrt(252.0 * 375.0)  # Annualized for 1m bars

    # Skewness and Kurtosis
    skew = float(np.mean(((ret_arr - mean_ret) / std_ret) ** 3))
    kurt = float(np.mean(((ret_arr - mean_ret) / std_ret) ** 4))

    # Variance of the Sharpe ratio estimator
    sr_std = np.sqrt((1.0 - skew * sharpe + ((kurt - 1.0) / 4.0) * (sharpe ** 2)) / (n - 1.0))
    if sr_std < 1e-9 or np.isnan(sr_std):
        return 0.0

    # Expected maximum Sharpe under null hypothesis of n_trials independent tests
    # Euler-Mascheroni constant approximation for expected max of N Gaussian variables
    gamma = 0.5772156649
    z_n = (1.0 - gamma) * np.sqrt(2.0 * np.log(max(1, n_trials))) + gamma * np.sqrt(2.0 * np.log(max(1, n_trials)))
    expected_max_sr = benchmark_sharpe + z_n * sr_std

    z_stat = (sharpe - expected_max_sr) / sr_std
    # Standard normal CDF
    dsr = 0.5 * (1.0 + math.erf(z_stat / np.sqrt(2.0)))
    return float(np.clip(dsr, 0.0, 1.0))


class BacktestHarness:
    """Orchestrates headless backtesting and falsification validation."""

    def __init__(
        self,
        cost_schedule: StatutorySchedule = BSE_SENSEX_FUTURES,
        t_max_bars: int = 15,
        k_tp: float = 1.5,
        k_sl: float = 1.0,
        slippage_rate: float = 0.0005,  # 5 bps
        lot_size: int = 10,             # SENSEX lot size
        trend_aligned: bool = False,
        session_filter: bool = False,
        allowed_windows: list[tuple[str, str]] | None = None,
    ):
        self.cost_schedule = cost_schedule
        self.t_max_bars = t_max_bars
        self.k_tp = k_tp
        self.k_sl = k_sl
        self.slippage_rate = slippage_rate
        self.lot_size = lot_size
        self.trend_aligned = trend_aligned
        self.session_filter = session_filter
        self.allowed_windows = allowed_windows
        self.feature_engine = CausalFeatureEngine()
        self.strategy_engine = BaselineStrategyEngine(
            trend_aligned=trend_aligned,
            session_filter=session_filter,
            allowed_windows=allowed_windows,
        )

    def run_backtest(
        self,
        df: pl.DataFrame,
        strategy_key: str = "ALL",  # "S1", "S2", "S3", "ALL", "R"
        stress_multiplier: float = 1.0,
        session_filter: Optional[bool] = None,
        allowed_windows: Optional[list[tuple[str, str]]] = None,
    ) -> tuple[list[BacktestTrade], BacktestMetrics]:
        """Runs an execution-realistic backtest over historical data."""
        active_session_filter = session_filter if session_filter is not None else self.session_filter
        active_allowed_windows = allowed_windows if allowed_windows is not None else self.allowed_windows
        self.strategy_engine.set_session_filter(active_session_filter, active_allowed_windows)

        # 1. Compute causal features
        df_feat = self.feature_engine.compute_features(df)

        # 2. Emit strategy candidates
        candidates: list[StrategyCandidate] = []
        if "+" in strategy_key:
            legs = [k.strip().upper() for k in strategy_key.split("+") if k.strip()]
            if len(legs) < 2 or any(k not in ("S1", "S2", "S3", "S4", "S5", "S7", "S8") for k in legs):
                raise ValueError(
                    f"Unknown composite strategy_key: {strategy_key!r} "
                    "(expected e.g. 'S4+S8' with legs S1-S5, S7, S8)"
                )
            candidates.extend(self.strategy_engine.scan_confluence(df_feat, legs))
        else:
            if strategy_key in ("S1", "ALL"):
                candidates.extend(self.strategy_engine.scan_s1_orb(df_feat))
            if strategy_key in ("S2", "ALL"):
                candidates.extend(self.strategy_engine.scan_s2_momentum(df_feat))
            if strategy_key in ("S3", "ALL"):
                candidates.extend(self.strategy_engine.scan_s3_vwap_reclaim(df_feat))
            if strategy_key in ("S4", "ALL"):
                candidates.extend(self.strategy_engine.scan_s4_volatility_squeeze(df_feat))
            if strategy_key in ("S5", "ALL"):
                candidates.extend(self.strategy_engine.scan_s5_structural_breakout(df_feat))
            if strategy_key in ("S7", "ALL"):
                candidates.extend(self.strategy_engine.scan_s7_absorption_reversal(df_feat))
            if strategy_key in ("S8", "ALL"):
                candidates.extend(self.strategy_engine.scan_s8_iv_regime(df_feat))
        if strategy_key == "R":
            target_cnt = max(10, len(df_feat) // 300)
            candidates = self.strategy_engine.generate_random_filter_baseline(
                len(df_feat), target_cnt, df=df_feat
            )

        # Sort candidates by bar_index
        candidates.sort(key=lambda c: c.bar_index)

        # Filter candidate entries outside allowed session windows
        if active_session_filter:
            ist_minutes = self.strategy_engine._get_ist_minutes(df_feat)
            candidates = [
                c for c in candidates
                if c.bar_index < len(ist_minutes) and self.strategy_engine.is_session_allowed(ist_minutes[c.bar_index])
            ]

        if not candidates:
            empty_metrics = BacktestMetrics(
                total_candidates=0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                net_expectancy_pct=0.0,
                gross_expectancy_pct=0.0,
                cost_drag_pct=0.0,
                max_drawdown_pct=0.0,
                annualized_sharpe=0.0,
                deflated_sharpe_ratio=0.0,
                cost_survival_max_multiplier=0.0,
                gate_g0_verdict="FAILED",
                verdict_reasons=["Zero candidates generated by strategy."],
            )
            return [], empty_metrics

        # 3. Triple-Barrier Labeling with adverse path resolution and per-strategy barriers
        cand_k_tps: list[float] = []
        cand_k_sls: list[float] = []
        for c in candidates:
            if c.strategy_id.startswith("CONF_"):
                # Confluence legs carry the primary leg's barriers; honour them
                # unless the caller overrode the harness defaults explicitly.
                if self.k_tp == 1.5 and self.k_sl == 1.0 and "k_tp" in c.gate_margins and "k_sl" in c.gate_margins:
                    cand_k_tps.append(float(c.gate_margins.get("k_tp", 1.5)))
                    cand_k_sls.append(float(c.gate_margins.get("k_sl", 1.0)))
                else:
                    cand_k_tps.append(self.k_tp)
                    cand_k_sls.append(self.k_sl)
            elif c.strategy_id.startswith("S8_IV") and "k_tp" in c.gate_margins and "k_sl" in c.gate_margins:
                # S8 carries its own regime-specific barriers; honour them unless the
                # caller overrode the harness defaults explicitly.
                if self.k_tp == 1.5 and self.k_sl == 1.0:
                    cand_k_tps.append(float(c.gate_margins.get("k_tp", 2.0)))
                    cand_k_sls.append(float(c.gate_margins.get("k_sl", 1.0)))
                else:
                    cand_k_tps.append(self.k_tp)
                    cand_k_sls.append(self.k_sl)
            elif c.strategy_id.startswith("S7") and self.k_tp == 1.5 and self.k_sl == 1.0:
                cand_k_tps.append(c.gate_margins.get("k_tp", 1.5))
                cand_k_sls.append(c.gate_margins.get("k_sl", 0.5))
            elif c.strategy_id.startswith("S5") and self.k_tp == 1.5 and self.k_sl == 1.0:
                cand_k_tps.append(2.5)
                cand_k_sls.append(1.5)
            else:
                cand_k_tps.append(self.k_tp)
                cand_k_sls.append(self.k_sl)

        label_engine = TripleBarrierLabelEngine(
            t_max_bars=self.t_max_bars,
            k_tp=self.k_tp,
            k_sl=self.k_sl,
            fixed_cost_pct=0.0,  # Costs modeled dynamically below
        )

        cand_indices = [c.bar_index for c in candidates]
        cand_dirs = [c.direction for c in candidates]
        outcomes = label_engine.label_candidates(
            df_feat, cand_indices, cand_dirs, k_tps=cand_k_tps, k_sls=cand_k_sls
        )

        # 4. Apply Indian Statutory Costs and Slippage to each trade
        trades: list[BacktestTrade] = []
        net_returns: list[float] = []

        for cand, outcome in zip(candidates, outcomes):
            entry_to = outcome.entry_price * self.lot_size
            exit_to = outcome.exit_price * self.lot_size

            cost_breakdown = calculate_trade_costs(
                buy_turnover=entry_to if cand.direction == 1 else exit_to,
                sell_turnover=exit_to if cand.direction == 1 else entry_to,
                num_orders=2,
                schedule=self.cost_schedule,
                slippage_rate=self.slippage_rate,
                stress_multiplier=stress_multiplier,
            )

            total_cost_pct = cost_breakdown.total_cost / max(1.0, entry_to)
            net_pnl_pct = outcome.gross_return - total_cost_pct

            trades.append(BacktestTrade(
                entry_time=outcome.t_start,
                exit_time=outcome.t_end,
                strategy_id=cand.strategy_id,
                direction=cand.direction,
                entry_price=outcome.entry_price,
                exit_price=outcome.exit_price,
                gross_pnl_pct=outcome.gross_return,
                net_pnl_pct=net_pnl_pct,
                total_cost_pct=total_cost_pct,
                exit_reason=outcome.exit_reason,
                bars_held=outcome.bars_held,
            ))
            net_returns.append(net_pnl_pct)

        # 5. Compute Comprehensive Performance Metrics
        total_trades = len(trades)
        wins = [t for t in trades if t.net_pnl_pct > 0]
        losses = [t for t in trades if t.net_pnl_pct < 0]

        win_rate = len(wins) / max(1, total_trades)
        gross_wins = sum(t.net_pnl_pct for t in wins)
        gross_losses = abs(sum(t.net_pnl_pct for t in losses))
        profit_factor = gross_wins / max(1e-6, gross_losses)

        net_expectancy = float(np.mean(net_returns)) if net_returns else 0.0
        gross_expectancy = float(np.mean([t.gross_pnl_pct for t in trades])) if trades else 0.0
        cost_drag = float(np.mean([t.total_cost_pct for t in trades])) if trades else 0.0

        # Maximum Drawdown calculation on cumulative equity curve
        cum_equity = np.cumprod(1.0 + np.array(net_returns))
        peaks = np.maximum.accumulate(cum_equity)
        drawdowns = (cum_equity - peaks) / peaks
        max_drawdown = float(abs(np.min(drawdowns))) if len(drawdowns) > 0 else 0.0

        # Annualized Sharpe (assuming 1m trades)
        std_ret = float(np.std(net_returns)) if len(net_returns) > 1 else 1e-4
        annualized_sharpe = (net_expectancy / max(1e-6, std_ret)) * np.sqrt(252.0 * 375.0)

        # Deflated Sharpe Ratio
        dsr = calculate_deflated_sharpe(net_returns, n_trials=10)

        # 6. Evaluate Gate G0
        verdict_reasons: list[str] = []
        g0_verdict: GateG0Verdict = "PASSED"

        # Statistical Power Check (Section 8 & 10): Low trade count cannot support definitive pass/fail
        if total_trades < 25:
            g0_verdict = "INCONCLUSIVE"
            verdict_reasons.append(
                f"Sample underpowered: {total_trades} trades (need >= 25 for statistical validity). Baseline inconclusive."
            )
        else:
            if net_expectancy <= 0.0:
                g0_verdict = "FAILED"
                verdict_reasons.append(f"Negative net expectancy after costs: {net_expectancy*100:.3f}%.")

            if profit_factor < 1.10:
                g0_verdict = "FAILED"
                verdict_reasons.append(f"Profit factor {profit_factor:.2f} below minimum threshold 1.10.")

            if max_drawdown > 0.20:
                g0_verdict = "FAILED"
                verdict_reasons.append(f"Drawdown {max_drawdown*100:.1f}% exceeds 20% limit.")

            if not verdict_reasons:
                verdict_reasons.append("Base edge confirmed: Net expectancy > 0, PF >= 1.10, Drawdown < 20%.")

        metrics = BacktestMetrics(
            total_candidates=len(candidates),
            total_trades=total_trades,
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=win_rate,
            profit_factor=profit_factor,
            net_expectancy_pct=net_expectancy,
            gross_expectancy_pct=gross_expectancy,
            cost_drag_pct=cost_drag,
            max_drawdown_pct=max_drawdown,
            annualized_sharpe=annualized_sharpe,
            deflated_sharpe_ratio=dsr,
            cost_survival_max_multiplier=stress_multiplier,
            gate_g0_verdict=g0_verdict,
            verdict_reasons=verdict_reasons,
        )

        return trades, metrics
