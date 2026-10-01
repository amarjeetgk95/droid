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


def _explain_detect_none(ctx: StrategyContext, strat_name: str) -> str:
    """Read-only why-not diagnostic for a detect() that returned None.

    Mirrors the fail-closed entry filters of the 4 auto-scan strategies so the
    funnel can show the TRUE blocker (low volume, price near VWAP, ORB window
    closed, no squeeze/expansion, no close-beyond cross) instead of leaving
    400+ silent evaluations that make Feed Health look like 100% of the story.
    Never has side effects; never fabricates a candidate.
    """
    try:
        from app.signals.strategies.base import (
            extract_volume_ratio,
            extract_breakout_pressure,
            extract_adx,
            has_closed_1m_candle,
            VOLUME_BREAKOUT_MIN,
            VOLUME_MICRO_MIN,
            VOLUME_ORB_MIN,
            VOLUME_SCALP_MIN,
            ADX_TREND_CUTOFF,
        )
    except Exception:
        return f"{strat_name}:NO_SETUP_NO_EDGE"
    try:
        from decimal import Decimal
    except Exception:
        Decimal = None  # type: ignore[assignment]
    try:
        upper = str(strat_name or "").upper()
        # BREAKOUT is an alias for the same VOLATILITY_BREAKOUT logic.
        if upper in ("VOLATILITY_BREAKOUT", "BREAKOUT"):
            if ctx.timeframe not in ("5M", "15M", "1H"):
                return f"{strat_name}:NO_SETUP_WRONG_TIMEFRAME_{ctx.timeframe}"
            vol = extract_volume_ratio(ctx.indicators)
            if vol is None:
                return f"{strat_name}:NO_SETUP_NO_VOLUME_MEASURED"
            if vol < VOLUME_BREAKOUT_MIN:
                return f"{strat_name}:NO_SETUP_LOW_VOLUME_{vol:.2f}_LT_{VOLUME_BREAKOUT_MIN}"
            bp = extract_breakout_pressure(ctx.indicators)
            if bp is None:
                return f"{strat_name}:NO_SETUP_NO_PRESSURE"
            # Squeeze gate (mirror volatility_breakout._has_squeeze inputs).
            try:
                from app.signals.strategies.volatility_breakout import _has_squeeze as _vb_squeeze
                from app.signals.risk_engine import resolve_realistic_atr
                atr = resolve_realistic_atr(ctx.underlying, ctx.spot_price, ctx.indicators)
                if not _vb_squeeze(ctx, ctx.indicators, ctx.candles, atr):
                    return f"{strat_name}:NO_SETUP_NO_SQUEEZE"
            except Exception:
                pass
            # Expansion gate.
            try:
                candles = ctx.candles or []
                if len(candles) >= 4:
                    recent = [float(c.get("high", 0)) - float(c.get("low", 0)) for c in candles[-4:-1]]
                    avg_r = sum(recent) / max(1, len(recent))
                    last = candles[-1]
                    curr_r = float(last.get("high", 0)) - float(last.get("low", 0))
                    if not (curr_r >= avg_r * 1.10) and bp < 68:
                        return f"{strat_name}:NO_SETUP_NO_EXPANSION_R_{curr_r:.1f}_AVG_{avg_r:.1f}_P_{bp:.0f}"
            except Exception:
                pass
            return f"{strat_name}:NO_SETUP_NO_CLOSE_CROSS"
        if upper == "ORB":
            try:
                if ctx.timestamp_ms and ctx.timestamp_ms > 0:
                    utc_min = (int(ctx.timestamp_ms) // 60000) % 1440
                    ist_min = (utc_min + 330) % 1440
                    if ist_min < 570 or ist_min > 690:
                        return f"{strat_name}:NO_SETUP_ORB_WINDOW_CLOSED_IST_{ist_min}"
            except Exception:
                pass
            vol = extract_volume_ratio(ctx.indicators)
            if vol is None:
                return f"{strat_name}:NO_SETUP_NO_VOLUME_MEASURED"
            if vol < VOLUME_ORB_MIN:
                return f"{strat_name}:NO_SETUP_LOW_VOLUME_{vol:.2f}_LT_{VOLUME_ORB_MIN}"
            return f"{strat_name}:NO_SETUP_NO_OR_BREAK"
        if upper == "VWAP_SCALP":
            if ctx.timeframe not in ("1M", "3M"):
                return f"{strat_name}:NO_SETUP_WRONG_TIMEFRAME_{ctx.timeframe}"
            if not has_closed_1m_candle(ctx):
                return f"{strat_name}:NO_SETUP_FORMING_CANDLE"
            if ctx.regime in ("TREND_UP", "TREND_DOWN"):
                return f"{strat_name}:NO_SETUP_REGIME_TREND_{ctx.regime}"
            vol = extract_volume_ratio(ctx.indicators)
            if vol is None:
                # Mirror detect() candle fallback before declaring missing.
                try:
                    cur_v = float(ctx.candles[-1].get("volume", 0)) if ctx.candles else None
                    ma_v = ctx.volume_ma_20
                    if cur_v and ma_v and ma_v > 0:
                        vol = cur_v / ma_v
                except Exception:
                    vol = None
                if vol is None:
                    return f"{strat_name}:NO_SETUP_NO_VOLUME_MEASURED"
            if vol < VOLUME_SCALP_MIN:
                return f"{strat_name}:NO_SETUP_LOW_VOLUME_{vol:.2f}_LT_{VOLUME_SCALP_MIN}"
            vwap_val = ctx.vwap
            if vwap_val is None:
                try:
                    raw = ctx.indicators.get("vwap") or ctx.indicators.get("trend", {}).get("vwap")
                    if raw is None:
                        return f"{strat_name}:NO_SETUP_NO_VWAP"
                except Exception:
                    return f"{strat_name}:NO_SETUP_NO_VWAP"
            else:
                try:
                    from decimal import Decimal
                    dev = abs(ctx.spot_price - vwap_val) / abs(vwap_val) * Decimal("100")
                    if dev < Decimal("0.3"):
                        return f"{strat_name}:NO_SETUP_VWAP_NOT_STRETCHED_{float(dev):.2f}PCT"
                except Exception:
                    pass
            return f"{strat_name}:NO_SETUP_NO_REJECTION_WICK"
        if upper in ("MICRO_MOMENTUM", "MOMENTUM_REACCELERATION"):
            # Both suppress on RANGE/LOW_VOL before any structure is read, and
            # both are volume-gated on the PIT-reconciled rvol. Reporting the
            # real blocker matters: a blanket NO_SETUP_NO_EDGE here previously
            # hid a structurally impossible volume gate behind 288 identical
            # "no edge" lines.
            if ctx.timeframe != "1M":
                return f"{strat_name}:NO_SETUP_WRONG_TIMEFRAME_{ctx.timeframe}"
            if not has_closed_1m_candle(ctx):
                return f"{strat_name}:NO_SETUP_FORMING_CANDLE"
            if ctx.regime in ("RANGE", "LOW_VOL"):
                return f"{strat_name}:NO_SETUP_REGIME_RANGE_{ctx.regime}"
            vol = extract_volume_ratio(ctx.indicators)
            if vol is None:
                return f"{strat_name}:NO_SETUP_NO_VOLUME_MEASURED"
            need = VOLUME_MICRO_MIN if upper == "MICRO_MOMENTUM" else VOLUME_SCALP_MIN
            if vol < need:
                return f"{strat_name}:NO_SETUP_LOW_VOLUME_{vol:.2f}_LT_{need}"
            return f"{strat_name}:NO_SETUP_NO_STRUCTURE"
        if upper == "TREND_PULLBACK":
            try:
                adx = extract_adx(ctx.indicators)
                if adx is not None and adx < ADX_TREND_CUTOFF:
                    return f"{strat_name}:NO_SETUP_LOW_ADX_{adx:.1f}_LT_{ADX_TREND_CUTOFF}"
            except Exception:
                pass
            try:
                trend_data = ctx.indicators.get("trend", {}) or {}
                ema20, ema50 = trend_data.get("ema20"), trend_data.get("ema50")
                if ema20 is not None and ema50 is not None:
                    if Decimal(str(ema20)) <= Decimal(str(ema50)):
                        return f"{strat_name}:NO_SETUP_NO_RIBBON_EMA20<=EMA50"
                    dist = abs(ctx.spot_price - Decimal(str(ema20))) / ctx.spot_price * Decimal("100")
                    if dist > Decimal("0.6"):
                        return f"{strat_name}:NO_SETUP_FAR_FROM_EMA20_{float(dist):.2f}PCT_GT_0.6"
            except Exception:
                pass
            return f"{strat_name}:NO_SETUP_NO_EDGE"
        if upper == "MEAN_REVERSION":
            try:
                rsi = float((ctx.indicators.get("momentum", {}) or {}).get("rsi") or ctx.indicators.get("rsi") or 50.0)
                bb_l = (ctx.indicators.get("volatility", {}) or {}).get("bollinger_lower")
                if bb_l is not None and float(ctx.spot_price) < float(bb_l) and rsi > 35.0:
                    return f"{strat_name}:NO_SETUP_RSI_NOT_EXTREME_{rsi:.0f}"
                if bb_l is not None and float(ctx.spot_price) >= float(bb_l):
                    return f"{strat_name}:NO_SETUP_NOT_AT_BAND"
            except Exception:
                pass
            return f"{strat_name}:NO_SETUP_NO_EDGE"
    except Exception:
        pass
    return f"{strat_name}:NO_SETUP_NO_EDGE"


def run_strategies(
    ctx: StrategyContext,
    strategies_to_run: dict[str, Strategy],
) -> tuple[list[SignalCandidate], list[str]]:
    """
    Executes detector on each strategy and applies immediate pre-qualification gates.
    Returns (candidates, rejected_gates).

    rejected_gates includes NO_SETUP_* codes for detect()->None so the funnel
    shows true entry-filter blockers. Callers must NOT count NO_SETUP_* as
    detected candidates (see scanner.py) — no candidate ever existed.
    """
    candidates: list[SignalCandidate] = []
    rejected_gates: list[str] = []

    for strat_name, strat in strategies_to_run.items():
        try:
            candidate = strat.detect(ctx)
            if not candidate:
                rejected_gates.append(_explain_detect_none(ctx, strat_name))
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
            if gap_pct_val > 1.5 and is_opening_window and strat_name not in GAP_EXEMPT_STRATEGIES:
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

            if candidate.path_simulation is None:
                candidate.path_simulation = {
                    "is_economically_viable": edge_res.passed,
                    "net_reward_risk_ratio": edge_res.net_reward_risk_ratio,
                    "total_friction_pts": edge_res.total_friction_pts,
                    "expected_net_edge_pts": edge_res.expected_net_edge_pts,
                    "cost_to_target_ratio_pct": edge_res.cost_to_target_ratio_pct,
                    "viability_rationale": [edge_res.rejection_reason] if edge_res.rejection_reason else [],
                    "breakdown": edge_res.breakdown,
                }

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
