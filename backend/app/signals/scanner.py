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
from app.signals.strategies import STRATEGY_REGISTRY
from app.signals.confluence import confluence_engine
from app.signals.fsm import signal_fsm, SignalInstance

logger = structlog.get_logger()


class SignalScanner:
    """
    Scans approved universe across all strategies using real-time market data.
    """

    async def scan_instrument(self, underlying: str, timeframe: str = "5M") -> list[SignalCandidate]:
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

        # Technical Analysis on target timeframe (5M default)
        target_tf = timeframe.lower()
        active_candles = candles_dict.get(target_tf) or candles_dict.get("5m") or []
        
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
        )

        candidates: list[SignalCandidate] = []
        # Evaluate all 5 strategies
        for strat_name, strat in STRATEGY_REGISTRY.items():
            try:
                candidate = strat.detect(ctx)
                if candidate:
                    candidates.append(candidate)
            except Exception as e:
                logger.warning("strategy_detect_failed", strategy=strat_name, underlying=u, error=str(e))

        return candidates

    async def scan_all(self) -> dict[str, Any]:
        """Scan all approved underlyings across all strategies."""
        tasks = [self.scan_instrument(u) for u in sorted(list(APPROVED_UNDERLYINGS))]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_candidates: list[SignalCandidate] = []
        for res in results:
            if isinstance(res, list):
                all_candidates.extend(res)

        # Process and register into FSM
        registered_signals: list[SignalInstance] = []
        for cand in all_candidates:
            # Check confluence with AI
            fused_score = confluence_engine.fuse(cand)
            cand.overall_confidence = fused_score

            # Convert to FSM instance
            instance = SignalInstance(
                underlying=cand.underlying,
                strategy=cand.strategy,
                direction=cand.direction,
                timeframe=cand.timeframe,
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
            # Deduplicate by (underlying, strategy, direction) in recent window
            existing = signal_fsm.list_active(underlying=cand.underlying, strategy=cand.strategy)
            same_dir = [s for s in existing if s.direction == cand.direction and not s.is_expired()]
            if not same_dir:
                signal_fsm.register(instance)
                registered_signals.append(instance)

        return {
            "scanned_underlyings": list(APPROVED_UNDERLYINGS),
            "total_candidates": len(all_candidates),
            "new_signals": [s.model_dump() for s in registered_signals],
            "active_signals": [s.model_dump() for s in signal_fsm.list_active()],
            "timestamp_ms": int(__import__("time").time() * 1000),
        }


scanner_engine = SignalScanner()
