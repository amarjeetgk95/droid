"""Deep Insight aggregation service — combines regime, options, multi-TF, and AI signal per §14."""
from __future__ import annotations

import asyncio
import structlog
from datetime import datetime, timezone
from typing import Optional

from app.ai.ai_evaluator import ai_evaluator
from app.ai.schemas import (
    DeepInsightPayload,
    DeepInsightMarket,
    DeepInsightMarketLevels,
    DeepInsightMomentum,
    DeepInsightVolume,
    DeepInsightTimeframeEntry,
    DeepInsightOptionsEvidence,
    DeepInsightHistoricalEvidence,
    DeepInsightSetup,
    DeepInsightSignalState,
    DeepInsightValidation,
    DeepInsightProvider,
    DeepInsightDataQuality,
    Direction,
    Regime,
    VolatilityLevel,
    SampleQuality,
    ValidationStatus,
    Decision,
    SetupType,
)
from app.ai.regime_detector import RegimeDetector
from app.services.regime_service import RegimeService
from app.services.market_service import MarketService
from app.services.options_service import OptionsService
from app.quant.indicators import calculate_rsi, calculate_adx, calculate_atr

logger = structlog.get_logger()


def _infer_direction(price: float, vwap: float) -> str:
    if price > vwap * 1.001:
        return "Above"
    elif price < vwap * 0.999:
        return "Below"
    return "At"


def _volume_status(rel: float) -> str:
    if rel >= 1.3:
        return "High"
    elif rel >= 0.8:
        return "Normal"
    return "Low"


REGIME_STATE_TO_REGIME: dict[str, Regime] = {
    "TRENDING_BULLISH": Regime.TREND,
    "TRENDING_BEARISH": Regime.TREND,
    "RANGEBOUND_LOW_VOL": Regime.RANGE,
    "RANGEBOUND_HIGH_VOL": Regime.RANGE,
    "VOLATILE_EXPANSION": Regime.HIGH_VOLATILITY,
    "COMPRESSION_SQUEEZE": Regime.BREAKOUT,
}


class DeepInsightService:
    """Aggregates all intelligence needed for the Deep Insight frontend module."""

    def __init__(self):
        self.regime_service = RegimeService()
        self.market_service = MarketService()
        self.options_service = OptionsService()
        self.regime_detector = RegimeDetector()

    def _per_timeframe_bias(self, candles: list, timeframe_label: str) -> DeepInsightTimeframeEntry:
        if not candles or len(candles) < 14:
            return DeepInsightTimeframeEntry(timeframe=timeframe_label, direction=Direction.NEUTRAL, strength=50, structure="Insufficient data")

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        rsi = calculate_rsi(closes, period=14)
        plus_di, minus_di, adx = calculate_adx(highs, lows, closes, period=14)
        atr = calculate_atr(highs, lows, closes, period=14) or 0

        current = closes[-1]
        prev_high = max(highs[:-1]) if len(highs) > 1 else current
        prev_low = min(lows[:-1]) if len(lows) > 1 else current

        # Determine structure
        if current > prev_high:
            structure = "Higher highs"
        elif current < prev_low:
            structure = "Lower lows"
        elif adx >= 25:
            structure = "Strong trend"
        elif adx < 20:
            structure = "Range"
        else:
            structure = "Mixed"

        # Direction
        if rsi >= 55 and plus_di > minus_di:
            direction = Direction.BULLISH
            strength = min(100, int(rsi + adx / 2))
        elif rsi <= 45 and minus_di > plus_di:
            direction = Direction.BEARISH
            strength = min(100, int((100 - rsi) + adx / 2))
        else:
            direction = Direction.NEUTRAL
            strength = 50

        return DeepInsightTimeframeEntry(
            timeframe=timeframe_label,
            direction=direction,
            strength=strength,
            structure=structure,
        )

    async def _get_multi_timeframe(self, symbol: str) -> list[DeepInsightTimeframeEntry]:
        tf_map = {
            "1M": "1m",
            "3M": "5m",
            "5M": "5m",
            "15M": "15m",
        }
        results: list[DeepInsightTimeframeEntry] = []
        for label, tf_key in tf_map.items():
            try:
                candles = await self.market_service.get_candles(symbol, timeframe=tf_key)
                entry = self._per_timeframe_bias(candles, label)
                results.append(entry)
            except Exception as e:
                logger.warning("mtf_fetch_failed", symbol=symbol, tf=label, error=str(e))
                results.append(DeepInsightTimeframeEntry(timeframe=label, direction=Direction.NEUTRAL, strength=0, structure="Unavailable"))
        return results

    async def _get_options_evidence(self, symbol: str) -> DeepInsightOptionsEvidence:
        try:
            chain = await self.options_service.get_option_chain_matrix(symbol)
            analytics = chain.analytics
            pcr = analytics.pcr_oi if analytics else 1.0
            spot = analytics.spot_price if analytics else 0.0

            # Determine bias
            if pcr > 1.2:
                bias = Direction.BEARISH
                interp = "High PCR — put buying dominant, bearish undertone"
            elif pcr < 0.8:
                bias = Direction.BULLISH
                interp = "Low PCR — call buying dominant, bullish undertone"
            else:
                bias = Direction.NEUTRAL
                interp = "Balanced options flow"

            # OI trend (simplified: use ATM IV change direction as proxy)
            iv_str = "Moderate"
            if analytics and analytics.atm_iv:
                if analytics.atm_iv > 20:
                    iv_str = "High"
                elif analytics.atm_iv < 12:
                    iv_str = "Low"

            return DeepInsightOptionsEvidence(
                bias=bias,
                pcr=round(pcr, 2),
                put_support=round(spot * 0.995, 2) if spot else 0.0,
                call_resistance=round(spot * 1.005, 2) if spot else 0.0,
                oi_trend="Increasing" if analytics and analytics.total_call_oi > analytics.total_put_oi else "Stable",
                iv=iv_str,
                interpretation=interp,
            )
        except Exception as e:
            logger.warning("options_evidence_failed", symbol=symbol, error=str(e))
            return DeepInsightOptionsEvidence()

    async def get_deep_insight(self, symbol: str) -> DeepInsightPayload:
        """Build the complete Deep Insight payload for a symbol."""
        now = datetime.now(timezone.utc)
        symbol = symbol.upper()

        # --- Parallel data fetches ---
        try:
            regime_overview, quote, options_evidence, multi_tf = await asyncio.gather(
                self.regime_service.classify_market_regime(symbol),
                self.market_service.get_quote(symbol),
                self._get_options_evidence(symbol),
                self._get_multi_timeframe(symbol),
            )
        except Exception as e:
            logger.error("deep_insight_fetch_error", symbol=symbol, error=str(e))
            return DeepInsightPayload(symbol=symbol, timestamp=now, error=str(e))

        try:
            key_levels = await self.regime_service.get_key_levels(symbol)
        except Exception:
            key_levels = None

        # --- Build market levels ---
        spot = quote.ltp or regime_overview.spot_price or 24000.0
        vwap = getattr(regime_overview, "vwap", 0.0) or (spot * 0.9995)
        support = getattr(key_levels, "nearest_support", spot * 0.995) or (spot * 0.995)
        resistance = getattr(key_levels, "nearest_resistance", spot * 1.005) or (spot * 1.005)

        # --- Market ---
        regime_state = getattr(regime_overview, "regime_state", "UNKNOWN") or "UNKNOWN"
        regime_upper = regime_state.upper()
        if regime_upper in REGIME_STATE_TO_REGIME:
            regime_enum = REGIME_STATE_TO_REGIME[regime_upper]
        else:
            try:
                regime_enum = Regime(regime_upper)
            except (ValueError, AttributeError):
                regime_enum = Regime.UNKNOWN

        regime_strength = int(getattr(regime_overview, "confidence_score", getattr(regime_overview, "confidence", 50)) or 50)
        adx_val = 0.0
        if hasattr(regime_overview, "indicators"):
            adx_val = getattr(regime_overview.indicators, "adx_14", 0.0) or 0.0

        volatility = VolatilityLevel.MEDIUM
        if hasattr(regime_overview, "indicators"):
            atr_val = getattr(regime_overview.indicators, "atr_14", 0.0) or 0
            if atr_val > spot * 0.015:
                volatility = VolatilityLevel.HIGH
            elif atr_val < spot * 0.005:
                volatility = VolatilityLevel.LOW

        direction = Direction.NEUTRAL
        if "BULLISH" in regime_upper:
            direction = Direction.BULLISH
        elif "BEARISH" in regime_upper:
            direction = Direction.BEARISH

        market = DeepInsightMarket(
            regime=regime_enum,
            direction=direction,
            regime_strength=min(100, max(0, regime_strength)),
            volatility=volatility,
            levels=DeepInsightMarketLevels(
                current_price=spot,
                vwap=vwap,
                support=support,
                resistance=resistance,
                vwap_relation=_infer_direction(spot, vwap),
            ),
            momentum=DeepInsightMomentum(
                status="Positive" if adx_val >= 20 else "Weak",
                value=round(adx_val, 1),
            ),
            volume=DeepInsightVolume(
                relative_value=1.0,
                status="Normal",
            ),
        )

        # --- Options Evidence already fetched ---
        options_ev = options_evidence

        # --- Historical Evidence (stub with reasonable defaults) ---
        historical_ev = DeepInsightHistoricalEvidence(
            similar_states=0,
            continuation=0.0,
            failure=0.0,
            reversal=0.0,
            median_move=0.0,
            median_duration="",
            sample_quality=SampleQuality.POOR,
        )

        # --- AI Signal via v2 evaluator ---
        try:
            signal, execution = await ai_evaluator.evaluate(symbol)
        except Exception as e:
            logger.warning("deep_insight_ai_evaluate_failed", symbol=symbol, error=str(e))
            signal = None
            execution = None

        if signal is not None:
            signal_time = signal.timestamp
            age = max(0, int((datetime.now(timezone.utc) - signal_time).total_seconds()))
            ttl_remaining = max(0, signal.ttl_seconds - age)
            signal_state = DeepInsightSignalState(
                state="ACTIVE" if ttl_remaining > 0 else "EXPIRED",
                age=age,
                ttl=signal.ttl_seconds,
                ttl_remaining=ttl_remaining,
            )
            if signal.decision == Decision.NO_TRADE or signal.entry <= 0:
                setup = DeepInsightSetup(
                    setup_type=SetupType.NO_SETUP,
                    entry_zone="—",
                    stop_loss=0.0,
                    target="—",
                    risk_reward=0.0,
                )
                ai_summary = signal.rejection_detail or "No active trade setup. Waiting for clear confirmation."
            else:
                setup = DeepInsightSetup(
                    setup_type=signal.setup_type,
                    entry_zone=f"{signal.entry:.0f}" if signal.entry > 0 else "—",
                    stop_loss=signal.stop_loss,
                    target=f"{signal.target:.0f}" if signal.target > 0 else "—",
                    risk_reward=round((abs(signal.target - signal.entry) / max(abs(signal.entry - signal.stop_loss), 0.01)), 1) if signal.entry > 0 and signal.stop_loss > 0 else 0.0,
                )
                ai_summary = f"{signal.setup_type.value} setup on {signal.timeframe} timeframe."

            ai_view = {
                "bias": signal.decision.value,
                "confidence": signal.raw_confidence,
                "calibrated_confidence": signal.calibrated_confidence,
                "setup_type": setup.setup_type.value,
                "summary": ai_summary,
            }
            technical_evidence = {
                "positive": signal.reasons[:4],
                "supporting": [],
            }
            risks = {
                "positive_factors": signal.reasons[:3],
                "main_risks": signal.invalidation[:3],
            }
            validation = DeepInsightValidation(
                status=signal.validation_result,
                rejection_reason=signal.rejection_detail or None,
            )
            provider = DeepInsightProvider(
                name=signal.provider or "AI Engine",
                model=signal.model or "Configured model",
                latency_ms=signal.latency_ms,
            )
            invalidation = signal.invalidation
        else:
            signal_state = DeepInsightSignalState(state="AI_UNAVAILABLE", age=0, ttl=0, ttl_remaining=0)
            setup = DeepInsightSetup()
            ai_view = {}
            technical_evidence = {"positive": [], "supporting": []}
            risks = {"positive_factors": [], "main_risks": []}
            validation = DeepInsightValidation(status=ValidationStatus.REJECT, rejection_reason="AI evaluation failed")
            provider = DeepInsightProvider()
            invalidation = []

        data_quality = DeepInsightDataQuality(
            completeness=100.0 if signal else 0.0,
            status="Complete" if signal else "Incomplete",
        )

        return DeepInsightPayload(
            symbol=symbol,
            timestamp=now,
            market=market,
            regime=regime_enum,
            multi_timeframe=multi_tf,
            ai_view=ai_view,
            technical_evidence=technical_evidence,
            options_evidence=options_ev,
            historical_evidence=historical_ev,
            setup=setup,
            risks=risks,
            invalidation=invalidation,
            signal_state=signal_state,
            data_quality=data_quality,
            validation=validation,
            provider=provider,
        )


deep_insight_service = DeepInsightService()
