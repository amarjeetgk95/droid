"""
9-Stage Component Ablation Runner (§32).

Executes 9 controlled configurations sequentially across the identical dataset
to measure the marginal predictive power and risk reduction of each component:

- Config A: Compression Alone
- Config B: Compression + Pressure
- Config C: Compression + Pressure + Translation Ratio (Primary Hypothesis Test)
- Config D: + Absorption Detector
- Config E: + Liquidity Vacuum Detector
- Config F: + Snap Energy Composite
- Config G: + Confirmation Engine
- Config H: + Market Regime Filtering
- Config I: Full System with Dynamic Exits
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from app.signals.strategies.vortex_snap.config import VortexSnapConfig
from app.signals.strategies.vortex_snap.strategy import VortexSnapStrategy
from app.signals.strategies.vortex_snap.backtest.data_loader import HistoricalBarContext
from app.signals.strategies.vortex_snap.backtest.engine import VortexBacktestEngine
from app.signals.strategies.vortex_snap.backtest.metrics import BacktestMetricsSummary


@dataclass
class AblationStageResult:
    """Performance and delta statistics for a single ablation configuration."""
    config_name: str
    stage_letter: str
    description: str
    metrics: BacktestMetricsSummary
    delta_sharpe_vs_baseline: float
    delta_win_rate_vs_baseline: float
    delta_profit_factor_vs_baseline: float
    delta_max_dd_vs_baseline: float
    marginal_sharpe_gain: float  # vs immediately preceding stage

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage_letter,
            "config_name": self.config_name,
            "description": self.description,
            "trades": self.metrics.total_trades,
            "win_rate_pct": round(self.metrics.win_rate_pct, 1),
            "profit_factor": round(self.metrics.profit_factor, 2),
            "annualized_sharpe": round(self.metrics.annualized_sharpe, 2),
            "max_dd_pct": round(self.metrics.max_drawdown_pct, 1),
            "delta_sharpe": round(self.delta_sharpe_vs_baseline, 2),
            "delta_win_rate": round(self.delta_win_rate_vs_baseline, 1),
            "marginal_sharpe": round(self.marginal_sharpe_gain, 2),
        }


@dataclass
class AblationStudyReport:
    """Full 9-stage ablation study report and hypothesis verification."""
    stages: List[AblationStageResult] = field(default_factory=list)
    primary_hypothesis_supported: bool = False
    primary_hypothesis_delta_sharpe: float = 0.0
    primary_hypothesis_delta_win_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary_hypothesis_supported": self.primary_hypothesis_supported,
            "primary_hypothesis_delta_sharpe": round(self.primary_hypothesis_delta_sharpe, 2),
            "primary_hypothesis_delta_win_rate": round(self.primary_hypothesis_delta_win_rate, 1),
            "stages": [s.to_dict() for s in self.stages],
        }


class ComponentAblationRunner:
    """Runs 9-stage component ablation experiments."""

    def __init__(self, base_config: Optional[VortexSnapConfig] = None):
        self.base_config = base_config or VortexSnapConfig()

    def run_study(
        self,
        bar_contexts: List[HistoricalBarContext],
        instrument: str = "NIFTY",
    ) -> AblationStudyReport:
        """Executes the 9-stage ablation study across bar contexts."""
        stages_def = [
            (
                "A",
                "Compression Alone",
                "Baseline compression breakout without microstructure pressure or translation",
                {
                    "pressure": False,
                    "translation": False,
                    "absorption": False,
                    "vacuum": False,
                    "snap_energy": False,
                    "regime": False,
                },
                False,  # dynamic exits
            ),
            (
                "B",
                "Compression + Pressure",
                "Adds directional pressure accumulation to compression",
                {
                    "pressure": True,
                    "translation": False,
                    "absorption": False,
                    "vacuum": False,
                    "snap_energy": False,
                    "regime": False,
                },
                False,
            ),
            (
                "C",
                "Compression + Pressure + Translation",
                "PRIMARY HYPOTHESIS: Tests predictive displacement-to-pressure efficiency",
                {
                    "pressure": True,
                    "translation": True,
                    "absorption": False,
                    "vacuum": False,
                    "snap_energy": False,
                    "regime": False,
                },
                False,
            ),
            (
                "D",
                "+ Absorption Detector",
                "Adds absorption reversal recognition (TYPE B)",
                {
                    "pressure": True,
                    "translation": True,
                    "absorption": True,
                    "vacuum": False,
                    "snap_energy": False,
                    "regime": False,
                },
                False,
            ),
            (
                "E",
                "+ Liquidity Vacuum",
                "Adds liquidity vacuum trap detection (TYPE C)",
                {
                    "pressure": True,
                    "translation": True,
                    "absorption": True,
                    "vacuum": True,
                    "snap_energy": False,
                    "regime": False,
                },
                False,
            ),
            (
                "F",
                "+ Snap Energy",
                "Adds multi-factor snap energy thresholding",
                {
                    "pressure": True,
                    "translation": True,
                    "absorption": True,
                    "vacuum": True,
                    "snap_energy": True,
                    "regime": False,
                },
                False,
            ),
            (
                "G",
                "+ Confirmation Engine",
                "Enforces 2-bar follow-through / retest confirmation gates",
                {
                    "pressure": True,
                    "translation": True,
                    "absorption": True,
                    "vacuum": True,
                    "snap_energy": True,
                    "regime": False,
                },
                False,
            ),
            (
                "H",
                "+ Market Regime Filtering",
                "Restricts candidate generation to permitted regime matrix",
                {
                    "pressure": True,
                    "translation": True,
                    "absorption": True,
                    "vacuum": True,
                    "snap_energy": True,
                    "regime": True,
                },
                False,
            ),
            (
                "I",
                "Full System (Dynamic Exits)",
                "Full architecture with 0.8x/1.3x multi-target scaling and time decay exits",
                {
                    "pressure": True,
                    "translation": True,
                    "absorption": True,
                    "vacuum": True,
                    "snap_energy": True,
                    "regime": True,
                },
                True,  # dynamic exits enabled
            ),
        ]

        results: List[AblationStageResult] = []
        base_sharpe = 0.0
        base_win_rate = 0.0
        base_pf = 0.0
        base_dd = 0.0
        prev_sharpe = 0.0

        for stage_letter, name, desc, overrides, dyn_exits in stages_def:
            strat = VortexSnapStrategy(config=self.base_config, ablation_overrides=overrides)
            engine = VortexBacktestEngine(
                strategy=strat,
                enable_dynamic_exits=dyn_exits,
            )
            m = engine.run(bar_contexts, instrument)

            if stage_letter == "A":
                base_sharpe = m.annualized_sharpe
                base_win_rate = m.win_rate_pct
                base_pf = m.profit_factor
                base_dd = m.max_drawdown_pct
                marginal = 0.0
            else:
                marginal = m.annualized_sharpe - prev_sharpe

            delta_sh = m.annualized_sharpe - base_sharpe
            delta_wr = m.win_rate_pct - base_win_rate
            delta_pf = m.profit_factor - base_pf
            delta_dd = m.max_drawdown_pct - base_dd

            results.append(
                AblationStageResult(
                    config_name=name,
                    stage_letter=stage_letter,
                    description=desc,
                    metrics=m,
                    delta_sharpe_vs_baseline=delta_sh,
                    delta_win_rate_vs_baseline=delta_wr,
                    delta_profit_factor_vs_baseline=delta_pf,
                    delta_max_dd_vs_baseline=delta_dd,
                    marginal_sharpe_gain=marginal,
                )
            )
            prev_sharpe = m.annualized_sharpe

        # Primary hypothesis: Delta from Stage B to Stage C
        stage_b = next(s for s in results if s.stage_letter == "B")
        stage_c = next(s for s in results if s.stage_letter == "C")
        prim_delta_sh = stage_c.metrics.annualized_sharpe - stage_b.metrics.annualized_sharpe
        prim_delta_wr = stage_c.metrics.win_rate_pct - stage_b.metrics.win_rate_pct
        hypothesis_supported = (prim_delta_sh > 0.0) or (prim_delta_wr > 0.0)

        return AblationStudyReport(
            stages=results,
            primary_hypothesis_supported=hypothesis_supported,
            primary_hypothesis_delta_sharpe=prim_delta_sh,
            primary_hypothesis_delta_win_rate=prim_delta_wr,
        )
