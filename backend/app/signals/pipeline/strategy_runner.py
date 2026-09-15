"""
Strategy Runner Module for Quantitative Scanning Pipeline (Phase 3)
Executes registered strategies against StrategyContext and enforces:
  - Gap exemption filtering
  - Scalp confirmation gate
  - Participation Engine evaluation
  - Orthogonal Confluence Engine evaluation
  - Friction Gate edge evaluation
"""
from __future__ import annotations

from typing import Any
import structlog

from app.signals.orthogonal_confluence import orthogonal_confluence_engine
from app.signals.participation.oi_volume_engine import participation_engine
from app.signals.risk.friction_gate import friction_gate
from app.signals.scalp_confirmation import scalp_confirmation_engine
from app.signals.strategies import SCALP_STRATEGIES
from app.signals.strategies.base import SignalCandidate, Strategy, StrategyContext

logger = structlog.get_logger()

# Strategies exempt from the opening pre-market gap filter (valuable on gap days)
GAP_EXEMPT_STRATEGIES = {"GAMMA_SPIKE", "GAMMA_SQUEEZE", "ORB"}


def run_strategies(
    ctx: StrategyContext,
    strategies_to_run: dict[str, Strategy],
) -> tuple[list[SignalCandidate], list[str]]:
    """
    Executes detector on each strategy and applies immediate pre-qualification gates.
    Returns (candidates, rejected_gates).
    """
    candidates: list[SignalCandidate] = []
    rejected_gates: list[str] = []

    for strat_name, strat in strategies_to_run.items():
        try:
            candidate = strat.detect(ctx)
            if not candidate:
                continue

            # Propagate context flags to candidate
            candidate.fno_degraded = ctx.fno_degraded
            candidate.vwap_degraded = ctx.vwap_degraded
            candidate.vwap_coverage_pct = ctx.vwap_coverage_pct
            candidate.vix_percentile = getattr(ctx, "vix_percentile", None)
            candidate.lunch_session = getattr(ctx, "lunch_session", False)

            # Pre-market gap filter: suppress if gap > 0.5% within first 15m of session (except gap-exempt strategies)
            gap_pct_val = float(getattr(ctx, "pre_market_gap_pct", 0.0) or 0.0)
            is_opening_window = False
            if ctx.timestamp_ms:
                try:
                    utc_min = (ctx.timestamp_ms // 60000) % 1440
                    ist_min = (utc_min + 330) % 1440
                    is_opening_window = (555 <= ist_min <= 570)
                except Exception:
                    pass
            if gap_pct_val > 0.5 and is_opening_window and strat_name not in GAP_EXEMPT_STRATEGIES:
                rejected_gates.append(f"{strat_name}:GAP_TOO_LARGE_{gap_pct_val:.2f}pct")
                logger.info("candidate_rejected_gap", strategy=strat_name, underlying=getattr(ctx, "underlying", "UNKNOWN"), gap_pct=gap_pct_val)
                continue

            # Gating Fast Scalping setups through ScalpConfirmationEngine (§16)
            if candidate.is_scalp or strat_name in SCALP_STRATEGIES:
                confirm_res = scalp_confirmation_engine.validate(
                    candidate=candidate,
                    current_spot=ctx.spot_price,
                    regime=ctx.regime,
                    candle_timestamp_ms=ctx.timestamp_ms,
                )
                if not confirm_res.passed:
                    rejected_gates.append(f"{strat_name}:{confirm_res.reason_code or 'REJECTED'}")
                    logger.info(
                        "scalp_candidate_rejected_gate",
                        strategy=strat_name,
                        underlying=ctx.underlying,
                        reason=confirm_res.reason_code,
                        msg=confirm_res.rejection_message,
                    )
                    continue
                scalp_confirmation_engine.record_confirmed(candidate, candle_timestamp_ms=ctx.timestamp_ms)

            # Participation Engine (§18, §19)
            desk_type = "SCALP" if (candidate.is_scalp or strat_name in SCALP_STRATEGIES) else "INTRADAY"
            part_ctx = participation_engine.evaluate(
                direction=candidate.direction,
                desk=desk_type,
                rvol=ctx.feature_snapshot.rvol if ctx.feature_snapshot else 1.0,
                volume_acceleration=ctx.feature_snapshot.volume_acceleration if ctx.feature_snapshot else 0.0,
                price_change_pct=ctx.feature_snapshot.roc_1 if ctx.feature_snapshot else 0.0,
                fno_data=ctx.fno,
                candles=ctx.candles,
            )
            candidate.participation = part_ctx.model_dump()

            # Orthogonal Confluence Engine (§23, §24)
            conf_res = orthogonal_confluence_engine.evaluate(candidate, ctx.feature_snapshot, part_ctx)
            candidate.confluence_factors = conf_res.confirmed_factors
            if not conf_res.passed:
                rejected_gates.append(f"{strat_name}:REJECT_CONFLUENCE")
                logger.info("candidate_rejected_confluence", strategy=strat_name, underlying=ctx.underlying, reasons=conf_res.rejection_reasons)
                continue

            # Net Edge & Friction Gate (§27, §28)
            edge_res = friction_gate.evaluate(candidate)
            candidate.net_edge = edge_res.expected_net_edge_pts
            if not edge_res.passed:
                rejected_gates.append(f"{strat_name}:{edge_res.rejection_reason or 'REJECT_FRICTION'}")
                logger.info("candidate_rejected_friction", strategy=strat_name, underlying=ctx.underlying, reason=edge_res.rejection_reason)
                continue

            candidate.vwap_coverage_pct = ctx.vwap_coverage_pct
            candidate.context_snapshot = {
                "regime": ctx.regime,
                "fno": ctx.fno,
                "mtf": ctx.mtf,
                "indicators": ctx.indicators,
                "vwap": float(ctx.vwap) if ctx.vwap else float(ctx.spot_price),
                "volume_ma_20": ctx.volume_ma_20,
                "spot_price": float(ctx.spot_price),
            }
            candidates.append(candidate)
        except Exception as e:
            logger.warning("strategy_detect_failed", strategy=strat_name, underlying=getattr(ctx, "underlying", "UNKNOWN"), error=str(e))

    return candidates, rejected_gates
