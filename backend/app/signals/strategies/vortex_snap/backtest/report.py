"""
Automated Research Reporting Engine (§50, §52).

Generates institutional Markdown and JSON research summaries covering:
- Baseline performance metrics
- 9-Stage Component Ablation results
- Primary Hypothesis Validation verdict
- Rolling Walk-Forward efficiency
- Robustness & Cost stress analysis
- Monte Carlo confidence intervals
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from app.signals.strategies.vortex_snap.backtest.metrics import BacktestMetricsSummary
from app.signals.strategies.vortex_snap.backtest.ablation import AblationStudyReport
from app.signals.strategies.vortex_snap.backtest.walk_forward import WalkForwardSummary
from app.signals.strategies.vortex_snap.backtest.robustness import RobustnessReport


class ResearchReportGenerator:
    """Generates comprehensive markdown and JSON research documents."""

    def __init__(self, output_dir: Path | str = "data/experiments"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_markdown(
        self,
        instrument: str,
        baseline: BacktestMetricsSummary,
        ablation: Optional[AblationStudyReport] = None,
        walk_forward: Optional[WalkForwardSummary] = None,
        robustness: Optional[RobustnessReport] = None,
    ) -> str:
        """Builds publication-ready Markdown research report."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        md = []
        md.append(f"# DROID VORTEX-SNAP Quantitative Research Report")
        md.append(f"**Instrument**: `{instrument}` | **Generated**: `{now_str}`")
        md.append(f"**Strategy Type**: Adaptive Microstructure Scalping Engine")
        md.append("")

        # 1. Executive Summary Table
        md.append("## 1. Baseline Performance Summary (§35)")
        md.append("| Metric | Value | Metric | Value |")
        md.append("| :--- | :--- | :--- | :--- |")
        md.append(f"| **Total Trades** | {baseline.total_trades} | **Win Rate** | {baseline.win_rate_pct:.1f}% |")
        md.append(f"| **Profit Factor** | {baseline.profit_factor:.2f} | **Win / Loss Ratio** | {baseline.win_loss_ratio:.2f} |")
        md.append(f"| **Gross PnL (₹)** | ₹{baseline.gross_pnl_rupees:,.2f} | **Net PnL (₹)** | ₹{baseline.net_pnl_rupees:,.2f} |")
        md.append(f"| **Total Friction (₹)** | ₹{baseline.total_friction_rupees:,.2f} | **Cost Drag** | {baseline.cost_drag_pct:.1f}% |")
        md.append(f"| **Annualized Sharpe** | {baseline.annualized_sharpe:.2f} | **Annualized Sortino** | {baseline.annualized_sortino:.2f} |")
        md.append(f"| **Max Drawdown %** | {baseline.max_drawdown_pct:.1f}% | **Max DD Duration** | {baseline.max_drawdown_duration_bars} bars |")
        md.append(f"| **Calmar Ratio** | {baseline.calmar_ratio:.2f} | **Recovery Factor** | {baseline.recovery_factor:.2f} |")
        md.append(f"| **Avg Holding Time** | {baseline.avg_holding_minutes:.1f} min | **P95 Holding Time** | {baseline.p95_holding_minutes:.1f} min |")
        md.append("")

        # Exit breakdown
        md.append("### Exit Type Distribution")
        md.append("| Exit Reason | Count | Percentage |")
        md.append("| :--- | :--- | :--- |")
        for reason, count in baseline.exit_reasons_breakdown.items():
            pct = (count / max(1, baseline.total_trades)) * 100.0
            md.append(f"| `{reason}` | {count} | {pct:.1f}% |")
        md.append("")

        # 2. 9-Stage Ablation Study
        if ablation is not None:
            md.append("## 2. 9-Stage Component Ablation Study (§32)")
            md.append("> **Research Hypothesis Evaluation**:")
            verdict = "SUPPORTED" if ablation.primary_hypothesis_supported else "REJECTED"
            md.append(f"> **Primary Hypothesis (Translation Ratio)**: `{verdict}`")
            md.append(f"> - Δ Sharpe: `{ablation.primary_hypothesis_delta_sharpe:+.2f}`")
            md.append(f"> - Δ Win Rate: `{ablation.primary_hypothesis_delta_win_rate:+.1f}%`")
            md.append("")
            md.append("| Stage | Configuration | Description | Trades | Win Rate | Sharpe | Max DD | Δ Sharpe | Marginal Gain |")
            md.append("| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
            for s in ablation.stages:
                md.append(
                    f"| **{s.stage_letter}** | {s.config_name} | {s.description} | "
                    f"{s.metrics.total_trades} | {s.metrics.win_rate_pct:.1f}% | {s.metrics.annualized_sharpe:.2f} | "
                    f"{s.metrics.max_drawdown_pct:.1f}% | {s.delta_sharpe_vs_baseline:+.2f} | {s.marginal_sharpe_gain:+.2f} |"
                )
            md.append("")

        # 3. Rolling Walk-Forward Analysis
        if walk_forward is not None:
            md.append("## 3. Rolling Walk-Forward Validation (§31)")
            md.append(f"- **Total Folds**: `{walk_forward.total_folds}`")
            md.append(f"- **Mean In-Sample Sharpe**: `{walk_forward.mean_is_sharpe:.2f}`")
            md.append(f"- **Mean Out-Of-Sample Sharpe**: `{walk_forward.mean_oos_sharpe:.2f}`")
            md.append(f"- **Mean Walk-Forward Efficiency (WFE)**: `{walk_forward.mean_wfe:.2f}`")
            md.append(f"- **Mean Out-Of-Sample Win Rate**: `{walk_forward.mean_oos_win_rate:.1f}%`")
            md.append("")
            md.append("| Fold | Train Bars | Val Bars | Test Bars | IS Sharpe | OOS Sharpe | WFE | Overfit Suspected |")
            md.append("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
            for f in walk_forward.folds:
                flag = "⚠️ YES" if f.is_overfit_suspected else "✅ NO"
                md.append(
                    f"| {f.fold_index} | {f.train_bars_count} | {f.val_bars_count} | {f.test_bars_count} | "
                    f"{f.train_metrics.annualized_sharpe:.2f} | {f.test_metrics.annualized_sharpe:.2f} | "
                    f"{f.walk_forward_efficiency:.2f} | {flag} |"
                )
            md.append("")

        # 4. Robustness & Stress Testing
        if robustness is not None:
            md.append("## 4. Robustness & Stress Analysis (§33)")
            status = "⚠️ FRAGILE" if robustness.is_fragile else "✅ ROBUST"
            md.append(f"**Overall Resilience Verdict**: `{status}`")
            if robustness.fragility_reasons:
                md.append("**Risk Flags**:")
                for r in robustness.fragility_reasons:
                    md.append(f"- ⚠️ {r}")
                md.append("")

            md.append("### Transaction Cost Friction Stress")
            md.append("| Friction Multiplier | Net PnL (₹) | Profit Factor | Sharpe | Cost Drag % | Profitable? |")
            md.append("| :---: | :---: | :---: | :---: | :---: | :---: |")
            for c in robustness.cost_stress:
                prof = "✅ YES" if c.is_profitable else "❌ NO"
                md.append(f"| **{c.multiplier:.1f}x** | ₹{c.net_pnl:,.2f} | {c.profit_factor:.2f} | {c.annualized_sharpe:.2f} | {c.cost_drag_pct:.1f}% | {prof} |")
            md.append("")

            md.append("### Monte Carlo Simulation (1,000 Iterations)")
            md.append(f"- **P05 Max Drawdown**: `{robustness.monte_carlo.p05_max_dd_pct:.1f}%`")
            md.append(f"- **Median Max Drawdown**: `{robustness.monte_carlo.p50_max_dd_pct:.1f}%`")
            md.append(f"- **P95 Max Drawdown**: `{robustness.monte_carlo.p95_max_dd_pct:.1f}%`")
            md.append(f"- **Probability of Ruin (>25% Drawdown)**: `{robustness.monte_carlo.probability_of_ruin_pct:.1f}%`")
            md.append("")

        return "\n".join(md)

    def save_report(
        self,
        instrument: str,
        baseline: BacktestMetricsSummary,
        ablation: Optional[AblationStudyReport] = None,
        walk_forward: Optional[WalkForwardSummary] = None,
        robustness: Optional[RobustnessReport] = None,
        filename_prefix: str = "vortex_snap",
    ) -> Tuple[Path, Path]:
        """Saves both markdown and JSON reports."""
        md_text = self.generate_markdown(
            instrument=instrument,
            baseline=baseline,
            ablation=ablation,
            walk_forward=walk_forward,
            robustness=robustness,
        )
        md_path = self.output_dir / f"{filename_prefix}_{instrument.lower()}_report.md"
        md_path.write_text(md_text, encoding="utf-8")

        json_data = {
            "instrument": instrument,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "baseline": baseline.to_dict(),
            "ablation": ablation.to_dict() if ablation else None,
            "walk_forward": walk_forward.to_dict() if walk_forward else None,
            "robustness": robustness.to_dict() if robustness else None,
        }
        json_path = self.output_dir / f"{filename_prefix}_{instrument.lower()}_report.json"
        json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")

        return md_path, json_path
