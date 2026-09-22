"""
Real-Time Multi-Asset & Multi-Strategy Scanner Engine
Evaluates NIFTY, BANKNIFTY, SENSEX across all 5 Quant Strategies against live market data.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import UTC, datetime
from datetime import time as dt_time
from decimal import Decimal
from typing import Any

import structlog

from app.signals.confluence import ARMED_THRESHOLD, confluence_engine
from app.signals.contract_resolver import APPROVED_UNDERLYINGS, validate_underlying
from app.signals.features.engine import compute_feature_snapshot
from app.signals.fsm import SignalInstance, signal_fsm
from app.signals.orthogonal_confluence import orthogonal_confluence_engine
from app.signals.participation.oi_volume_engine import participation_engine
from app.signals.risk.cross_desk_arbiter import cross_desk_arbiter
from app.signals.risk.friction_gate import friction_gate
from app.signals.scalp_confirmation import scalp_confirmation_engine
from app.signals.strategies import (
    INTRADAY_STRATEGIES,
    SCALP_STRATEGIES,
    STRATEGY_ENABLED,
    STRATEGY_REGISTRY,
)
from app.signals.strategies.base import SignalCandidate, StrategyContext
from app.signals.pipeline import (
    acquire_market_context,
    run_strategies,
    build_signal_instance,
    register_and_notify,
    enrich_candidate,
    # Single-sourced from the pipeline package — do not redefine here.
    GAP_EXEMPT_STRATEGIES,
    ScanDiagnostics,
    is_fallback_quote,
    GateChain,
    FeedCircuitGate,
    FNOIntegrityGate,
    DeskConcurrencyGate,
    PortfolioConcurrencyGate,
    CrossDeskArbiterGate,
    RSIGate,
    MarketStructureGate,
    TriggerIntegrityGate,
    OptionViabilityGate,
    ChainMarkGate,
)

logger = structlog.get_logger()

# NOTE: GAP_EXEMPT_STRATEGIES and ScanDiagnostics are imported from
# app.signals.pipeline (single source of truth) and re-exported here so
# existing `from app.signals.scanner import ...` call sites keep working.


class SignalScanner:
    """
    Dual-Cadence Quantitative Scanner Engine:
      - Scalp Desk (1M / 3M): VWAP Rejection, Micro-Momentum, EMA Ribbon, Gamma Spike
      - Intraday Desk (5M / 15M): Breakout, Mean Reversion, Trend Pullback, Gamma Squeeze, ORB
    """

    def __init__(self, scan_cache_ttl_s: float = 10.0):
        self._last_diagnostics: dict[str, ScanDiagnostics] = {}
        self._scan_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._scan_cache_ttl_s = scan_cache_ttl_s
        self._market_svc: Any = None
        self._daily_funnel_date: str = ""
        self._daily_funnel: dict[str, Any] = {}
        self._init_daily_funnel()

    def _init_daily_funnel(self) -> None:
        today_str = datetime.now(UTC).strftime("%Y-%m-%d")
        self._daily_funnel_date = today_str
        self._daily_funnel = {
            "date": today_str,
            "data_since": datetime.now(UTC).isoformat(),
            "opportunities_evaluated": 0,
            "candidates_found": 0,
            "stages": {
                "evaluated": 0,
                "candidates": 0,
                "strategy_qualified": 0,
                "pre_risk_passed": 0,
                "risk_passed": 0,
                "post_risk_passed": 0,
                "enrichment_passed": 0,
                "confirmed": 0,
            },
            "rejections": defaultdict(int),
            "strategy_stats": defaultdict(lambda: {
                "evaluated": 0,
                "candidates": 0,
                "strategy_qualified": 0,
                "risk_passed": 0,
                "confirmed": 0,
            }),
            "underlying_stats": defaultdict(lambda: {
                "evaluated": 0,
                "candidates": 0,
                "confirmed": 0,
            }),
        }

    def _check_rollover(self) -> None:
        today_str = datetime.now(UTC).strftime("%Y-%m-%d")
        if self._daily_funnel_date != today_str:
            self._init_daily_funnel()

    def _record_rejection(self, raw_reason: str, count: int = 1) -> None:
        self._check_rollover()
        self._daily_funnel["rejections"][raw_reason] += count

    @staticmethod
    def _categorize_rejection(code: str) -> tuple[str, str]:
        upper = code.upper()
        if "MARKET_CLOSED" in upper or "CALENDAR" in upper:
            return "Market Closed", "Session is closed or outside authorized trading window"
        if "MARKET_DATA_OFFLINE" in upper or "FEED" in upper or "CIRCUIT" in upper or "STALE" in upper:
            return "Feed Health / Circuit", "Market feed stale, offline, or circuit health check degraded"
        if "GAP" in upper:
            return "Opening Gap Hurdle", "Gap > 0.5% during first 15 minutes of trading session"
        if "CONFLUENCE" in upper or "ORTHOGONAL" in upper:
            return "Orthogonal Confluence", "Multi-factor agreement (trend, momentum, orderflow) insufficient"
        if "FRICTION" in upper or "NET_EDGE" in upper:
            return "Friction & Cost Hurdle", "Expected gross edge does not clear transaction frictions"
        if "RISK_REWARD" in upper or "RR_" in upper or "MIN_RR" in upper or "INSUFFICIENT" in upper:
            return "Risk / Reward Insufficient", "Setup does not satisfy institutional minimum risk-to-reward ratio"
        if "RSI" in upper:
            return "RSI Gate Alignment", "Extreme RSI reading violates directional boundary conditions"
        if "VWAP" in upper:
            return "VWAP Regime Alignment", "Candle / trend relationship to VWAP conflicts with entry"
        if "TRIGGER" in upper or "NO_EDGE" in upper or "DISTANCE" in upper:
            return "Trigger Integrity", "Trigger distance or price condition has no actionable edge"
        if "CONCURRENCY" in upper or "MAX_POSITIONS" in upper:
            return "Concurrency Limit", "Maximum concurrent active positions on desk reached"
        if "FNO" in upper or "OPTION_MARK" in upper or "CHAIN" in upper or "VIABILITY" in upper:
            return "Option Viability & Mark", "Option liquidity, spread or broker mark unviable"
        if "STRUCTURE" in upper:
            return "Market Structure Conflict", "Higher-timeframe structure opposes local signal"
        if "CONFLICT" in upper:
            return "Directional Conflict", "Conflicting candidate on same underlying dropped by resolver"
        if "FACTORY" in upper or "REGISTRATION" in upper:
            return "Safety & Guard Rejection", "Pre-trade safety gate or factory validation blocked signal"

        clean = code.split(":")[-1].replace("_", " ").title()
        return clean, f"Filtered by {clean}"

    def get_funnel_analytics(
        self,
        strategy_filter: str | None = None,
        underlying_filter: str | None = None,
    ) -> dict[str, Any]:
        self._check_rollover()

        stages = dict(self._daily_funnel["stages"])
        rejections = dict(self._daily_funnel["rejections"])
        strategy_stats = {k: dict(v) for k, v in self._daily_funnel["strategy_stats"].items()}
        underlying_stats = {k: dict(v) for k, v in self._daily_funnel["underlying_stats"].items()}

        if strategy_filter:
            strat_upper = strategy_filter.upper()
            rejections = {k: v for k, v in rejections.items() if k.upper().startswith(strat_upper + ":")}

        blocker_groups: dict[str, dict[str, Any]] = {}
        for code, count in rejections.items():
            category, description = self._categorize_rejection(code)
            if category not in blocker_groups:
                blocker_groups[category] = {
                    "name": category,
                    "description": description,
                    "count": 0,
                    "sample_code": code,
                }
            blocker_groups[category]["count"] += count

        sorted_blockers = sorted(blocker_groups.values(), key=lambda x: x["count"], reverse=True)
        total_rejections = sum(b["count"] for b in sorted_blockers)
        for b in sorted_blockers:
            b["percentage"] = round((b["count"] / total_rejections * 100.0), 1) if total_rejections > 0 else 0.0

        candidates = stages.get("candidates", 0)
        confirmed = stages.get("confirmed", 0)
        conversion_rate = round((confirmed / candidates * 100.0), 2) if candidates > 0 else 0.0

        try:
            from app.signals.outcome_tracker import outcome_tracker
            perf = outcome_tracker.get_performance_metrics()
            perf_dict = perf.strategy_breakdown or {}
        except Exception:
            perf_dict = {}

        all_strats: list[dict[str, Any]] = []
        for name in sorted(STRATEGY_REGISTRY.keys()):
            is_enabled = STRATEGY_ENABLED.get(name, False)
            desk = "SCALP" if name in SCALP_STRATEGIES else "INTRADAY"
            stats = strategy_stats.get(name, {
                "evaluated": 0,
                "candidates": 0,
                "strategy_qualified": 0,
                "risk_passed": 0,
                "confirmed": 0,
            })
            p_data = perf_dict.get(name, {})
            all_strats.append({
                "strategy": name,
                "desk": desk,
                "enabled": is_enabled,
                "evaluated": stats.get("evaluated", 0),
                "candidates": stats.get("candidates", 0),
                "strategy_qualified": stats.get("strategy_qualified", 0),
                "risk_passed": stats.get("risk_passed", 0),
                "confirmed": stats.get("confirmed", 0),
                "total_trades": p_data.get("total", 0),
                "wins": p_data.get("wins", 0),
                "losses": p_data.get("losses", 0),
                "win_rate_pct": p_data.get("win_rate", 0.0),
            })

        return {
            "date": self._daily_funnel_date,
            "data_since": self._daily_funnel["data_since"],
            "opportunities_evaluated": self._daily_funnel["opportunities_evaluated"],
            "total_candidates_found": self._daily_funnel["candidates_found"],
            "total_confirmed": confirmed,
            "conversion_rate_pct": conversion_rate,
            "stages": stages,
            "top_blockers": sorted_blockers[:10],
            "raw_rejections": [
                {"code": k, "count": v}
                for k, v in sorted(rejections.items(), key=lambda x: x[1], reverse=True)[:25]
            ],
            "strategy_performance": all_strats,
            "underlying_stats": underlying_stats,
        }

    def _get_market_svc(self) -> Any:
        if self._market_svc is None:
            from app.services.market_service import MarketService
            self._market_svc = MarketService()
        return self._market_svc

    def get_last_diagnostics(self) -> dict[str, Any]:
        return {k: v.model_dump() for k, v in self._last_diagnostics.items()}

    @staticmethod
    def _is_fallback_quote(quote: Any) -> bool:
        # Thin compat wrapper — logic is single-sourced in pipeline.data_acquisition.
        return bool(is_fallback_quote(quote))

    async def scan_instrument(
        self,
        underlying: str,
        timeframe: str = "5M",
        desk: str | None = None,
    ) -> list[SignalCandidate]:
        self._check_rollover()
        u = validate_underlying(underlying)
        ctx, diag = await acquire_market_context(u, timeframe, self._get_market_svc())
        self._last_diagnostics[f"{u}:{timeframe}"] = diag
        if not ctx:
            self._record_rejection(f"{u}:MARKET_DATA_OFFLINE_{diag.data_quality}")
            return []

        # Select strategies according to desk and timeframe, then enforce the
        # institutional freeze fail-closed: only STRATEGY_ENABLED=True names run.
        # Research-only strategies stay importable for manual/backtest use.
        if desk == "SCALP" or timeframe in ("1M", "3M"):
            strategies_to_run = SCALP_STRATEGIES
        elif desk == "INTRADAY" or timeframe in ("5M", "15M", "1H"):
            strategies_to_run = INTRADAY_STRATEGIES
        else:
            strategies_to_run = STRATEGY_REGISTRY

        strategies_to_run = {
            name: strat
            for name, strat in strategies_to_run.items()
            if STRATEGY_ENABLED.get(name, False) is True
        }

        num_strats = len(strategies_to_run)
        self._daily_funnel["opportunities_evaluated"] += num_strats
        self._daily_funnel["stages"]["evaluated"] += num_strats
        self._daily_funnel["underlying_stats"][u]["evaluated"] += num_strats
        for s_name in strategies_to_run:
            self._daily_funnel["strategy_stats"][s_name]["evaluated"] += 1

        diag.strategies_evaluated = len(strategies_to_run)
        candidates, rejected = run_strategies(ctx, strategies_to_run)
        diag.candidates_found = len(candidates)
        diag.reasons.extend(rejected)

        for cand in candidates:
            self._daily_funnel["candidates_found"] += 1
            self._daily_funnel["stages"]["candidates"] += 1
            self._daily_funnel["stages"]["strategy_qualified"] += 1
            self._daily_funnel["strategy_stats"][cand.strategy]["candidates"] += 1
            self._daily_funnel["strategy_stats"][cand.strategy]["strategy_qualified"] += 1
            self._daily_funnel["underlying_stats"][u]["candidates"] += 1

        for rej in rejected:
            self._record_rejection(rej)
            strat = rej.split(":", 1)[0] if ":" in rej else None
            if strat:
                self._daily_funnel["candidates_found"] += 1
                self._daily_funnel["stages"]["candidates"] += 1
                self._daily_funnel["strategy_stats"][strat]["candidates"] += 1
                self._daily_funnel["underlying_stats"][u]["candidates"] += 1

        return candidates

    async def _process_candidates(self, candidates: list[SignalCandidate]) -> tuple[list[SignalInstance], list[str]]:
        """Validates confluence + trigger integrity, registers passing candidates into FSM.

        Returns (registered, rejected_reasons). Rejections (no-edge triggers etc.)
        are surfaced in scan diagnostics instead of silently vanishing.
        """
        self._check_rollover()
        from app.services.calendar_service import calendar_service
        perm = calendar_service.can_trade_now()
        if not perm.allowed:
            logger.info("process_candidates_rejected_market_closed", reason=perm.reason)
            reason_str = f"MARKET_CLOSED_{perm.reason}"
            for c in candidates:
                self._record_rejection(f"{c.strategy}:{reason_str}")
            return [], [reason_str]

        from app.algo.signal_fusion import conflict_resolver
        from app.signals.risk_engine import StrategySetup, central_risk_engine

        registered_signals: list[SignalInstance] = []
        rejected_gates: list[str] = []

        candidates, dropped_conflicts = conflict_resolver.resolve_candidate_conflicts(candidates, tie_epsilon=5.0)
        if dropped_conflicts:
            rejected_gates.extend(dropped_conflicts)
            for d in dropped_conflicts:
                self._record_rejection(f"CONFLICT:{d}")

        pre_risk_chain = GateChain([
            FeedCircuitGate(),
            FNOIntegrityGate(),
            DeskConcurrencyGate(),
            PortfolioConcurrencyGate(),
            CrossDeskArbiterGate(),
        ])

        post_risk_chain = GateChain([
            RSIGate(),
            MarketStructureGate(),
            TriggerIntegrityGate(),
            OptionViabilityGate(),
            ChainMarkGate(),
        ])

        for cand in candidates:
            # 1. Evaluate Pre-Risk Gates
            passed_pre, results_pre = pre_risk_chain.evaluate(cand, registered_in_flight=registered_signals)
            fno_is_degraded = getattr(cand, "fno_degraded", False)
            for r in results_pre:
                if not r.passed and r.reason_code:
                    rejected_gates.append(f"{cand.strategy}:{r.reason_code}")
                    self._record_rejection(f"{cand.strategy}:{r.reason_code}")
                elif r.reason_code == "ARMED_BLOCKED_FNO_DEGRADED":
                    rejected_gates.append(f"{cand.strategy}:{r.reason_code}")
                    self._record_rejection(f"{cand.strategy}:{r.reason_code}")
            if not passed_pre:
                continue
            self._daily_funnel["stages"]["pre_risk_passed"] += 1

            # 2. Centralized Risk Engine Validation
            cand_greeks = getattr(cand, "greeks", {}) or {}
            strat_setup = StrategySetup(
                strategy_name=cand.strategy,
                underlying=cand.underlying,
                direction=cand.direction,
                timeframe=cand.timeframe,
                is_scalp=cand.is_scalp,
                spot_price=cand.spot_price,
                entry_trigger=cand.trigger,
                raw_structural_stop=cand.stop_loss,
                structural_target_candidates=[cand.target_1, cand.target_2],
                atr_5m=Decimal(str(round(float(cand.risk_points or 20.0), 2))),
                confidence=cand.overall_confidence,
                option_delta=cand_greeks.get("delta"),
                option_theta_hour=cand_greeks.get("theta_hour"),
                option_premium=cand_greeks.get("theoretical_price"),
                option_iv=cand_greeks.get("iv"),
            )
            overlay = None
            try:
                from app.event_engine.risk_overlay import event_risk_overlay_service
                from app.event_engine.service import event_engine_service
                events = event_engine_service.get_today_events()
                overlay = event_risk_overlay_service.evaluate_overlay(cand.underlying, events)
            except Exception as ev_err:
                logger.debug("event_overlay_eval_skipped", underlying=cand.underlying, error=str(ev_err))

            risk_decision = central_risk_engine.evaluate(strat_setup, event_overlay=overlay)
            if not risk_decision.accepted:
                reason_str = f"{cand.strategy}:{risk_decision.rejection_reason}"
                rejected_gates.append(reason_str)
                self._record_rejection(reason_str)
                logger.info(
                    "candidate_rejected_risk_engine",
                    strategy=cand.strategy,
                    underlying=cand.underlying,
                    reason=risk_decision.rejection_reason,
                    event_state=getattr(overlay, "proximity_state", "UNKNOWN") if overlay else "NONE",
                )
                continue
            self._daily_funnel["stages"]["risk_passed"] += 1
            self._daily_funnel["strategy_stats"][cand.strategy]["risk_passed"] += 1

            # Update candidate parameters from risk decision
            cand.stop_loss = risk_decision.stop_loss
            cand.target_1 = risk_decision.target_1
            cand.target_2 = risk_decision.target_2
            cand.risk_points = Decimal(str(risk_decision.risk_points))
            cand.risk_reward_t1 = risk_decision.risk_reward_t1
            cand.risk_reward_t2 = risk_decision.risk_reward_t2
            cand.ttl_seconds = max(cand.ttl_seconds or 300, risk_decision.trigger_ttl_seconds)
            cand.time_stop_seconds = max(getattr(cand, "time_stop_seconds", 0) or 0, risk_decision.active_time_stop_seconds)

            # 3. Evaluate Post-Risk Gates
            passed_post, results_post = post_risk_chain.evaluate(cand)
            for r in results_post:
                if not r.passed and r.reason_code:
                    reason_str = f"{cand.strategy}:{r.reason_code}"
                    rejected_gates.append(reason_str)
                    self._record_rejection(reason_str)
            if not passed_post:
                continue
            self._daily_funnel["stages"]["post_risk_passed"] += 1

            # 4. Multi-Domain Intelligence Enrichment (PIT inputs threaded from the
            #    candidate's context snapshot — real decision/quote timestamps, candles, F&O)
            c_snap = getattr(cand, "context_snapshot", {}) or {}
            _pit_candles = c_snap.get("candles") if isinstance(c_snap.get("candles"), list) else []
            _pit_fno = c_snap.get("fno") if isinstance(c_snap.get("fno"), dict) else {}
            _decision_ts = c_snap.get("timestamp_ms") or getattr(cand, "created_at_utc", None)
            try:
                _decision_ts = int(_decision_ts) if _decision_ts is not None else None
            except Exception:
                _decision_ts = None
            _quote_ts = c_snap.get("quote_timestamp_ms")
            try:
                _quote_ts = int(_quote_ts) if _quote_ts is not None else None
            except Exception:
                _quote_ts = None
            enriched = await enrich_candidate(
                cand=cand,
                active_candles=_pit_candles,
                fno_data=_pit_fno,
                fno_is_degraded=fno_is_degraded,
                risk_decision=risk_decision,
                overlay=overlay,
                rejected_gates=rejected_gates,
                decision_timestamp_ms=_decision_ts,
                quote_timestamp_ms=_quote_ts,
            )
            if len(enriched) == 6:
                fused_score, inst_overlay, explain_bundle, fsm_init_state, ai_advice, ml_pred = enriched
            else:  # backward-compat with legacy 4-tuple enrichment results
                fused_score, inst_overlay, explain_bundle, fsm_init_state = enriched
                ai_advice, ml_pred = None, None
            if fsm_init_state == "REJECT":
                reason_str = f"{cand.strategy}:REJECT_ENRICHMENT_PIT"
                rejected_gates.append(reason_str)
                self._record_rejection(reason_str)
                continue
            self._daily_funnel["stages"]["enrichment_passed"] += 1

            # 5. Build SignalInstance and Register (fail-closed per candidate)
            try:
                instance = build_signal_instance(
                    cand=cand,
                    fused_score=fused_score,
                    fsm_init_state=fsm_init_state,
                    risk_decision=risk_decision,
                    inst_overlay=inst_overlay,
                    ai_advice=ai_advice,
                    ml_pred=ml_pred,
                    overlay=overlay,
                    explain_bundle=explain_bundle,
                    fno_is_degraded=fno_is_degraded,
                )
                await register_and_notify(instance)
            except ValueError as ve:
                reason_str = f"{cand.strategy}:FACTORY_REJECTED_{str(ve)[:120]}"
                rejected_gates.append(reason_str)
                self._record_rejection(reason_str)
                logger.info(
                    "candidate_rejected_factory",
                    strategy=cand.strategy,
                    underlying=cand.underlying,
                    reason=str(ve)[:200],
                )
                continue
            except Exception as e:
                reason_str = f"{cand.strategy}:REGISTRATION_FAILED_{type(e).__name__}"
                rejected_gates.append(reason_str)
                self._record_rejection(reason_str)
                logger.warning(
                    "candidate_registration_failed",
                    strategy=cand.strategy,
                    underlying=cand.underlying,
                    error=str(e)[:200],
                )
                continue
            registered_signals.append(instance)
            self._daily_funnel["stages"]["confirmed"] += 1
            self._daily_funnel["strategy_stats"][cand.strategy]["confirmed"] += 1
            self._daily_funnel["underlying_stats"][cand.underlying]["confirmed"] += 1

        return registered_signals, rejected_gates

    @staticmethod
    def _strip_new_signals(result: dict[str, Any]) -> dict[str, Any]:
        """Cached scan results must never re-deliver stale signals as new."""
        cleaned = dict(result)
        cleaned["new_signals"] = []
        for desk_key in ("scalp_desk", "intraday_desk"):
            desk = cleaned.get(desk_key)
            if isinstance(desk, dict):
                desk_copy = dict(desk)
                desk_copy["new_signals"] = []
                cleaned[desk_key] = desk_copy
        return cleaned

    def _cache_get(self, key: str) -> dict[str, Any] | None:
        entry = self._scan_cache.get(key)
        if not entry:
            return None
        ts, result = entry
        if (time.time() - ts) > self._scan_cache_ttl_s:
            self._scan_cache.pop(key, None)
            return None
        cached = self._strip_new_signals(dict(result))
        cached["cache_hit"] = True
        return cached

    def _cache_put(self, key: str, result: dict[str, Any]) -> None:
        # Bound cache size (avoid unbounded growth)
        if len(self._scan_cache) > 32:
            oldest = min(self._scan_cache.items(), key=lambda kv: kv[1][0])[0]
            self._scan_cache.pop(oldest, None)
        # Never cache new_signals — a cache hit must not replay stale signals.
        self._scan_cache[key] = (time.time(), self._strip_new_signals(result))

    async def _scan_universe(
        self, universe: list[str], timeframe: str, desk: str
    ) -> tuple[list[SignalCandidate], list[dict[str, Any]], dict[str, str]]:
        tasks = [self.scan_instrument(u, timeframe=timeframe, desk=desk) for u in universe]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        candidates: list[SignalCandidate] = []
        errors: dict[str, str] = {}
        for u, res in zip(universe, results):
            if isinstance(res, list):
                candidates.extend(res)
            elif isinstance(res, BaseException):
                if isinstance(res, ValueError):
                    errors[u] = str(res)[:200]
                else:
                    errors[u] = f"{type(res).__name__}: {str(res)[:180]}"
                logger.warning("scanner_instrument_failed", underlying=u, error=str(res)[:200])
        diagnostics = [self._last_diagnostics.get(f"{u}:{timeframe}", ScanDiagnostics(underlying=u)).model_dump() for u in universe]
        return candidates, diagnostics, errors

    @staticmethod
    def _summarize_quality(diagnostics: list[dict[str, Any]], errors: dict[str, str]) -> tuple[str, list[str]]:
        qualities = [d.get("data_quality", "UNKNOWN") for d in diagnostics]
        degraded = [d.get("underlying", "?") for d in diagnostics if d.get("data_quality") in ("DEGRADED", "OFFLINE", "UNKNOWN")]
        degraded.extend([u for u in errors if u not in degraded])
        if not qualities or all(q == "OFFLINE" for q in qualities):
            return "OFFLINE", sorted(set(degraded))
        if any(q in ("DEGRADED", "OFFLINE", "UNKNOWN") for q in qualities) or errors:
            return "DEGRADED", sorted(set(degraded))
        return "LIVE", []

    async def scan_scalp(self, underlying: str | None = None) -> dict[str, Any]:
        """Scans 1M candles for Scalping setups (VWAP, Micro-Momentum, EMA Ribbon, Gamma Spike)."""
        if underlying:
            u = validate_underlying(underlying)
            universe = [u]
        else:
            universe = sorted(list(APPROVED_UNDERLYINGS))
        cache_key = f"scalp:{','.join(universe)}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        candidates, diagnostics, errors = await self._scan_universe(universe, timeframe="1M", desk="SCALP")
        registered, rejected = await self._process_candidates(candidates)
        quality, degraded = self._summarize_quality(diagnostics, errors)
        result: dict[str, Any] = {
            "desk": "SCALP",
            "timeframe": "1M",
            "scanned_underlyings": universe,
            "total_candidates": len(candidates),
            "new_signals": [s.model_dump() for s in registered],
            "rejected_no_edge": rejected,
            "active_signals": [s.model_dump() for s in signal_fsm.list_active()],
            "data_quality": quality,
            "degraded_underlyings": degraded,
            "errors": errors,
            "diagnostics": diagnostics,
            "cache_hit": False,
            "timestamp_ms": int(time.time() * 1000),
        }
        self._cache_put(cache_key, result)
        return result

    async def scan_intraday(self, underlying: str | None = None) -> dict[str, Any]:
        """Scans 5M candles for Core Intraday setups (Breakout, Mean Rev, Trend Pullback, Gamma, ORB)."""
        if underlying:
            u = validate_underlying(underlying)
            universe = [u]
        else:
            universe = sorted(list(APPROVED_UNDERLYINGS))
        cache_key = f"intraday:{','.join(universe)}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        candidates, diagnostics, errors = await self._scan_universe(universe, timeframe="5M", desk="INTRADAY")
        registered, rejected = await self._process_candidates(candidates)
        quality, degraded = self._summarize_quality(diagnostics, errors)
        result: dict[str, Any] = {
            "desk": "INTRADAY",
            "timeframe": "5M",
            "scanned_underlyings": universe,
            "total_candidates": len(candidates),
            "new_signals": [s.model_dump() for s in registered],
            "rejected_no_edge": rejected,
            "active_signals": [s.model_dump() for s in signal_fsm.list_active()],
            "data_quality": quality,
            "degraded_underlyings": degraded,
            "errors": errors,
            "diagnostics": diagnostics,
            "cache_hit": False,
            "timestamp_ms": int(time.time() * 1000),
        }
        self._cache_put(cache_key, result)
        return result

    async def scan_all(self) -> dict[str, Any]:
        """Scan both Scalping (1M) and Intraday (5M) desks across all approved underlyings."""
        cached = self._cache_get("all")
        if cached:
            return cached
        scalp_res = await self.scan_scalp()
        intraday_res = await self.scan_intraday()

        all_new = scalp_res["new_signals"] + intraday_res["new_signals"]
        diagnostics_all = list(scalp_res.get("diagnostics", [])) + list(intraday_res.get("diagnostics", []))
        errors_all = {**scalp_res.get("errors", {}), **intraday_res.get("errors", {})}
        quality, degraded = self._summarize_quality(diagnostics_all, errors_all)
        result: dict[str, Any] = {
            "scanned_underlyings": sorted(list(APPROVED_UNDERLYINGS)),
            "total_candidates": scalp_res["total_candidates"] + intraday_res["total_candidates"],
            "new_signals": all_new,
            "rejected_no_edge": list(scalp_res.get("rejected_no_edge", [])) + list(intraday_res.get("rejected_no_edge", [])),
            "active_signals": [s.model_dump() for s in signal_fsm.list_active()],
            "scalp_desk": scalp_res,
            "intraday_desk": intraday_res,
            "diagnostics": diagnostics_all,
            "errors": errors_all,
            "data_quality": quality,
            "degraded_underlyings": degraded,
            "cache_hit": False,
            "timestamp_ms": int(time.time() * 1000),
        }
        self._cache_put("all", result)
        return result


scanner_engine = SignalScanner()
signal_scanner = scanner_engine

