"""
Real-Time Multi-Asset & Multi-Strategy Scanner Engine
Evaluates NIFTY, BANKNIFTY, SENSEX across all 5 Quant Strategies against live market data.
"""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import Optional, Any
import structlog
from pydantic import BaseModel, Field

from app.signals.contract_resolver import APPROVED_UNDERLYINGS, validate_underlying
from app.signals.strategies.base import StrategyContext, SignalCandidate
from app.signals.strategies import STRATEGY_REGISTRY, SCALP_STRATEGIES, INTRADAY_STRATEGIES
from app.signals.confluence import confluence_engine
from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.scalp_confirmation import scalp_confirmation_engine

logger = structlog.get_logger()


class ScanDiagnostics(BaseModel):
    """Per-underlying scan health — explains WHY a scan is empty instead of silent []."""
    underlying: str = "UNKNOWN"
    data_quality: str = "UNKNOWN"  # LIVE | DEGRADED | OFFLINE
    quote_status: str = "UNKNOWN"
    provider: str = "UNKNOWN"
    spot_price: Optional[float] = None
    candles_count: int = 0
    strategies_evaluated: int = 0
    candidates_found: int = 0
    registered: int = 0
    reasons: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    duration_ms: int = 0


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

    def _get_market_svc(self) -> Any:
        if self._market_svc is None:
            from app.services.market_service import MarketService
            self._market_svc = MarketService()
        return self._market_svc

    def get_last_diagnostics(self) -> dict[str, Any]:
        return {k: v.model_dump() for k, v in self._last_diagnostics.items()}

    @staticmethod
    def _is_fallback_quote(quote: Any) -> bool:
        try:
            status = str(getattr(quote, "status", "") or "").upper()
            provider = str(getattr(quote, "provider", "") or "").lower()
            if any(s in status for s in ("OFFLINE", "DEGRADED", "STALE", "CLOSED", "INVALID")):
                return True
            if provider in ("fallback", "synthetic", "mock"):
                return True
        except Exception:
            pass
        return False

    async def scan_instrument(
        self,
        underlying: str,
        timeframe: str = "5M",
        desk: Optional[str] = None,
    ) -> list[SignalCandidate]:
        started = time.time()
        u = validate_underlying(underlying)
        diag = ScanDiagnostics(underlying=u)

        # ── Centralized Market Session Check ──
        from app.services.calendar_service import calendar_service
        perm = calendar_service.can_trade_now()
        if not perm.allowed:
            diag.data_quality = "CLOSED"
            diag.reasons.append(f"Market is closed ({perm.reason}: NSE trading hours 09:15 - 15:30 IST). Quantitative scanning paused.")
            diag.duration_ms = int((time.time() - started) * 1000)
            self._last_diagnostics[f"{u}:{timeframe}"] = diag
            return []

        from app.technical_analysis.analyzer import analyze_timeframe
        from app.multi_timeframe.alignment import compute_alignment

        market_svc = self._get_market_svc()
        try:
            quote = await asyncio.wait_for(market_svc.get_quote(u), timeout=8.0)
        except asyncio.TimeoutError:
            diag.data_quality = "OFFLINE"
            diag.error = "quote_timeout_after_8s"
            diag.reasons.append("Quote fetch timed out — feed unreachable")
            diag.duration_ms = int((time.time() - started) * 1000)
            self._last_diagnostics[f"{u}:{timeframe}"] = diag
            return []
        except ValueError:
            raise
        except Exception as e:
            diag.data_quality = "OFFLINE"
            diag.error = f"quote_failed: {str(e)[:120]}"
            diag.reasons.append(f"Quote fetch failed: {str(e)[:120]}")
            diag.duration_ms = int((time.time() - started) * 1000)
            self._last_diagnostics[f"{u}:{timeframe}"] = diag
            return []
        if not quote or getattr(quote, "ltp", None) is None or float(getattr(quote, "ltp", 0.0) or 0.0) <= 0:
            diag.data_quality = "OFFLINE"
            diag.error = "no_quote_or_non_positive_ltp"
            diag.reasons.append(f"Quote unavailable or LTP ({getattr(quote, 'ltp', None)}) <= 0")
            diag.duration_ms = int((time.time() - started) * 1000)
            self._last_diagnostics[f"{u}:{timeframe}"] = diag
            return []

        raw_status = getattr(quote, "status", "UNKNOWN")
        diag.quote_status = str(getattr(raw_status, "value", raw_status))
        diag.provider = str(getattr(quote, "provider", "UNKNOWN"))
        try:
            diag.spot_price = float(quote.ltp)
        except Exception:
            diag.spot_price = None

        # ── Trust gate: never generate signals off fabricated fallback prices ──
        if self._is_fallback_quote(quote):
            diag.data_quality = "OFFLINE"
            diag.error = "fallback_quote"
            diag.reasons.append(
                f"Provider={diag.provider} status={diag.quote_status} — fallback price rejected, no signals generated"
            )
            diag.duration_ms = int((time.time() - started) * 1000)
            self._last_diagnostics[f"{u}:{timeframe}"] = diag
            logger.info("scanner_fallback_quote_rejected", underlying=u, provider=diag.provider)
            return []

        # ── Staleness gate: reject quotes older than scanner threshold ──
        if getattr(quote, "timestamp", None):
            try:
                from datetime import datetime, timezone
                from app.core.config import settings
                q_ts = quote.timestamp
                if q_ts.tzinfo is None:
                    q_ts = q_ts.replace(tzinfo=timezone.utc)
                age_sec = (datetime.now(timezone.utc) - q_ts).total_seconds()
                if age_sec > settings.scanner_quote_age_seconds:
                    diag.data_quality = "DEGRADED"
                    diag.error = f"stale_quote_{round(age_sec, 1)}s"
                    diag.reasons.append(f"Quote age ({round(age_sec, 1)}s) exceeds max allowed ({settings.scanner_quote_age_seconds}s)")
                    diag.duration_ms = int((time.time() - started) * 1000)
                    self._last_diagnostics[f"{u}:{timeframe}"] = diag
                    logger.info("scanner_stale_quote_rejected", underlying=u, age_sec=round(age_sec, 1))
                    return []
            except Exception:
                pass

        try:
            spot = Decimal(str(quote.ltp))
        except Exception:
            diag.data_quality = "OFFLINE"
            diag.error = "invalid_spot_price"
            diag.reasons.append("Quote LTP is not numeric")
            diag.duration_ms = int((time.time() - started) * 1000)
            self._last_diagnostics[f"{u}:{timeframe}"] = diag
            return []

        # Fetch real candles for indicators (bounded timeout, never fatal)
        candles_dict = {}
        try:
            target_tfs = ["1m", "5m", "15m", "1h"]

            async def _fetch_tf(tf_str: str):
                try:
                    c_list = await market_svc.get_candles(u, timeframe=tf_str)
                    return tf_str, [
                        c.model_dump() if hasattr(c, "model_dump") else dict(c)
                        for c in c_list
                    ]
                except Exception as ce:
                    logger.debug("candle_tf_fetch_error", underlying=u, timeframe=tf_str, error=str(ce))
                    return tf_str, []

            tf_results = await asyncio.wait_for(
                asyncio.gather(*[_fetch_tf(tf_str) for tf_str in target_tfs]),
                timeout=8.0,
            )
            candles_dict = {tf_k: c_arr for tf_k, c_arr in tf_results if c_arr}
        except asyncio.TimeoutError:
            diag.reasons.append("Candle fetch timed out — indicators degraded")
        except Exception as e:
            diag.reasons.append(f"Candle fetch failed: {str(e)[:120]}")

        target_tf = timeframe.lower()
        active_candles = candles_dict.get(target_tf) or candles_dict.get("5m") or candles_dict.get("1m") or []
        diag.candles_count = len(active_candles)
        if not active_candles:
            diag.reasons.append("No candles available — S/R, volume and MTF use synthetic defaults")

        ta_analysis: dict[str, Any] = {}
        if active_candles:
            try:
                ta_analysis = analyze_timeframe(active_candles, symbol=u, timeframe=timeframe) or {}
            except Exception as e:
                diag.reasons.append(f"TA analysis failed: {str(e)[:100]} — using defaults")
                logger.debug("ta_analysis_failed", underlying=u, error=str(e))

        # Multi-Timeframe Alignment
        mtf_analyses = {}
        for tf_k, c_list in candles_dict.items():
            if c_list:
                try:
                    mtf_analyses[tf_k] = analyze_timeframe(c_list, symbol=u, timeframe=tf_k)
                except Exception:
                    pass
        mtf_result = compute_alignment(mtf_analyses) if mtf_analyses else {"overall_bias": ta_analysis.get("bias", "NEUTRAL"), "alignment_score": 70.0}

        # F&O Context (bounded, falls back to neutral — flagged in diagnostics)
        fno_data = {}
        fno_degraded = False
        try:
            from app.fno.context import get_fno_context
            fno_data = await asyncio.wait_for(get_fno_context(u), timeout=6.0) or {}
        except asyncio.TimeoutError:
            fno_degraded = True
            diag.reasons.append("F&O context timed out — PCR/OI neutral")
        except Exception as e:
            fno_degraded = True
            diag.reasons.append(f"F&O context failed: {str(e)[:100]}")
        if not fno_data:
            fno_degraded = True
            fno_data = {"pcr": 1.05, "oi_change_pct": 5.2, "atm_iv": 14.2, "max_pain": float(spot)}

        # Market Regime
        regime = "RANGE"
        adx_val = float(ta_analysis.get("momentum", {}).get("adx", 20.0))
        trend_val = ta_analysis.get("trend", {}).get("trend", "RANGE")
        if adx_val >= 25.0 and trend_val == "BULLISH":
            regime = "TREND_UP"
        elif adx_val >= 25.0 and trend_val == "BEARISH":
            regime = "TREND_DOWN"
        elif float(ta_analysis.get("volatility", {}).get("atr_percentile", 50.0)) >= 80.0:
            regime = "HIGH_VOL"

        # Check VWAP & 20 MA Volume
        vwap_val = None
        if active_candles:
            try:
                cum_vol = sum(float(c.get("volume", 0)) for c in active_candles)
                cum_pv = sum(float(c.get("volume", 0)) * ((float(c.get("high", 0)) + float(c.get("low", 0)) + float(c.get("close", 0))) / 3.0) for c in active_candles)
                if cum_vol > 0:
                    vwap_val = Decimal(str(round(cum_pv / cum_vol, 2)))
            except Exception:
                pass

        vol_ma = None
        if len(active_candles) >= 20:
            vol_ma = sum(float(c.get("volume", 0)) for c in active_candles[-20:]) / 20.0

        ctx = StrategyContext(
            underlying=u,  # type: ignore
            spot_price=spot,
            timeframe=timeframe,  # type: ignore
            indicators=ta_analysis,
            mtf=mtf_result,
            fno=fno_data,
            regime=regime,
            session_state="OPEN",
            candles=active_candles,
            vwap=vwap_val,
            volume_ma_20=vol_ma,
            is_new_1m_candle=(timeframe == "1M"),
            is_new_5m_candle=(timeframe == "5M"),
        )

        # Select strategies according to desk and timeframe
        if desk == "SCALP" or timeframe in ("1M", "3M"):
            strategies_to_run = SCALP_STRATEGIES
        elif desk == "INTRADAY" or timeframe in ("5M", "15M", "1H"):
            strategies_to_run = INTRADAY_STRATEGIES
        else:
            strategies_to_run = STRATEGY_REGISTRY

        candidates: list[SignalCandidate] = []
        rejected_gates: list[str] = []
        for strat_name, strat in strategies_to_run.items():
            try:
                candidate = strat.detect(ctx)
                if candidate:
                    # Gating Fast Scalping setups through ScalpConfirmationEngine (§16)
                    if candidate.is_scalp or strat_name in SCALP_STRATEGIES:
                        confirm_res = scalp_confirmation_engine.validate(
                            candidate=candidate,
                            current_spot=spot,
                            regime=regime,
                            candle_timestamp_ms=ctx.timestamp_ms,
                        )
                        if not confirm_res.passed:
                            rejected_gates.append(f"{strat_name}:{confirm_res.reason_code or 'REJECTED'}")
                            logger.info(
                                "scalp_candidate_rejected_gate",
                                strategy=strat_name,
                                underlying=u,
                                reason=confirm_res.reason_code,
                                msg=confirm_res.rejection_message,
                            )
                            continue
                        # Gate passed: record confirmed fingerprint
                        scalp_confirmation_engine.record_confirmed(candidate, candle_timestamp_ms=ctx.timestamp_ms)

                    candidates.append(candidate)
            except Exception as e:
                diag.reasons.append(f"{strat_name} detect failed: {str(e)[:100]}")
                logger.warning("strategy_detect_failed", strategy=strat_name, underlying=u, error=str(e))

        diag.strategies_evaluated = len(strategies_to_run)
        diag.candidates_found = len(candidates)
        if rejected_gates:
            diag.reasons.append(f"Scalp gates rejected: {', '.join(rejected_gates[:4])}")
        if not candidates:
            diag.reasons.append(
                f"No strategy triggered on {u} {timeframe} (regime={regime}, volume_ratio≈{float(ta_analysis.get('volume_ratio', 0) or 0):.2f})"
            )
        # Data quality: LIVE only when real quote + real candles + real F&O
        if not diag.candles_count or fno_degraded:
            diag.data_quality = "DEGRADED"
        else:
            diag.data_quality = "LIVE"
        diag.duration_ms = int((time.time() - started) * 1000)
        self._last_diagnostics[f"{u}:{timeframe}"] = diag
        return candidates

    async def _process_candidates(self, candidates: list[SignalCandidate]) -> tuple[list[SignalInstance], list[str]]:
        """Validates confluence + trigger integrity, registers passing candidates into FSM.

        Returns (registered, rejected_reasons). Rejections (no-edge triggers etc.)
        are surfaced in scan diagnostics instead of silently vanishing.
        """
        from app.services.calendar_service import calendar_service
        perm = calendar_service.can_trade_now()
        if not perm.allowed:
            logger.info("process_candidates_rejected_market_closed", reason=perm.reason)
            return [], [f"MARKET_CLOSED_{perm.reason}"]

        from app.signals.trigger_gate import check_trigger_integrity
        from app.signals.risk_engine import central_risk_engine, StrategySetup

        registered_signals: list[SignalInstance] = []
        rejected_gates: list[str] = []

        for cand in candidates:
            # ── Centralized Risk Engine Validation (Enforces Envelopes & Rejection of Oversized SL) ──
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
            )
            risk_decision = central_risk_engine.evaluate(strat_setup)
            if not risk_decision.accepted:
                rejected_gates.append(f"{cand.strategy}:{risk_decision.rejection_reason}")
                logger.info(
                    "candidate_rejected_risk_engine",
                    strategy=cand.strategy,
                    underlying=cand.underlying,
                    reason=risk_decision.rejection_reason,
                )
                continue

            # Update candidate with validated, realistic parameters
            cand.stop_loss = risk_decision.stop_loss
            cand.target_1 = risk_decision.target_1
            cand.target_2 = risk_decision.target_2
            cand.risk_points = Decimal(str(risk_decision.risk_points))
            cand.risk_reward_t1 = risk_decision.risk_reward_t1
            cand.risk_reward_t2 = risk_decision.risk_reward_t2
            cand.ttl_seconds = risk_decision.trigger_ttl_seconds
            cand.time_stop_seconds = risk_decision.active_time_stop_seconds

            # ── Trigger integrity gate: kill born-triggered / no-edge setups ──
            gate = check_trigger_integrity(
                underlying=cand.underlying,
                strategy=cand.strategy,
                direction=cand.direction,
                spot_price=cand.spot_price,
                entry_min=cand.entry_min,
                entry_max=cand.entry_max,
                trigger=cand.trigger,
                stop_loss=cand.stop_loss,
                target_1=cand.target_1,
                target_2=cand.target_2,
                risk_points=cand.risk_points,
                risk_reward_t1=cand.risk_reward_t1,
                risk_reward_t2=cand.risk_reward_t2,
            )
            if not gate.passed:
                rejected_gates.append(f"{cand.strategy}:{gate.reason_code}")
                logger.info(
                    "candidate_rejected_trigger_gate",
                    strategy=cand.strategy,
                    underlying=cand.underlying,
                    reason=gate.reason_code,
                    msg=gate.message,
                )
                continue

            # Check confluence with AI
            fused_score = confluence_engine.fuse(cand)
            cand.overall_confidence = fused_score

            # Convert to FSM instance with Version 6.0 fields
            instance = SignalInstance(
                underlying=cand.underlying,
                strategy=cand.strategy,
                direction=cand.direction,
                timeframe=cand.timeframe,
                spot_price=cand.spot_price,
                signal_type=cand.signal_type,
                is_scalp=cand.is_scalp,
                entry_min=cand.entry_min,
                entry_max=cand.entry_max,
                trigger=cand.trigger,
                stop_loss=cand.stop_loss,
                initial_stop_loss=cand.stop_loss,
                current_stop_loss=cand.stop_loss,
                target_1=cand.target_1,
                target_2=cand.target_2,
                t1_price=cand.target_1,
                t2_price=cand.target_2,
                risk_points=cand.risk_points,
                risk_reward_t1=cand.risk_reward_t1,
                risk_reward_t2=cand.risk_reward_t2,
                ttl_seconds=cand.ttl_seconds,
                runner_ttl_seconds=cand.runner_ttl_seconds,
                time_stop_seconds=cand.time_stop_seconds,
                lots=risk_decision.lots,
                quantity=risk_decision.quantity,
                max_rupee_loss=risk_decision.max_rupee_loss,
                confidence=fused_score,
                confluence_breakdown={
                    "technical": cand.technical_score,
                    "mtf": cand.mtf_score,
                    "fno": cand.fno_score,
                    "regime": cand.regime_score,
                    "ai": cand.ai_score or 70.0,
                },
                rationale=cand.rationale,
                option_contract=cand.option_contract.model_dump() if cand.option_contract else None,
                fsm_state="ARMED" if fused_score >= 70.0 else "VALIDATED",
            )

            # Deduplicate by (underlying, strategy, direction) among in-flight signals
            existing = signal_fsm.list_active(underlying=cand.underlying, strategy=cand.strategy)
            same_dir = [
                s for s in existing
                if s.direction == cand.direction
                and s.fsm_state in ("DETECTED", "VALIDATED", "ARMED", "TRIGGERED", "CONFIRMED", "TARGET_1_HIT")
                and not s.is_expired()
            ]
            if not same_dir:
                signal_fsm.register(instance)
                registered_signals.append(instance)

                # Record into Signal Audit Ledger
                try:
                    from app.signals.audit_ledger import signal_audit_ledger
                    signal_audit_ledger.record_signal_created(
                        signal_id=instance.signal_id,
                        underlying=instance.underlying,
                        strategy=instance.strategy,
                        direction=instance.direction,
                        timeframe=instance.timeframe,
                        spot_price=float(instance.spot_price),
                        trigger=float(instance.trigger),
                        stop_loss=float(instance.stop_loss),
                        target_1=float(instance.target_1),
                        target_2=float(instance.target_2),
                        confidence=float(instance.confidence),
                        option_contract=instance.option_contract,
                        status=instance.fsm_state,
                    )
                except Exception as ae:
                    logger.warning("audit_record_created_failed", error=str(ae))

                # Enqueue Telegram notification
                try:
                    from app.institutional.telegram_notifications import SignalEvent, telegram_notification_queue
                    ev = SignalEvent(
                        event_type="POSSIBLE_SETUP",
                        signal_id=instance.signal_id,
                        instrument=instance.underlying,
                        candle_timeframe=instance.timeframe,
                        setup_type=f"{'⚡ ' if instance.is_scalp else ''}{instance.strategy}",
                        direction="BULLISH" if "CALL" in instance.direction else "BEARISH",
                        status=instance.fsm_state,
                        trigger_level=float(instance.trigger),
                        current_price=float(instance.spot_price),
                        stop_loss=float(instance.stop_loss),
                        target_low=float(instance.target_1),
                        target_high=float(instance.target_2),
                        confidence=float(instance.confidence),
                    )
                    await telegram_notification_queue.publish_signal_event(ev)
                except Exception as te:
                    logger.warning("scanner_telegram_publish_failed", error=str(te))

        return registered_signals, rejected_gates

    def _cache_get(self, key: str) -> Optional[dict[str, Any]]:
        entry = self._scan_cache.get(key)
        if not entry:
            return None
        ts, result = entry
        if (time.time() - ts) > self._scan_cache_ttl_s:
            self._scan_cache.pop(key, None)
            return None
        cached = dict(result)
        cached["cache_hit"] = True
        return cached

    def _cache_put(self, key: str, result: dict[str, Any]) -> None:
        # Bound cache size (avoid unbounded growth)
        if len(self._scan_cache) > 32:
            oldest = min(self._scan_cache.items(), key=lambda kv: kv[1][0])[0]
            self._scan_cache.pop(oldest, None)
        self._scan_cache[key] = (time.time(), result)

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

    async def scan_scalp(self, underlying: Optional[str] = None) -> dict[str, Any]:
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

    async def scan_intraday(self, underlying: Optional[str] = None) -> dict[str, Any]:
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

