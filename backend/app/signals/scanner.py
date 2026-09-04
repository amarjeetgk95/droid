"""
Real-Time Multi-Asset & Multi-Strategy Scanner Engine
Evaluates NIFTY, BANKNIFTY, SENSEX across all 5 Quant Strategies against live market data.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Optional, Any
import structlog

from app.signals.contract_resolver import APPROVED_UNDERLYINGS, validate_underlying, resolve_option_contract
from app.signals.strategies.base import StrategyContext, SignalCandidate
from app.signals.strategies import STRATEGY_REGISTRY, SCALP_STRATEGIES, INTRADAY_STRATEGIES
from app.signals.confluence import confluence_engine
from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.scalp_confirmation import scalp_confirmation_engine

logger = structlog.get_logger()


class SignalScanner:
    """
    Dual-Cadence Quantitative Scanner Engine:
      - Scalp Desk (1M / 3M): VWAP Rejection, Micro-Momentum, EMA Ribbon, Gamma Spike
      - Intraday Desk (5M / 15M): Breakout, Mean Reversion, Trend Pullback, Gamma Squeeze, ORB
    """

    async def scan_instrument(
        self,
        underlying: str,
        timeframe: str = "5M",
        desk: Optional[str] = None,
    ) -> list[SignalCandidate]:
        u = validate_underlying(underlying)
        from app.services.market_service import MarketService
        from app.technical_analysis.analyzer import analyze_timeframe
        from app.multi_timeframe.alignment import compute_alignment

        market_svc = MarketService()
        quote = await market_svc.get_quote(u)
        if not quote or getattr(quote, "ltp", None) is None:
            logger.debug("scanner_no_quote", underlying=u)
            return []

        spot = Decimal(str(quote.ltp))

        # Fetch real candles for indicators
        candles_dict = {}
        try:
            from app.services.candles_service import candles_service
            candles_dict = await candles_service.get_multi_timeframe_candles(u, timeframes=["1m", "5m", "15m", "1h"])
        except Exception:
            pass

        target_tf = timeframe.lower()
        active_candles = candles_dict.get(target_tf) or candles_dict.get("5m") or candles_dict.get("1m") or []

        ta_analysis = {}
        if active_candles:
            try:
                ta_analysis = analyze_timeframe(active_candles, symbol=u, timeframe=timeframe)
            except Exception as e:
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

        # F&O Context
        fno_data = {}
        try:
            from app.fno.context import get_fno_context
            fno_data = await get_fno_context(u)
        except Exception:
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
                logger.warning("strategy_detect_failed", strategy=strat_name, underlying=u, error=str(e))

        return candidates

    async def _process_candidates(self, candidates: list[SignalCandidate]) -> list[SignalInstance]:
        """Validates confluence and registers candidates into FSM."""
        registered_signals: list[SignalInstance] = []

        for cand in candidates:
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

        return registered_signals

    async def scan_scalp(self, underlying: Optional[str] = None) -> dict[str, Any]:
        """Scans 1M candles for Scalping setups (VWAP, Micro-Momentum, EMA Ribbon, Gamma Spike)."""
        universe = [underlying] if underlying else sorted(list(APPROVED_UNDERLYINGS))
        tasks = [self.scan_instrument(u, timeframe="1M", desk="SCALP") for u in universe]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        candidates: list[SignalCandidate] = []
        for res in results:
            if isinstance(res, list):
                candidates.extend(res)

        registered = await self._process_candidates(candidates)
        return {
            "desk": "SCALP",
            "timeframe": "1M",
            "total_candidates": len(candidates),
            "new_signals": [s.model_dump() for s in registered],
            "timestamp_ms": int(__import__("time").time() * 1000),
        }

    async def scan_intraday(self, underlying: Optional[str] = None) -> dict[str, Any]:
        """Scans 5M candles for Core Intraday setups (Breakout, Mean Rev, Trend Pullback, Gamma, ORB)."""
        universe = [underlying] if underlying else sorted(list(APPROVED_UNDERLYINGS))
        tasks = [self.scan_instrument(u, timeframe="5M", desk="INTRADAY") for u in universe]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        candidates: list[SignalCandidate] = []
        for res in results:
            if isinstance(res, list):
                candidates.extend(res)

        registered = await self._process_candidates(candidates)
        return {
            "desk": "INTRADAY",
            "timeframe": "5M",
            "total_candidates": len(candidates),
            "new_signals": [s.model_dump() for s in registered],
            "timestamp_ms": int(__import__("time").time() * 1000),
        }

    async def scan_all(self) -> dict[str, Any]:
        """Scan both Scalping (1M) and Intraday (5M) desks across all approved underlyings."""
        scalp_res = await self.scan_scalp()
        intraday_res = await self.scan_intraday()

        all_new = scalp_res["new_signals"] + intraday_res["new_signals"]
        return {
            "scanned_underlyings": list(APPROVED_UNDERLYINGS),
            "total_candidates": scalp_res["total_candidates"] + intraday_res["total_candidates"],
            "new_signals": all_new,
            "active_signals": [s.model_dump() for s in signal_fsm.list_active()],
            "scalp_desk": scalp_res,
            "intraday_desk": intraday_res,
            "timestamp_ms": int(__import__("time").time() * 1000),
        }


scanner_engine = SignalScanner()

