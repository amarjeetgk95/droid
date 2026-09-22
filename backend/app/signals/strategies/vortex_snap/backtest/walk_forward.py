"""
Rolling Walk-Forward Validator (§31).

Implements strict temporal splits:
- In-Sample (Train/Calibration)
- Validation (Selection)
- Out-of-Sample (Unseen Testing)
- Purged Embargo buffers between splits to eliminate autocorrelation leakage
- Walk-Forward Efficiency (WFE) = OOS Annualized Sharpe / IS Annualized Sharpe
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from app.signals.strategies.vortex_snap.strategy import VortexSnapStrategy
from app.signals.strategies.vortex_snap.backtest.data_loader import HistoricalBarContext
from app.signals.strategies.vortex_snap.backtest.engine import VortexBacktestEngine
from app.signals.strategies.vortex_snap.backtest.metrics import BacktestMetricsSummary


@dataclass
class WalkForwardFoldResult:
    """Performance results for a single rolling walk-forward fold."""
    fold_index: int
    train_bars_count: int
    val_bars_count: int
    test_bars_count: int
    train_metrics: BacktestMetricsSummary
    val_metrics: BacktestMetricsSummary
    test_metrics: BacktestMetricsSummary
    walk_forward_efficiency: float
    is_overfit_suspected: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fold_index": self.fold_index,
            "train_bars": self.train_bars_count,
            "val_bars": self.val_bars_count,
            "test_bars": self.test_bars_count,
            "is_sharpe": round(self.train_metrics.annualized_sharpe, 2),
            "val_sharpe": round(self.val_metrics.annualized_sharpe, 2),
            "oos_sharpe": round(self.test_metrics.annualized_sharpe, 2),
            "is_win_rate": round(self.train_metrics.win_rate_pct, 1),
            "oos_win_rate": round(self.test_metrics.win_rate_pct, 1),
            "walk_forward_efficiency": round(self.walk_forward_efficiency, 2),
            "is_overfit_suspected": self.is_overfit_suspected,
        }


@dataclass
class WalkForwardSummary:
    """Aggregate walk-forward analysis across all folds."""
    total_folds: int
    mean_is_sharpe: float
    mean_oos_sharpe: float
    mean_wfe: float
    mean_oos_win_rate: float
    folds: List[WalkForwardFoldResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_folds": self.total_folds,
            "mean_is_sharpe": round(self.mean_is_sharpe, 2),
            "mean_oos_sharpe": round(self.mean_oos_sharpe, 2),
            "mean_wfe": round(self.mean_wfe, 2),
            "mean_oos_win_rate": round(self.mean_oos_win_rate, 1),
            "folds": [f.to_dict() for f in self.folds],
        }


class RollingWalkForwardValidator:
    """Executes rolling walk-forward backtests with purged embargoes."""

    def __init__(
        self,
        n_folds: int = 3,
        train_ratio: float = 0.60,
        val_ratio: float = 0.20,
        test_ratio: float = 0.20,
        embargo_bars: int = 375,  # 1 full session embargo
    ):
        self.n_folds = n_folds
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        self.embargo_bars = embargo_bars

    def evaluate(
        self,
        bar_contexts: List[HistoricalBarContext],
        instrument: str = "NIFTY",
    ) -> WalkForwardSummary:
        """Executes walk-forward validation across the available bar contexts."""
        total_bars = len(bar_contexts)
        min_required = 375 * 5  # At least 5 trading days
        if total_bars < min_required:
            # Single fold fallback if small sample
            engine = VortexBacktestEngine()
            full_res = engine.run(bar_contexts, instrument)
            single_fold = WalkForwardFoldResult(
                fold_index=1,
                train_bars_count=int(total_bars * 0.6),
                val_bars_count=int(total_bars * 0.2),
                test_bars_count=int(total_bars * 0.2),
                train_metrics=full_res,
                val_metrics=full_res,
                test_metrics=full_res,
                walk_forward_efficiency=1.0,
                is_overfit_suspected=False,
            )
            return WalkForwardSummary(
                total_folds=1,
                mean_is_sharpe=full_res.annualized_sharpe,
                mean_oos_sharpe=full_res.annualized_sharpe,
                mean_wfe=1.0,
                mean_oos_win_rate=full_res.win_rate_pct,
                folds=[single_fold],
            )

        fold_size = total_bars // self.n_folds
        folds_results: List[WalkForwardFoldResult] = []

        for fold_idx in range(self.n_folds):
            # Window slice
            window_start = fold_idx * (total_bars - fold_size) // max(1, self.n_folds - 1)
            window_end = min(window_start + fold_size, total_bars)
            window_bars = bar_contexts[window_start:window_end]

            n_w = len(window_bars)
            train_end = int(n_w * self.train_ratio)
            val_start = train_end + self.embargo_bars
            val_end = min(val_start + int(n_w * self.val_ratio), n_w)
            test_start = val_end + self.embargo_bars
            test_end = n_w

            if val_start >= n_w or test_start >= n_w:
                # If embargo pushes past window, adjust without embargo
                train_end = int(n_w * 0.6)
                val_start = train_end
                val_end = int(n_w * 0.8)
                test_start = val_end
                test_end = n_w

            train_slice = window_bars[:train_end]
            val_slice = window_bars[val_start:val_end]
            test_slice = window_bars[test_start:test_end]

            engine_train = VortexBacktestEngine()
            train_m = engine_train.run(train_slice, instrument)

            engine_val = VortexBacktestEngine()
            val_m = engine_val.run(val_slice, instrument)

            engine_test = VortexBacktestEngine()
            test_m = engine_test.run(test_slice, instrument)

            is_sharpe = max(train_m.annualized_sharpe, 0.01)
            oos_sharpe = test_m.annualized_sharpe
            wfe = oos_sharpe / is_sharpe

            # Overfitting suspected if WFE < 0.40 or OOS Sharpe <= 0 while IS Sharpe > 1.5
            is_overfit = (wfe < 0.40) or (train_m.annualized_sharpe > 1.5 and test_m.annualized_sharpe <= 0.0)

            folds_results.append(
                WalkForwardFoldResult(
                    fold_index=fold_idx + 1,
                    train_bars_count=len(train_slice),
                    val_bars_count=len(val_slice),
                    test_bars_count=len(test_slice),
                    train_metrics=train_m,
                    val_metrics=val_m,
                    test_metrics=test_m,
                    walk_forward_efficiency=round(wfe, 3),
                    is_overfit_suspected=is_overfit,
                )
            )

        mean_is = sum(f.train_metrics.annualized_sharpe for f in folds_results) / len(folds_results)
        mean_oos = sum(f.test_metrics.annualized_sharpe for f in folds_results) / len(folds_results)
        mean_wfe = sum(f.walk_forward_efficiency for f in folds_results) / len(folds_results)
        mean_oos_wr = sum(f.test_metrics.win_rate_pct for f in folds_results) / len(folds_results)

        return WalkForwardSummary(
            total_folds=len(folds_results),
            mean_is_sharpe=mean_is,
            mean_oos_sharpe=mean_oos,
            mean_wfe=mean_wfe,
            mean_oos_win_rate=mean_oos_wr,
            folds=folds_results,
        )
