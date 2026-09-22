"""Gate G1: Orthogonal ML Validation & Disjoint Calibration Evaluator (Tier 1).

Executes rigorous walk-forward cross-validation comparing:
- Arm 0: Deterministic Base (B) - no ML filter
- Arm 1: ElasticNet Only (View A Macro/Regime)
- Arm 2: LightGBM Only (View B Microstructure/Momentum)
- Arm 3: Orthogonal Ensemble (View A + View B with Disjoint Calibration & Disagreement Gating)
- Arm 4: Trade-Count Matched Random Filter (R)

Enforces Marcos López de Prado's Purging and Embargoing on overlapping triple-barrier labels.
Computes model diversity metrics (correlation, disagreement dispersion, disagreement rejection rate).
Evaluates whether ML adds genuine incremental value over the deterministic base and random filter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
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
from app.quant.backtest.backtest_harness import calculate_deflated_sharpe
from app.ml.orthogonal_ensemble import OrthogonalEnsemble, EnsemblePrediction

logger = structlog.get_logger(__name__)

GateG1Verdict = Literal["PASSED", "FAILED", "INCONCLUSIVE"]


@dataclass
class ArmResult:
    arm_name: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    net_expectancy_pct: float
    gross_expectancy_pct: float
    cost_drag_pct: float
    profit_factor: float
    max_drawdown_pct: float
    deflated_sharpe_ratio: float
    trades: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm_name": self.arm_name,
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 4),
            "net_expectancy_pct": round(self.net_expectancy_pct, 4),
            "gross_expectancy_pct": round(self.gross_expectancy_pct, 4),
            "cost_drag_pct": round(self.cost_drag_pct, 4),
            "profit_factor": round(self.profit_factor, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "deflated_sharpe_ratio": round(self.deflated_sharpe_ratio, 4),
        }


@dataclass
class GateG1Report:
    timestamp: datetime
    n_folds: int
    total_candidates: int
    arms: dict[str, ArmResult]
    model_correlation: float
    mean_disagreement: float
    disagreement_rejections: int
    disagreement_rejection_pct: float
    gate_g1_verdict: GateG1Verdict
    verdict_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "n_folds": self.n_folds,
            "total_candidates": self.total_candidates,
            "arms": {k: v.to_dict() for k, v in self.arms.items()},
            "model_correlation": round(self.model_correlation, 4),
            "mean_disagreement": round(self.mean_disagreement, 4),
            "disagreement_rejections": self.disagreement_rejections,
            "disagreement_rejection_pct": round(self.disagreement_rejection_pct, 2),
            "gate_g1_verdict": self.gate_g1_verdict,
            "verdict_reasons": self.verdict_reasons,
        }


class GateG1Evaluator:
    """Orchestrates Purged Walk-Forward Ablation and Gate G1 Evaluation."""

    def __init__(
        self,
        cost_schedule: StatutorySchedule = BSE_SENSEX_FUTURES,
        t_max_bars: int = 15,
        k_tp: float = 1.5,
        k_sl: float = 1.0,
        slippage_rate: float = 0.0005,
        lot_size: int = 10,
        n_folds: int = 5,
        confidence_threshold: float = 0.52,
        max_disagreement: float = 0.35,
        random_seed: int = 42,
    ):
        self.cost_schedule = cost_schedule
        self.t_max_bars = t_max_bars
        self.k_tp = k_tp
        self.k_sl = k_sl
        self.slippage_rate = slippage_rate
        self.lot_size = lot_size
        self.n_folds = n_folds
        self.confidence_threshold = confidence_threshold
        self.max_disagreement = max_disagreement
        self.random_seed = random_seed

    def _compute_arm_metrics(self, arm_name: str, trades: list[dict[str, Any]]) -> ArmResult:
        """Computes comprehensive performance metrics for a backtested arm."""
        if not trades:
            return ArmResult(
                arm_name=arm_name,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                net_expectancy_pct=0.0,
                gross_expectancy_pct=0.0,
                cost_drag_pct=0.0,
                profit_factor=0.0,
                max_drawdown_pct=0.0,
                deflated_sharpe_ratio=0.0,
            )

        net_returns = [t["net_pnl_pct"] for t in trades]
        gross_returns = [t["gross_pnl_pct"] for t in trades]
        costs = [t["total_cost_pct"] for t in trades]

        wins = [r for r in net_returns if r > 0]
        losses = [r for r in net_returns if r < 0]

        win_rate = len(wins) / len(net_returns)
        gross_win_sum = sum(wins)
        gross_loss_sum = abs(sum(losses))
        profit_factor = gross_win_sum / max(1e-6, gross_loss_sum)

        net_expectancy = float(np.mean(net_returns))
        gross_expectancy = float(np.mean(gross_returns))
        cost_drag = float(np.mean(costs))

        # Maximum Drawdown on cumulative equity
        cum_equity = np.cumprod(1.0 + np.array(net_returns))
        peaks = np.maximum.accumulate(cum_equity)
        drawdowns = (cum_equity - peaks) / peaks
        max_drawdown = float(abs(np.min(drawdowns))) if len(drawdowns) > 0 else 0.0

        dsr = calculate_deflated_sharpe(net_returns, n_trials=10)

        return ArmResult(
            arm_name=arm_name,
            total_trades=len(trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=win_rate,
            net_expectancy_pct=net_expectancy,
            gross_expectancy_pct=gross_expectancy,
            cost_drag_pct=cost_drag,
            profit_factor=profit_factor,
            max_drawdown_pct=max_drawdown,
            deflated_sharpe_ratio=dsr,
            trades=trades,
        )

    def evaluate(
        self,
        df: pl.DataFrame,
        strategy_key: str = "ALL",
        trend_aligned: bool = True,
    ) -> GateG1Report:
        """Executes walk-forward ablation and assesses Gate G1."""
        np.random.seed(self.random_seed)

        # 1. Compute Causal Features
        feat_engine = CausalFeatureEngine()
        df_feat = feat_engine.compute_features(df)

        # 2. Emit Strategy Candidates
        strat_engine = BaselineStrategyEngine(trend_aligned=trend_aligned)
        candidates: list[StrategyCandidate] = []
        if strategy_key in ("S1", "ALL"):
            candidates.extend(strat_engine.scan_s1_orb(df_feat))
        if strategy_key in ("S2", "ALL"):
            candidates.extend(strat_engine.scan_s2_momentum(df_feat))
        if strategy_key in ("S3", "ALL"):
            candidates.extend(strat_engine.scan_s3_vwap_reclaim(df_feat))
        if strategy_key in ("S4", "ALL"):
            candidates.extend(strat_engine.scan_s4_volatility_squeeze(df_feat))

        candidates.sort(key=lambda c: c.bar_index)
        n_cands = len(candidates)
        if n_cands < 20:
            empty_arms = {
                arm: ArmResult(
                    arm_name=arm,
                    total_trades=0,
                    winning_trades=0,
                    losing_trades=0,
                    win_rate=0.0,
                    net_expectancy_pct=0.0,
                    gross_expectancy_pct=0.0,
                    cost_drag_pct=0.0,
                    profit_factor=0.0,
                    max_drawdown_pct=0.0,
                    deflated_sharpe_ratio=0.0,
                    trades=[],
                )
                for arm in [
                    "Arm 0 (Base B)",
                    "Arm 1 (Linear/Causal Features)",
                    "Arm 2 (LGBM/Kinetic Features)",
                    "Arm 3 (Orthogonal Ensemble)",
                    "Arm 4 (Matched Random Filter)",
                ]
            }
            return GateG1Report(
                timestamp=datetime.now(),
                n_folds=self.n_folds,
                total_candidates=n_cands,
                arms=empty_arms,
                model_correlation=0.0,
                mean_disagreement=0.0,
                disagreement_rejections=0,
                disagreement_rejection_pct=0.0,
                gate_g1_verdict="INCONCLUSIVE",
                verdict_reasons=[
                    f"Sample underpowered: {n_cands} candidates found (need >= 20 for Purged WFO ablation). Gate G1 inconclusive."
                ],
            )

        # 3. Triple-Barrier Labeling with adverse path resolution
        label_engine = TripleBarrierLabelEngine(
            t_max_bars=self.t_max_bars,
            k_tp=self.k_tp,
            k_sl=self.k_sl,
        )
        cand_indices = [c.bar_index for c in candidates]
        cand_dirs = [c.direction for c in candidates]
        outcomes = label_engine.label_candidates(df_feat, cand_indices, cand_dirs)

        # 4. Compute Net Returns and Binary Labels per Candidate
        cand_net_returns: list[float] = []
        cand_gross_returns: list[float] = []
        cand_costs: list[float] = []
        cand_timestamps: list[datetime] = []
        cand_end_times: list[datetime] = []
        binary_targets: list[int] = []

        for cand, outcome in zip(candidates, outcomes):
            entry_to = outcome.entry_price * self.lot_size
            exit_to = outcome.exit_price * self.lot_size

            cost_breakdown = calculate_trade_costs(
                buy_turnover=entry_to if cand.direction == 1 else exit_to,
                sell_turnover=exit_to if cand.direction == 1 else entry_to,
                num_orders=2,
                schedule=self.cost_schedule,
                slippage_rate=self.slippage_rate,
            )
            cost_pct = cost_breakdown.total_cost / max(1.0, entry_to)
            net_ret = outcome.gross_return - cost_pct

            cand_net_returns.append(net_ret)
            cand_gross_returns.append(outcome.gross_return)
            cand_costs.append(cost_pct)
            cand_timestamps.append(outcome.t_start)
            cand_end_times.append(outcome.t_end)
            binary_targets.append(1 if net_ret > 0 else 0)

        y_all = np.array(binary_targets)

        # 5. Purged Walk-Forward Cross-Validation
        splitter = PurgedWalkForwardSplitter(
            n_folds=self.n_folds,
            train_ratio=0.55,
            val_ratio=0.15,
            test_ratio=0.30,
        )
        folds = splitter.split(cand_timestamps, cand_end_times)

        # Stores out-of-sample trades for each ablation arm
        trades_base: list[dict[str, Any]] = []
        trades_linear: list[dict[str, Any]] = []
        trades_lgbm: list[dict[str, Any]] = []
        trades_ensemble: list[dict[str, Any]] = []
        trades_random: list[dict[str, Any]] = []

        # Model diversity telemetry across all test observations
        all_p_linear: list[float] = []
        all_p_lgbm: list[float] = []
        disagreement_rejections = 0
        total_test_evals = 0

        for fold in folds:
            if len(fold.train_indices) < 10 or len(fold.test_indices) < 5:
                continue

            train_bar_indices = [cand_indices[i] for i in fold.train_indices]
            val_bar_indices = [cand_indices[i] for i in fold.val_indices] if fold.val_indices else None

            ensemble = OrthogonalEnsemble(
                confidence_threshold=self.confidence_threshold,
                max_disagreement=self.max_disagreement,
                random_state=self.random_seed + fold.fold_id,
            )

            ensemble.fit(
                df=df_feat,
                train_indices=train_bar_indices,
                y_train=y_all[fold.train_indices],
                val_indices=val_bar_indices,
                y_val=y_all[fold.val_indices] if fold.val_indices else None,
            )

            if not ensemble.is_fitted:
                continue

            # Evaluate each test candidate out-of-sample
            fold_ensemble_accepted_indices: list[int] = []

            for i in fold.test_indices:
                bar_idx = cand_indices[i]
                pred = ensemble.predict_one(df_feat, bar_idx)
                total_test_evals += 1

                all_p_linear.append(pred.p_linear)
                all_p_lgbm.append(pred.p_lgbm)

                # Track if high disagreement killed an otherwise probable setup
                if pred.calibrated_prob >= self.confidence_threshold and pred.disagreement > self.max_disagreement:
                    disagreement_rejections += 1

                trade_data = {
                    "entry_time": cand_timestamps[i],
                    "strategy_id": candidates[i].strategy_id,
                    "direction": candidates[i].direction,
                    "gross_pnl_pct": cand_gross_returns[i],
                    "net_pnl_pct": cand_net_returns[i],
                    "total_cost_pct": cand_costs[i],
                    "bars_held": outcomes[i].bars_held,
                }

                # Arm 0: Base (always accepted)
                trades_base.append(trade_data)

                # Arm 1: Linear Only (threshold check on p_linear)
                if pred.p_linear >= self.confidence_threshold:
                    trades_linear.append(trade_data)

                # Arm 2: LightGBM Only (threshold check on p_lgbm)
                if pred.p_lgbm >= self.confidence_threshold:
                    trades_lgbm.append(trade_data)

                # Arm 3: Orthogonal Ensemble (disagreement penalized & calibrated)
                if pred.is_qualified:
                    trades_ensemble.append(trade_data)
                    fold_ensemble_accepted_indices.append(i)

            # Arm 4: Matched Random Filter
            # Picks exactly k random candidates from the fold's test set
            k_match = len(fold_ensemble_accepted_indices)
            if k_match > 0 and len(fold.test_indices) > 0:
                chosen_random_indices = np.random.choice(
                    fold.test_indices,
                    size=min(k_match, len(fold.test_indices)),
                    replace=False,
                )
                for r_idx in chosen_random_indices:
                    trades_random.append({
                        "entry_time": cand_timestamps[r_idx],
                        "strategy_id": candidates[r_idx].strategy_id,
                        "direction": candidates[r_idx].direction,
                        "gross_pnl_pct": cand_gross_returns[r_idx],
                        "net_pnl_pct": cand_net_returns[r_idx],
                        "total_cost_pct": cand_costs[r_idx],
                        "bars_held": outcomes[r_idx].bars_held,
                    })

        # 6. Compute Performance for all 5 arms
        arms_results = {
            "Arm 0 (Base B)": self._compute_arm_metrics("Base (B)", trades_base),
            "Arm 1 (ElasticNet)": self._compute_arm_metrics("ElasticNet (View A)", trades_linear),
            "Arm 2 (LightGBM)": self._compute_arm_metrics("LightGBM (View B)", trades_lgbm),
            "Arm 3 (Orthogonal Ensemble)": self._compute_arm_metrics("Orthogonal Ensemble", trades_ensemble),
            "Arm 4 (Matched Random Filter)": self._compute_arm_metrics("Matched Random Filter (R)", trades_random),
        }

        # 7. Model Diversity & Disagreement Statistics
        if len(all_p_linear) > 1:
            corr_matrix = np.corrcoef(all_p_linear, all_p_lgbm)
            model_corr = float(corr_matrix[0, 1]) if not np.isnan(corr_matrix[0, 1]) else 0.0
            mean_disagree = float(np.mean(np.abs(np.array(all_p_linear) - np.array(all_p_lgbm))))
        else:
            model_corr = 0.0
            mean_disagree = 0.0

        disagree_pct = (disagreement_rejections / max(1, total_test_evals)) * 100.0

        # 8. Evaluate Gate G1 Rules
        ens_res = arms_results["Arm 3 (Orthogonal Ensemble)"]
        base_res = arms_results["Arm 0 (Base B)"]
        rand_res = arms_results["Arm 4 (Matched Random Filter)"]

        verdict_reasons: list[str] = []
        g1_verdict: GateG1Verdict = "PASSED"

        if ens_res.total_trades < 10:
            g1_verdict = "FAILED"
            verdict_reasons.append(f"Insufficient out-of-sample trades: {ens_res.total_trades} (need >= 10).")

        if ens_res.net_expectancy_pct <= 0.0:
            g1_verdict = "FAILED"
            verdict_reasons.append(
                f"Ensemble net expectancy {ens_res.net_expectancy_pct*100:.3f}% is non-positive."
            )

        if ens_res.net_expectancy_pct < base_res.net_expectancy_pct:
            g1_verdict = "FAILED"
            verdict_reasons.append(
                f"Ensemble net expectancy ({ens_res.net_expectancy_pct*100:.3f}%) does not beat Base ({base_res.net_expectancy_pct*100:.3f}%)."
            )

        if ens_res.net_expectancy_pct <= rand_res.net_expectancy_pct:
            g1_verdict = "FAILED"
            verdict_reasons.append(
                f"Ensemble net expectancy ({ens_res.net_expectancy_pct*100:.3f}%) does not beat Matched Random ({rand_res.net_expectancy_pct*100:.3f}%)."
            )

        if model_corr > 0.85:
            g1_verdict = "FAILED"
            verdict_reasons.append(
                f"Feature views insufficiently diverse: Linear & LGBM correlation {model_corr:.2f} > 0.85."
            )

        if not verdict_reasons:
            verdict_reasons.append(
                "Orthogonal Ensemble proven: beats Base, beats Matched Random, positive net expectancy, and diverse inductive biases."
            )

        return GateG1Report(
            timestamp=datetime.now(),
            n_folds=len(folds),
            total_candidates=n_cands,
            arms=arms_results,
            model_correlation=model_corr,
            mean_disagreement=mean_disagree,
            disagreement_rejections=disagreement_rejections,
            disagreement_rejection_pct=disagree_pct,
            gate_g1_verdict=g1_verdict,
            verdict_reasons=verdict_reasons,
        )
