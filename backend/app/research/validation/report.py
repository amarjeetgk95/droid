"""Experiment report formatting utilities for the Research Laboratory."""

from typing import Any, Dict
from app.research.models import ExperimentRun, ValidationReport


def format_validation_markdown(run: ExperimentRun, report: ValidationReport, indicator_name: str) -> str:
    """Format validation outcome into a clear, scannable Markdown report (§21)."""
    sig_badge = "[PASS: STATISTICALLY SIGNIFICANT]" if report.is_statistically_significant else "[FAIL: NOT SIGNIFICANT]"

    md = [
        f"# Research Validation Report: {indicator_name}",
        f"**Run ID**: `{run.run_id}` | **Status**: `{run.status.value}`",
        f"**Samples Evaluated**: {report.sample_size}",
        "",
        "## Statistical Verification",
        f"- **Statistical Edge**: **{sig_badge}**",
        f"- **Indicator Accuracy**: `{report.accuracy}%` (95% CI: `[{report.confidence_interval_95[0]}%, {report.confidence_interval_95[1]}%]` )",
        f"- **Empirical Baseline Accuracy**: `{report.baseline_accuracy}%`",
        f"- **Excess Accuracy**: `{report.excess_accuracy:+0.2f}%`",
        f"- **p-value**: `{report.p_value:.4f}` (alpha = 0.05)",
        "",
        "## Performance Metrics",
        f"- **Precision**: `{report.precision}%`",
        f"- **Recall**: `{report.recall}%`",
        f"- **F1 Score**: `{report.f1_score}%`",
        f"- **Mean Favorable Excursion (MFE)**: `{report.mfe_mean}` pts",
        f"- **Mean Adverse Excursion (MAE)**: `{report.mae_mean}` pts",
        f"- **Win / Loss Ratio**: `{report.win_loss_ratio}`",
        "",
        "## Market Session Breakdown",
        "| Session | Sample Size | Accuracy |",
        "|---|---|---|",
    ]

    for sess, stats in report.session_breakdown.items():
        md.append(f"| {sess} | {int(stats['sample_size'])} | {stats['accuracy']}% |")

    md.extend([
        "",
        "## Market Regime Breakdown",
        "| Regime | Sample Size | Accuracy |",
        "|---|---|---|",
    ])

    for reg, stats in report.regime_breakdown.items():
        md.append(f"| {reg} | {int(stats['sample_size'])} | {stats['accuracy']}% |")

    return "\n".join(md)
