"""
Crypto Scalp Performance Attribution & Track Record Engine
Computes institutional-grade quantitative metrics: empirical win rate %,
profit factor, expectancy R, execution drag, strategy and asset breakdowns,
and enforces statistical quality gates (sample size < 10 warning).
"""
from __future__ import annotations

from typing import Iterable
from app.crypto_scalp.models_execution import (
    CryptoScalpExecutionRecord,
    CryptoScalpPositionState,
    CryptoScalpPerformanceMetrics,
    CryptoScalpStrategyStats,
    CryptoScalpAssetStats,
)
from app.crypto_scalp.strategies import CRYPTO_SCALP_STRATEGIES


STRATEGY_DISPLAY_NAMES: dict[str, str] = {
    "VWAP_BOUNCE": "VWAP Rejection Scalp",
    "EMA_CROSS_SCALP": "Micro EMA Cross Scalp",
    "FUNDING_SQUEEZE": "Perp Funding Squeeze",
    "BREAKOUT_VOLUME": "Volume Burst Breakout",
    "DEPTH_FLIP": "Order Book Liquidity Flip",
}


class CryptoScalpPerformanceEngine:
    """Calculates comprehensive quantitative performance metrics from execution records."""

    @staticmethod
    def calculate_metrics(records: Iterable[CryptoScalpExecutionRecord]) -> CryptoScalpPerformanceMetrics:
        recs = list(records)
        total_signals = len(recs)

        active = [r for r in recs if r.position_state in (CryptoScalpPositionState.ACTIVE, CryptoScalpPositionState.PARTIALLY_CLOSED)]
        closed = [r for r in recs if r.position_state == CryptoScalpPositionState.CLOSED]

        completed_trades = len(closed)
        winning_trades = [r for r in closed if r.net_pnl_usd > 0.0]
        losing_trades = [r for r in closed if r.net_pnl_usd < 0.0]
        breakeven_trades = [r for r in closed if r.net_pnl_usd == 0.0]

        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        be_count = len(breakeven_trades)

        win_rate_pct = round((win_count / completed_trades) * 100.0, 1) if completed_trades > 0 else 0.0

        gross_profit_usd = round(sum(r.net_pnl_usd for r in winning_trades), 2)
        gross_loss_usd = round(sum(abs(r.net_pnl_usd) for r in losing_trades), 2)

        if gross_loss_usd > 0:
            profit_factor = round(gross_profit_usd / gross_loss_usd, 2)
        elif gross_profit_usd > 0:
            profit_factor = 999.0
        else:
            profit_factor = 1.0

        expectancy_r = round(sum(r.r_multiple for r in closed) / completed_trades, 2) if completed_trades > 0 else 0.0
        average_r = expectancy_r
        average_win_r = round(sum(r.r_multiple for r in winning_trades) / win_count, 2) if win_count > 0 else 0.0
        average_loss_r = round(sum(r.r_multiple for r in losing_trades) / loss_count, 2) if loss_count > 0 else 0.0

        net_pnl_usd = round(sum(r.net_pnl_usd for r in closed), 2)
        total_fees_usd = round(sum(r.fees_usd for r in recs), 2)
        total_slippage_usd = round(sum(r.slippage_usd for r in recs), 2)
        total_execution_drag_usd = round(sum(r.execution_drag_r * r.initial_risk_usd for r in closed), 2)

        avg_dur_sec = int(sum(r.duration_seconds for r in closed) / completed_trades) if completed_trades > 0 else 0
        mins = avg_dur_sec // 60
        secs = avg_dur_sec % 60
        avg_dur_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

        # 1. Strategy Breakdown
        strategy_stats: dict[str, CryptoScalpStrategyStats] = {}
        # Pre-seed default strategies
        for strat_key in CRYPTO_SCALP_STRATEGIES.keys():
            strategy_stats[strat_key] = CryptoScalpStrategyStats(
                strategy=strat_key,
                strategy_name=STRATEGY_DISPLAY_NAMES.get(strat_key, strat_key),
            )

        for strat_key in list(strategy_stats.keys()):
            strat_all = [r for r in recs if r.strategy.upper() == strat_key.upper()]
            strat_closed = [r for r in strat_all if r.position_state == CryptoScalpPositionState.CLOSED]
            strat_wins = [r for r in strat_closed if r.net_pnl_usd > 0.0]
            strat_losses = [r for r in strat_closed if r.net_pnl_usd < 0.0]
            strat_be = [r for r in strat_closed if r.net_pnl_usd == 0.0]

            s_completed = len(strat_closed)
            s_win_count = len(strat_wins)
            s_loss_count = len(strat_losses)
            s_be_count = len(strat_be)

            s_win_rate = round((s_win_count / s_completed) * 100.0, 1) if s_completed > 0 else 0.0
            s_gp = round(sum(r.net_pnl_usd for r in strat_wins), 2)
            s_gl = round(sum(abs(r.net_pnl_usd) for r in strat_losses), 2)
            s_pf = round(s_gp / s_gl, 2) if s_gl > 0 else (999.0 if s_gp > 0 else 1.0)
            s_exp = round(sum(r.r_multiple for r in strat_closed) / s_completed, 2) if s_completed > 0 else 0.0
            s_net = round(sum(r.net_pnl_usd for r in strat_closed), 2)
            s_dur = int(sum(r.duration_seconds for r in strat_closed) / s_completed) if s_completed > 0 else 0

            strategy_stats[strat_key] = CryptoScalpStrategyStats(
                strategy=strat_key,
                strategy_name=STRATEGY_DISPLAY_NAMES.get(strat_key, strat_key),
                total_signals=len(strat_all),
                filled_trades=len(strat_all),
                completed_trades=s_completed,
                winning_trades=s_win_count,
                losing_trades=s_loss_count,
                breakeven_trades=s_be_count,
                win_rate_pct=s_win_rate,
                profit_factor=s_pf,
                expectancy_r=s_exp,
                gross_profit_usd=s_gp,
                gross_loss_usd=s_gl,
                net_pnl_usd=s_net,
                average_r=s_exp,
                average_duration_seconds=s_dur,
                sample_size=s_completed,
                insufficient_sample=s_completed < 10,
            )

        # 2. Asset Breakdown (BTC vs ETH)
        asset_stats: dict[str, CryptoScalpAssetStats] = {
            "BTC": CryptoScalpAssetStats(asset="BTC", symbol="BTCUSDT"),
            "ETH": CryptoScalpAssetStats(asset="ETH", symbol="ETHUSDT"),
        }

        for asset_key, symbol_code in [("BTC", "BTCUSDT"), ("ETH", "ETHUSDT")]:
            a_closed = [r for r in closed if r.asset.upper() == asset_key]
            a_completed = len(a_closed)
            a_wins = [r for r in a_closed if r.net_pnl_usd > 0.0]
            a_losses = [r for r in a_closed if r.net_pnl_usd < 0.0]
            a_win_rate = round((len(a_wins) / a_completed) * 100.0, 1) if a_completed > 0 else 0.0

            a_gp = sum(r.net_pnl_usd for r in a_wins)
            a_gl = sum(abs(r.net_pnl_usd) for r in a_losses)
            a_pf = round(a_gp / a_gl, 2) if a_gl > 0 else (999.0 if a_gp > 0 else 1.0)
            a_net = round(sum(r.net_pnl_usd for r in a_closed), 2)
            a_exp = round(sum(r.r_multiple for r in a_closed) / a_completed, 2) if a_completed > 0 else 0.0
            a_dur = int(sum(r.duration_seconds for r in a_closed) / a_completed) if a_completed > 0 else 0

            asset_stats[asset_key] = CryptoScalpAssetStats(
                asset=asset_key,
                symbol=symbol_code,
                total_trades=a_completed,
                winning_trades=len(a_wins),
                losing_trades=len(a_losses),
                win_rate_pct=a_win_rate,
                profit_factor=a_pf,
                net_pnl_usd=a_net,
                expectancy_r=a_exp,
                average_duration_seconds=a_dur,
            )

        return CryptoScalpPerformanceMetrics(
            total_signals=total_signals,
            active_positions=len(active),
            completed_trades=completed_trades,
            winning_trades=win_count,
            losing_trades=loss_count,
            breakeven_trades=be_count,
            win_rate_pct=win_rate_pct,
            profit_factor=profit_factor,
            expectancy_r=expectancy_r,
            average_r=average_r,
            average_win_r=average_win_r,
            average_loss_r=average_loss_r,
            gross_profit_usd=gross_profit_usd,
            gross_loss_usd=gross_loss_usd,
            net_pnl_usd=net_pnl_usd,
            total_fees_usd=total_fees_usd,
            total_slippage_usd=total_slippage_usd,
            total_execution_drag_usd=total_execution_drag_usd,
            average_duration_seconds=avg_dur_sec,
            average_duration_str=avg_dur_str,
            insufficient_sample=completed_trades < 10,
            strategy_breakdown=strategy_stats,
            asset_breakdown=asset_stats,
        )


performance_engine = CryptoScalpPerformanceEngine()
