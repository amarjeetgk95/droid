"""Strategy promotion gate: single source of truth for re-enabling a strategy.

A research-only strategy may flip STRATEGY_ENABLED False->True ONLY with a
Gate-G2 PASSED report. Thresholds are imported from gate_g2_evaluator so the
two can never drift: trades>=25, PF>=1.10, DD<=20%, DSR>=0.40, survive to
>=1.5x costs, >=2/3 barrier variants positive.

This module is deliberately polars-free: it judges a metrics dict, so the
scanner, API, and scripts can all call it without a dataframe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.quant.validation.gate_g2_evaluator import (
    MAX_DRAWDOWN,
    MIN_DSR,
    MIN_PROFIT_FACTOR,
    MIN_TRADES,
    REQUIRED_SURVIVAL_MULTIPLIER,
)

PromotionVerdict = Literal["PASSED", "FAILED", "INCONCLUSIVE"]


@dataclass
class PromotionDecision:
    strategy_key: str
    verdict: PromotionVerdict
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_key": self.strategy_key,
            "verdict": self.verdict,
            "reasons": self.reasons,
        }


def evaluate_strategy_promotion(
    strategy_key: str,
    metrics: dict[str, Any],
) -> PromotionDecision:
    """Judge a G2-style metrics dict. Fail-closed on missing keys."""
    reasons: list[str] = []
    verdict: PromotionVerdict = "PASSED"

    def _num(key: str) -> float | None:
        try:
            v = metrics.get(key)
            return None if v is None else float(v)
        except (TypeError, ValueError):
            return None

    trades_raw = metrics.get("total_trades")
    try:
        trades = int(trades_raw) if trades_raw is not None else None
    except (TypeError, ValueError):
        trades = None

    if trades is None:
        return PromotionDecision(strategy_key, "FAILED", ["Missing total_trades: cannot promote without a sample."])

    if trades < MIN_TRADES:
        return PromotionDecision(
            strategy_key,
            "INCONCLUSIVE",
            [f"Sample underpowered: {trades} trades (need >= {MIN_TRADES})."],
        )

    net_exp = _num("net_expectancy_pct")
    pf = _num("profit_factor")
    dd = _num("max_drawdown_pct")
    dsr = _num("deflated_sharpe_ratio")
    survival = _num("cost_survival_max_multiplier")
    sens_pass = metrics.get("sensitivity_pass_count")
    try:
        sens_pass_n: int | None = int(sens_pass) if sens_pass is not None else None
    except (TypeError, ValueError):
        sens_pass_n = None

    missing = [k for k, v in (
        ("net_expectancy_pct", net_exp),
        ("profit_factor", pf),
        ("max_drawdown_pct", dd),
        ("deflated_sharpe_ratio", dsr),
        ("cost_survival_max_multiplier", survival),
    ) if v is None]
    if missing:
        return PromotionDecision(
            strategy_key, "FAILED", [f"Missing metrics {missing}: fail-closed, no promotion."]
        )

    assert net_exp is not None and pf is not None and dd is not None
    assert dsr is not None and survival is not None

    if net_exp <= 0.0:
        verdict = "FAILED"
        reasons.append(f"Negative base net expectancy: {net_exp * 100:.3f}%.")
    if pf < MIN_PROFIT_FACTOR:
        verdict = "FAILED"
        reasons.append(f"Profit factor {pf:.2f} below minimum {MIN_PROFIT_FACTOR:.2f}.")
    if dd > MAX_DRAWDOWN:
        verdict = "FAILED"
        reasons.append(f"Drawdown {dd * 100:.1f}% exceeds {MAX_DRAWDOWN * 100:.0f}% limit.")
    if dsr < MIN_DSR:
        verdict = "FAILED"
        reasons.append(f"Deflated Sharpe {dsr:.2f} below {MIN_DSR:.2f} (multiple-testing aware).")
    if survival < REQUIRED_SURVIVAL_MULTIPLIER:
        verdict = "FAILED"
        reasons.append(
            f"Cost fragility: survives only to {survival:.2f}x "
            f"(need >= {REQUIRED_SURVIVAL_MULTIPLIER:.2f}x)."
        )
    if sens_pass_n is not None and sens_pass_n < 2:
        verdict = "FAILED"
        reasons.append(f"Parameter sensitivity: only {sens_pass_n}/3 variants positive.")
    if verdict == "PASSED":
        reasons.append(
            f"Robust: survives to {survival:.2f}x costs, DSR {dsr:.2f}."
        )
    return PromotionDecision(strategy_key, verdict, reasons)


def is_strategy_promotable(metrics: dict[str, Any]) -> bool:
    """True only on PASSED. INCONCLUSIVE and FAILED both block promotion."""
    return evaluate_strategy_promotion(metrics.get("strategy_key", "UNKNOWN"), metrics).verdict == "PASSED"
