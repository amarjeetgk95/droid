"""
Real-Time Multi-Asset & Multi-Strategy Scanner Engine
Evaluates NIFTY, BANKNIFTY, SENSEX across all 5 Quant Strategies against live market data.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone, time as dt_time
from zoneinfo import ZoneInfo
from decimal import Decimal
from typing import Optional, Any
import structlog
from pydantic import BaseModel, Field

from app.signals.contract_resolver import APPROVED_UNDERLYINGS, validate_underlying
from app.signals.strategies.base import StrategyContext, SignalCandidate
from app.signals.strategies import STRATEGY_REGISTRY, SCALP_STRATEGIES, INTRADAY_STRATEGIES
from app.signals.confluence import confluence_engine, ARMED_THRESHOLD
from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.scalp_confirmation import scalp_confirmation_engine
from app.signals.features.engine import compute_feature_snapshot
from app.signals.participation.oi_volume_engine import participation_engine
from app.signals.orthogonal_confluence import orthogonal_confluence_engine
from app.signals.risk.friction_gate import friction_gate
from app.signals.risk.cross_desk_arbiter import cross_desk_arbiter

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
    throttled_signals_count: int = 0
    fno_degraded: bool = False
    vwap_degraded: bool = False
    vwap_coverage_pct: float = 100.0


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

        # Pre-market gap filter: suppress strategies for first 3 candles if gap > 0.5%
        prev_close = getattr(quote, "previous_close", None)
        gap_pct = 0.0
        if prev_close and prev_close > 0:
            gap_pct = float(abs((spot - Decimal(str(prev_close))) / Decimal(str(prev_close))) * Decimal("100.0"))

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
        if target_tf == "1m":
            active_candles = candles_dict.get("1m") or []
            if not active_candles:
                diag.reasons.append("Scalp native 1m candles unavailable — fallback prohibited to prevent timeframe skew")
        else:
            active_candles = candles_dict.get(target_tf) or candles_dict.get("5m") or []
            if not active_candles and "1m" in candles_dict:
                active_candles = candles_dict.get("1m") or []
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

        # F&O Context (bounded, strict degradation detection — flagged in diagnostics)
        fno_data = {}
        fno_degraded = False
        try:
            from app.fno.context import get_fno_context
            fno_data = await asyncio.wait_for(get_fno_context(u), timeout=6.0) or {}
        except asyncio.TimeoutError:
            fno_degraded = True
            diag.reasons.append("F&O context timed out — PCR/OI degraded")
        except Exception as e:
            fno_degraded = True
            diag.reasons.append(f"F&O context failed: {str(e)[:100]}")
        if not fno_data:
            fno_degraded = True
            fno_data = {}

        # Market Regime — shared matrix (single source with scalp_confirmation §15).
        # TREND_UP/DOWN (ADX>=25 + trend), HIGH_VOL (atr_pct>=80), COMPRESSION (bb_width pct<=20 + adx<18),
        # EVENT (explicit event flag), else RANGE.
        regime = "RANGE"
        adx_val = float(ta_analysis.get("momentum", {}).get("adx", 20.0))
        trend_val = ta_analysis.get("trend", {}).get("trend", "RANGE")
        try:
            atr_pct = float(ta_analysis.get("volatility", {}).get("atr_percentile", 50.0))
        except Exception:
            atr_pct = 50.0
        try:
            bbw = ta_analysis.get("volatility", {}).get("bb_width_pctile", ta_analysis.get("bollinger_bandwidth_pctile", 50.0))
            bbw = float(bbw)
        except Exception:
            bbw = 50.0
        event_flag = bool(ta_analysis.get("event_flag", False) or ta_analysis.get("is_event_day", False))
        if event_flag:
            regime = "EVENT"
        elif adx_val >= 25.0 and trend_val == "BULLISH":
            regime = "TREND_UP"
        elif adx_val >= 25.0 and trend_val == "BEARISH":
            regime = "TREND_DOWN"
        elif atr_pct >= 80.0:
            regime = "HIGH_VOL"
        elif bbw <= 20.0 and adx_val < 18.0:
            regime = "COMPRESSION_SQUEEZE"

        # Check True Session-Anchored VWAP (Strictly >= 09:15:00 IST of current trading session)
        vwap_val = None
        vwap_degraded = False
        vwap_coverage_pct = 100.0
        if active_candles:
            try:
                from zoneinfo import ZoneInfo
                ist_tz = ZoneInfo("Asia/Kolkata")
                
                # Determine session reference date (latest candle date in IST)
                latest_candle_time = None
                for c in reversed(active_candles):
                    ts = c.get("timestamp")
                    if ts is not None:
                        if isinstance(ts, datetime):
                            latest_candle_time = ts.astimezone(ist_tz) if ts.tzinfo else ts.replace(tzinfo=ist_tz)
                            break
                        elif isinstance(ts, (int, float)):
                            latest_candle_time = datetime.fromtimestamp(ts if ts < 1e11 else ts / 1000.0, tz=ist_tz)
                            break
                        elif isinstance(ts, str):
                            try:
                                dt = datetime.fromisoformat(ts)
                                latest_candle_time = dt.astimezone(ist_tz) if dt.tzinfo else dt.replace(tzinfo=ist_tz)
                                break
                            except Exception:
                                pass

                session_candles = []
                if latest_candle_time:
                    session_open = datetime.combine(latest_candle_time.date(), dt_time(9, 15, 0), tzinfo=ist_tz)
                    for c in active_candles:
                        ts = c.get("timestamp")
                        c_dt = None
                        if isinstance(ts, datetime):
                            c_dt = ts.astimezone(ist_tz) if ts.tzinfo else ts.replace(tzinfo=ist_tz)
                        elif isinstance(ts, (int, float)):
                            c_dt = datetime.fromtimestamp(ts if ts < 1e11 else ts / 1000.0, tz=ist_tz)
                        elif isinstance(ts, str):
                            try:
                                dt = datetime.fromisoformat(ts)
                                c_dt = dt.astimezone(ist_tz) if dt.tzinfo else dt.replace(tzinfo=ist_tz)
                            except Exception:
                                pass
                        if c_dt and c_dt >= session_open and c_dt.date() == latest_candle_time.date():
                            session_candles.append(c)

                vwap_pool = session_candles if session_candles else active_candles
                vwap_degraded = not bool(session_candles)
                try:
                    vwap_coverage_pct = round(len(session_candles) / max(1, len(active_candles)) * 100.0, 1)
                except Exception:
                    vwap_coverage_pct = 0.0 if vwap_degraded else 100.0
                cum_vol = sum(float(c.get("volume", 0)) for c in vwap_pool)
                cum_pv = sum(
                    float(c.get("volume", 0)) * ((float(c.get("high", 0)) + float(c.get("low", 0)) + float(c.get("close", 0))) / 3.0)
                    for c in vwap_pool
                )
                if cum_vol > 0:
                    vwap_val = Decimal(str(round(cum_pv / cum_vol, 2)))
            except Exception as v_err:
                logger.debug("session_vwap_calc_error", error=str(v_err))
                vwap_degraded = True
                vwap_coverage_pct = 0.0
        else:
            vwap_degraded = True
            vwap_coverage_pct = 0.0

        vol_ma = None
        if len(active_candles) >= 20:
            vol_ma = sum(float(c.get("volume", 0)) for c in active_candles[-20:]) / 20.0

        # Lunch-session liquidity vacuum detection (12:00-13:30 IST = 720-810 min)
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
        ist_minute_of_day = now_ist.hour * 60 + now_ist.minute
        lunch_session = 720 <= ist_minute_of_day <= 810

        feat_snap = compute_feature_snapshot(
            underlying=u,
            spot_price=float(spot),
            candles=active_candles,
            timeframe=timeframe,
            vwap=float(vwap_val) if vwap_val else None,
            indicators=ta_analysis,
            timestamp_ms=int(time.time() * 1000),
            prior_day_high=float(getattr(quote, "high", 0.0) or 0.0) if getattr(quote, "high", None) else None,
            prior_day_low=float(getattr(quote, "low", 0.0) or 0.0) if getattr(quote, "low", None) else None,
        )

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
            fno_degraded=fno_degraded,
            vwap_degraded=vwap_degraded,
            vwap_coverage_pct=vwap_coverage_pct,
            timestamp_ms=int(time.time() * 1000),
            vix_percentile=None,
            lunch_session=lunch_session,
            pre_market_gap_pct=float(gap_pct),
            feature_snapshot=feat_snap,
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
                    # Propagate context flags to candidate before confirmation gates
                    candidate.fno_degraded = fno_degraded
                    candidate.vwap_degraded = vwap_degraded
                    candidate.vwap_coverage_pct = vwap_coverage_pct
                    candidate.vix_percentile = getattr(ctx, "vix_percentile", None)
                    candidate.lunch_session = getattr(ctx, "lunch_session", False)

                    # Pre-market gap filter: suppress if gap > 0.5% within first 3 candles
                    gap_pct_val = float(getattr(ctx, "pre_market_gap_pct", 0.0) or 0.0)
                    if gap_pct_val > 0.5 and len(ctx.candles) <= 3:
                        rejected_gates.append(f"{strat_name}:GAP_TOO_LARGE_{gap_pct_val:.2f}pct")
                        logger.info("candidate_rejected_gap", strategy=strat_name, underlying=u, gap_pct=gap_pct_val)
                        continue

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

                    # ── Participation Engine (§18, §19) ──
                    desk_type = "SCALP" if (candidate.is_scalp or strat_name in SCALP_STRATEGIES) else "INTRADAY"
                    part_ctx = participation_engine.evaluate(
                        direction=candidate.direction,
                        desk=desk_type,
                        rvol=feat_snap.rvol if feat_snap else 1.0,
                        volume_acceleration=feat_snap.volume_acceleration if feat_snap else 0.0,
                        price_change_pct=feat_snap.roc_1 if feat_snap else 0.0,
                        fno_data=fno_data,
                        candles=active_candles,
                    )
                    candidate.participation = part_ctx.model_dump()

                    # ── Orthogonal Confluence Engine (§23, §24) ──
                    conf_res = orthogonal_confluence_engine.evaluate(candidate, feat_snap, part_ctx)
                    candidate.confluence_factors = conf_res.confirmed_factors
                    if not conf_res.passed:
                        rejected_gates.append(f"{strat_name}:REJECT_CONFLUENCE")
                        logger.info("candidate_rejected_confluence", strategy=strat_name, underlying=u, reasons=conf_res.rejection_reasons)
                        continue

                    # ── Net Edge & Friction Gate (§27, §28) ──
                    edge_res = friction_gate.evaluate(candidate)
                    candidate.net_edge = edge_res.expected_net_edge_pts
                    if not edge_res.passed:
                        rejected_gates.append(f"{strat_name}:{edge_res.rejection_reason or 'REJECT_FRICTION'}")
                        logger.info("candidate_rejected_friction", strategy=strat_name, underlying=u, reason=edge_res.rejection_reason)
                        continue

                    candidate.vwap_coverage_pct = vwap_coverage_pct
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
                diag.reasons.append(f"{strat_name} detect failed: {str(e)[:100]}")
                logger.warning("strategy_detect_failed", strategy=strat_name, underlying=u, error=str(e))

        diag.strategies_evaluated = len(strategies_to_run)
        diag.candidates_found = len(candidates)
        if rejected_gates:
            diag.reasons.append(f"Scalp gates rejected: {', '.join(rejected_gates[:4])}")
        if not candidates:
            vol_r = ta_analysis.get("volume", {}).get("ratio") if isinstance(ta_analysis.get("volume"), dict) else ta_analysis.get("volume_ratio")
            vol_ratio_fmt = float(vol_r or 1.0)
            diag.reasons.append(
                f"No strategy triggered on {u} {timeframe} (regime={regime}, volume_ratio≈{vol_ratio_fmt:.2f})"
            )
        # Data quality: LIVE only when real quote + real candles + real F&O + session VWAP
        if not diag.candles_count or fno_degraded:
            diag.data_quality = "DEGRADED"
        elif vwap_degraded:
            diag.data_quality = "DEGRADED"
            diag.reasons.append(f"Session VWAP degraded (coverage {vwap_coverage_pct:.1f}%) — confidence haircut applied")
        else:
            diag.data_quality = "LIVE"
        diag.fno_degraded = fno_degraded
        diag.vwap_degraded = vwap_degraded
        diag.vwap_coverage_pct = vwap_coverage_pct
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
        from app.algo.signal_fusion import conflict_resolver

        registered_signals: list[SignalInstance] = []
        rejected_gates: list[str] = []

        # ── Cross-Strategy Directional Conflict Arbitration (§28) ──
        candidates, dropped_conflicts = conflict_resolver.resolve_candidate_conflicts(candidates, tie_epsilon=5.0)
        if dropped_conflicts:
            rejected_gates.extend(dropped_conflicts)

        for cand in candidates:
            # ── F&O Integrity Gate (§1): State-aware execution protection ──
            fno_is_degraded = getattr(cand, "fno_degraded", False)
            if fno_is_degraded:
                rejected_gates.append(f"{cand.strategy}:ARMED_BLOCKED_FNO_DEGRADED")
                logger.info(
                    "candidate_fno_degraded_clamped_to_validated",
                    strategy=cand.strategy,
                    underlying=cand.underlying,
                    reason="ARMED_BLOCKED_FNO_DEGRADED",
                )

            # ── Desk-Differentiated Concurrency & Anti-Stacking Governance (§3) ──
            cand_is_scalp = bool(getattr(cand, "is_scalp", False) or cand.timeframe in ("1M", "3M"))
            active_underlying_all = signal_fsm.list_active(underlying=cand.underlying)
            in_flight_underlying = [
                s for s in active_underlying_all
                if s.fsm_state in ("DETECTED", "VALIDATED", "ARMED", "TRIGGERED", "CONFIRMED", "TARGET_1_HIT")
                and not s.is_expired()
            ] + [s for s in registered_signals if s.underlying == cand.underlying]

            # Isolate in-flight setups belonging to the SAME desk
            same_desk_in_flight = [
                s for s in in_flight_underlying
                if bool(getattr(s, "is_scalp", False) or s.timeframe in ("1M", "3M")) == cand_is_scalp
            ]

            # Reject if underlying already has an active trade in the SAME desk lane
            active_same_desk_trades = [s for s in same_desk_in_flight if s.fsm_state in ("CONFIRMED", "TARGET_1_HIT")]
            if active_same_desk_trades:
                desk_lbl = "SCALP" if cand_is_scalp else "INTRADAY"
                reason = f"UNDERLYING_HAS_ACTIVE_TRADE_{desk_lbl}_{active_same_desk_trades[0].strategy}"
                rejected_gates.append(f"{cand.strategy}:{reason}")
                diag = self._last_diagnostics.get(f"{cand.underlying}:{cand.timeframe}")
                if diag:
                    diag.throttled_signals_count += 1
                logger.info("candidate_rejected_active_trade_exists", underlying=cand.underlying, strategy=cand.strategy, desk=desk_lbl)
                continue

            # Reject if underlying already has an actionable in-flight signal in
            # the same direction on the SAME desk. VALIDATED/DETECTED are
            # watch-only (never executable) so they must NOT block a new,
            # potentially stronger ARMED setup — otherwise one weak 09:30
            # VALIDATED would suppress every better setup until it expires,
            # leaving the desk blank for an hour.
            same_dir_stacked = [
                s for s in same_desk_in_flight
                if s.direction == cand.direction
                and s.fsm_state in ("ARMED", "TRIGGERED", "CONFIRMED", "TARGET_1_HIT")
            ]
            if same_dir_stacked:
                reason = f"STACKING_BLOCKED_EXISTING_{same_dir_stacked[0].strategy}_{same_dir_stacked[0].direction}"
                rejected_gates.append(f"{cand.strategy}:{reason}")
                diag = self._last_diagnostics.get(f"{cand.underlying}:{cand.timeframe}")
                if diag:
                    diag.throttled_signals_count += 1
                logger.info("candidate_rejected_stacking", underlying=cand.underlying, strategy=cand.strategy, blocked_by=same_dir_stacked[0].strategy)
                continue

            # Portfolio Concurrency Cap: Max 4 open/active trades across entire portfolio
            all_active = signal_fsm.list_active()
            portfolio_open_trades = [
                s for s in all_active
                if s.fsm_state in ("CONFIRMED", "TARGET_1_HIT")
                and not s.is_expired()
            ]
            if len(portfolio_open_trades) >= 4:
                reason = "PORTFOLIO_CONCURRENCY_LIMIT_REACHED"
                rejected_gates.append(f"{cand.strategy}:{reason}")
                diag = self._last_diagnostics.get(f"{cand.underlying}:{cand.timeframe}")
                if diag:
                    diag.throttled_signals_count += 1
                logger.info("candidate_rejected_portfolio_cap", strategy=cand.strategy, active_open_trades=len(portfolio_open_trades))
                continue

            # ── Cross-Desk Inventory Arbiter (§31, §51) ──
            arb_dec = cross_desk_arbiter.arbitrate(
                candidate_is_scalp=cand_is_scalp,
                candidate_underlying=cand.underlying,
                candidate_direction=cand.direction,
                active_trades=all_active,
            )
            if not arb_dec.passed:
                rejected_gates.append(f"{cand.strategy}:{arb_dec.reason}")
                logger.info("candidate_rejected_cross_desk_arbiter", strategy=cand.strategy, underlying=cand.underlying, reason=arb_dec.reason)
                continue

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
            # ── Centralized Risk Engine Validation with Event Risk Overlay (§28) ──
            overlay = None
            try:
                from app.event_engine.service import event_engine_service
                from app.event_engine.risk_overlay import event_risk_overlay_service
                events = event_engine_service.get_today_events()
                overlay = event_risk_overlay_service.evaluate_overlay(cand.underlying, events)
            except Exception as ev_err:
                logger.debug("event_overlay_eval_skipped", underlying=cand.underlying, error=str(ev_err))

            risk_decision = central_risk_engine.evaluate(strat_setup, event_overlay=overlay)
            if not risk_decision.accepted:
                rejected_gates.append(f"{cand.strategy}:{risk_decision.rejection_reason}")
                logger.info(
                    "candidate_rejected_risk_engine",
                    strategy=cand.strategy,
                    underlying=cand.underlying,
                    reason=risk_decision.rejection_reason,
                    event_state=getattr(overlay, "proximity_state", "UNKNOWN") if overlay else "NONE",
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

            # ── 1a. Strategy-aware RSI confirmation gate ──
            indicators_snap = cand.context_snapshot.get("indicators", {}) or {}
            rsi_explicit = indicators_snap.get("rsi") or indicators_snap.get("momentum", {}).get("rsi")
            if rsi_explicit is not None:
                rsi_val = float(rsi_explicit)
                is_call = "CALL" in cand.direction
                strat = cand.strategy.upper()

                if strat == "MEAN_REVERSION":
                    # Exhaustion setups: CALL requires oversold, PUT requires overbought
                    rsi_ok = (is_call and rsi_val <= 38.0) or (not is_call and rsi_val >= 62.0)
                elif strat in ("BREAKOUT", "MICRO_MOMENTUM", "GAMMA_SQUEEZE", "GAMMA_SPIKE"):
                    # Momentum expansion setups
                    rsi_ok = (is_call and 52.0 <= rsi_val <= 82.0) or (not is_call and 18.0 <= rsi_val <= 48.0)
                elif strat in ("TREND_PULLBACK", "EMA_RIBBON", "ORB", "VWAP_SCALP"):
                    # Trend-following pullback / continuation
                    rsi_ok = (is_call and 40.0 <= rsi_val <= 70.0) or (not is_call and 30.0 <= rsi_val <= 60.0)
                else:
                    # Default permissive window
                    rsi_ok = (is_call and 35.0 <= rsi_val <= 80.0) or (not is_call and 20.0 <= rsi_val <= 65.0)

                if not rsi_ok:
                    rejected_gates.append(f"{cand.strategy}:RSI_REJECTION_{rsi_val:.1f}")
                    logger.info("candidate_rejected_rsi", strategy=cand.strategy, underlying=cand.underlying, rsi=rsi_val, direction=cand.direction)
                    continue

            # ── 1b. Strategy-aware market-structure proximity filter ──
            # Universal rejection near S/R breaks BREAKOUT (which triggers at S/R) and MEAN_REVERSION.
            # Only trend-continuation setups should reject running directly into opposing blocking levels.
            strat = cand.strategy.upper()
            if strat not in ("BREAKOUT", "MEAN_REVERSION", "VWAP_SCALP"):
                atr_val = Decimal(str(indicators_snap.get("volatility", {}).get("atr") or float(cand.risk_points or 20.0)))
                sr_data = indicators_snap.get("support_resistance", {})
                is_call = "CALL" in cand.direction
                if is_call and sr_data.get("resistance"):
                    # Check for immediate overhead resistance blocking CALL upside
                    raw_res = sr_data.get("resistance")
                    res_items = raw_res if isinstance(raw_res, (list, tuple, set)) else [raw_res] if raw_res is not None else []
                    res_levels = []
                    for r in res_items:
                        try:
                            dec_r = Decimal(str(r))
                            if dec_r > cand.spot_price:
                                res_levels.append(dec_r)
                        except Exception:
                            pass
                    if res_levels:
                        dist_to_overhead = min(lvl - cand.spot_price for lvl in res_levels)
                        if dist_to_overhead < (atr_val * Decimal("0.25")):
                            rejected_gates.append(f"{cand.strategy}:BLOCKED_BY_RESISTANCE_{float(dist_to_overhead):.1f}pts")
                            logger.info("candidate_rejected_blocking_resistance", strategy=cand.strategy, underlying=cand.underlying, dist_pts=float(dist_to_overhead))
                            continue
                elif (not is_call) and sr_data.get("support"):
                    # Check for immediate support floor blocking PUT downside
                    raw_sup = sr_data.get("support")
                    sup_items = raw_sup if isinstance(raw_sup, (list, tuple, set)) else [raw_sup] if raw_sup is not None else []
                    sup_levels = []
                    for s in sup_items:
                        try:
                            dec_s = Decimal(str(s))
                            if dec_s < cand.spot_price:
                                sup_levels.append(dec_s)
                        except Exception:
                            pass
                    if sup_levels:
                        dist_to_floor = min(cand.spot_price - lvl for lvl in sup_levels)
                        if dist_to_floor < (atr_val * Decimal("0.25")):
                            rejected_gates.append(f"{cand.strategy}:BLOCKED_BY_SUPPORT_{float(dist_to_floor):.1f}pts")
                            logger.info("candidate_rejected_blocking_support", strategy=cand.strategy, underlying=cand.underlying, dist_pts=float(dist_to_floor))
                            continue

            # ── 2. Trigger integrity gate: kill born-triggered / no-edge setups ──
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
                is_scalp=getattr(cand, "is_scalp", False),
                timeframe=getattr(cand, "timeframe", "5M"),
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

            # Check confluence with Desk-Specific AI Advisory (§35)
            ai_advice = None
            try:
                c_snap = getattr(cand, "context_snapshot", {}) or {}
                ai_snapshot = {
                    "regime": c_snap.get("regime") or ("RANGE" if cand.regime_score in (70.0, 85.0) else "TREND"),
                    "fno": c_snap.get("fno", {}),
                    "mtf": c_snap.get("mtf", {}),
                    "indicators": c_snap.get("indicators") or {"volatility": {"atr": float(cand.risk_points or 20.0)}},
                    "spot_price": float(c_snap.get("spot_price") or cand.spot_price),
                    "vwap": float(c_snap.get("vwap") or cand.spot_price),
                    "volume_ma_20": c_snap.get("volume_ma_20"),
                }
                ai_advice = await confluence_engine.fetch_ai_advisory(cand, ai_snapshot)
                cand.ai_score = ai_advice.score
                if ai_advice.rationale:
                    cand.rationale.append(f"AI: {ai_advice.rationale}")
            except Exception as ai_err:
                logger.debug("ai_advisory_fetch_skipped", error=str(ai_err))

            # Query ML Prediction if available (§48)
            ml_pred = None
            try:
                from app.ml.predictor import ml_predictor
                ml_res = await ml_predictor.predict_probabilities(cand.underlying)
                if ml_res:
                    ml_pred = {
                        "is_available": True,
                        "bullish_pct": ml_res.bullish_pct,
                        "bearish_pct": ml_res.bearish_pct,
                        "confidence_score": ml_res.confidence_score,
                    }
                    is_call = "CALL" in cand.direction
                    cand_ml_score = ml_res.bullish_pct if is_call else ml_res.bearish_pct
                    cand.rationale.append(f"ML: {ml_res.predicted_bias} ({cand_ml_score:.1f}% prob, conf {ml_res.confidence_score:.0f}%)")
            except Exception as ml_err:
                logger.debug("ml_prediction_fetch_skipped", error=str(ml_err))

            fused_score = confluence_engine.fuse(cand, ai_result=ai_advice, ml_prediction=ml_pred)
            cand.overall_confidence = fused_score

            # Convert to FSM instance with Version 6.0 fields.
            # VALIDATED is watch-only (never auto-executed) — it is the
            # "armed but waiting" shelf the desk watches. Give it a 30-min
            # visibility window so the board is not blank 1hr after open
            # when nothing is executable yet. ARMED keeps the short
            # execution TTL (300/600s) so stale triggers still die fast.
            fsm_init_state = "VALIDATED" if fno_is_degraded else ("ARMED" if fused_score >= ARMED_THRESHOLD else "VALIDATED")
            watch_ttl_seconds = cand.ttl_seconds
            if fsm_init_state == "VALIDATED":
                try:
                    watch_ttl_seconds = max(int(cand.ttl_seconds or 0), 1800)
                except Exception:
                    watch_ttl_seconds = 1800
                try:
                    cand.rationale.append(
                        f"WATCH only (score {fused_score:.1f} < ARMED {ARMED_THRESHOLD:.0f}) — waiting for confirmation, not executable"
                    )
                except Exception:
                    pass
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
                ttl_seconds=watch_ttl_seconds,
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
                    "ai": cand.ai_score,
                    "ai_status": getattr(ai_advice, "status", "UNAVAILABLE") if ai_advice else "UNAVAILABLE",
                    "ml_score": (ml_pred.get("bullish_pct") if "CALL" in cand.direction else ml_pred.get("bearish_pct")) if ml_pred else None,
                    "ml_status": "AVAILABLE" if ml_pred else "UNAVAILABLE",
                    "event_state": getattr(overlay, "proximity_state", "NORMAL") if overlay else "NORMAL",
                    "event_sizing_multiplier": getattr(overlay, "sizing_multiplier", 1.0) if overlay else 1.0,
                    "fno_degraded": fno_is_degraded,
                },
                rationale=cand.rationale,
                option_contract=cand.option_contract.model_dump() if cand.option_contract else None,
                greeks=cand.greeks,
                expected_move=cand.expected_move,
                ai_research=cand.ai_research,
                path_simulation=cand.path_simulation,
                fsm_state=fsm_init_state,
            )

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
signal_scanner = scanner_engine

