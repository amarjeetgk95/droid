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

from app.services.calendar_service import calendar_service

from app.signals.orthogonal_confluence import orthogonal_confluence_engine
from app.signals.pipeline.contract_greeks import attach_chain_implied_greeks
from app.signals.participation.oi_volume_engine import participation_engine
from app.signals.risk.friction_gate import friction_gate
from app.signals.scalp_confirmation import scalp_confirmation_engine
from app.signals.safety.clocks import IST as IST_TZ
from app.signals.strategies import SCALP_STRATEGIES
from app.signals.strategies.base import SignalCandidate, Strategy, StrategyContext

logger = structlog.get_logger()

# Strategies exempt from the opening pre-market gap filter (valuable on gap days).
# Single source of truth — scanner.py imports this symbol, do not duplicate it there.
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

            # Chain-implied Greeks for fallback contracts: detectors resolve
            # via resolve_option_contract (no chain quotes reach the
            # quantitative selector, so it fail-closes to None) leaving
            # greeks=None, which the friction gate hard-fails (NO_LIVE_IV).
            # Solve IV from the live chain premium — market-implied, never
            # defaulted. Best-effort: failure keeps greeks=None and the
            # candidate stays subject to the usual fail-closed gates.
            greeks_gap = attach_chain_implied_greeks(candidate)
            if greeks_gap:
                logger.debug(
                    "candidate_no_chain_greeks",
                    strategy=strat_name,
                    underlying=getattr(ctx, "underlying", "UNKNOWN"),
                    reason=greeks_gap,
                )

            # Pre-market gap filter: suppress if gap > 0.5% within first 15m of session (except gap-exempt strategies).
            # Gap window is resolved from the exchange calendar (IST session open), not manual minute math,
            # so special sessions (e.g. Muhurat) anchor correctly.
            gap_pct_val = float(getattr(ctx, "pre_market_gap_pct", 0.0) or 0.0)
            is_opening_window = False
            if ctx.timestamp_ms:
                try:
                    from datetime import datetime

                    decision_ist = datetime.fromtimestamp(float(ctx.timestamp_ms) / 1000.0, tz=IST_TZ)
                    session_info = calendar_service.get_session_info(decision_ist.date())
                    if session_info.market_open is not None:
                        elapsed_s = (decision_ist - session_info.market_open).total_seconds()
                        is_opening_window = 0 <= elapsed_s <= 15 * 60
                except Exception:
                    is_opening_window = False
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

            # Participation Engine (§18, §19) — fail closed without a feature snapshot.
            # Never default rvol=1.0 / vol_accel=0 / roc=0: invented neutrality is fabrication.
            if ctx.feature_snapshot is None:
                rejected_gates.append(f"{strat_name}:MISSING_FEATURE_SNAPSHOT")
                logger.info("candidate_rejected_no_features", strategy=strat_name, underlying=ctx.underlying)
                continue
            desk_type = "SCALP" if (candidate.is_scalp or strat_name in SCALP_STRATEGIES) else "INTRADAY"
            part_ctx = participation_engine.evaluate(
                direction=candidate.direction,
                desk=desk_type,
                rvol=ctx.feature_snapshot.rvol,
                volume_acceleration=ctx.feature_snapshot.volume_acceleration,
                price_change_pct=ctx.feature_snapshot.roc_1,
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
            # Full PIT context snapshot: downstream enrichment/validation must see the
            # exact candles, quote timestamp, and data quality behind this decision.
            # vwap propagates None when unavailable — never fallback to spot (fabrication).
            candidate.context_snapshot = {
                "regime": ctx.regime,
                "fno": ctx.fno,
                "mtf": ctx.mtf,
                "indicators": ctx.indicators,
                "vwap": float(ctx.vwap) if ctx.vwap is not None else None,
                "volume_ma_20": ctx.volume_ma_20,
                "spot_price": float(ctx.spot_price),
                "timestamp_ms": ctx.timestamp_ms,
                "candles": ctx.candles,
                "quote_timestamp_ms": getattr(ctx, "quote_timestamp_ms", None),
                "data_quality": getattr(ctx, "data_quality", None),
            }
            candidates.append(candidate)
        except Exception as e:
            logger.warning("strategy_detect_failed", strategy=strat_name, underlying=getattr(ctx, "underlying", "UNKNOWN"), error=str(e))

    return candidates, rejected_gates
