"""
Institutional Confluence Engine with Desk-Specific AI & Dynamic Weight Renormalization (§16, §35)
Unified weights (backend/config/scoring_weights.json v2):
  - Technical: 40%
  - MTF: 20%
  - F&O: 15% (+5% event_risk via overlay sizing, total 20% F&O domain)
  - Regime: 10%
  - AI Advisory: <= 10% (Capped, desk-specific timeout)
  - ML Predictor: <= 7% (When available)
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional
import structlog
from pydantic import BaseModel, Field

from app.signals.strategies.base import SignalCandidate

logger = structlog.get_logger()


def _load_confluence_weights() -> dict:
    try:
        for p in (
            Path(__file__).resolve().parents[2] / "config" / "scoring_weights.json",
            Path("backend/config/scoring_weights.json"),
            Path("config/scoring_weights.json"),
        ):
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                wf = data.get("weights_fraction", {})
                if wf:
                    return {
                        "technical": float(wf.get("technical", 0.40)),
                        "mtf": float(wf.get("mtf", 0.20)),
                        "fno": float(wf.get("fno", 0.15)),
                        "regime": float(wf.get("regime", 0.10)),
                        "ai": float(wf.get("ai", 0.10)),
                    }
    except Exception:
        pass
    return {
        "technical": 0.40,
        "mtf": 0.20,
        "fno": 0.15,
        "regime": 0.10,
        "ai": 0.10,
    }


DEFAULT_WEIGHTS = _load_confluence_weights()
ARMED_THRESHOLD = 70.0
AI_UNAVAILABLE_HAIRCUT = 8.0
FNODEGRADED_HAIRCUT = 10.0
VWAPDEGRADED_HAIRCUT = 10.0


class AIAdviceResult(BaseModel):
    status: str = "UNAVAILABLE"  # AVAILABLE, UNAVAILABLE, TIMEOUT, ERROR
    score: Optional[float] = None
    confidence: Optional[float] = None
    rationale: Optional[str] = None
    risk_flags: list[str] = Field(default_factory=list)
    latency_ms: int = 0


class ConfluenceEngine:
    """
    Evaluates multi-domain confluence and applies advisory AI scoring with strict isolation
    and dynamic weight renormalization (§16).
    """

    def __init__(self, ai_weight: float = 0.10):
        assert 0.0 <= ai_weight <= 0.10, "AI weight cannot exceed 0.10 (10%) per master contract §35"
        self.ai_weight = ai_weight

    async def fetch_ai_advisory(self, candidate: SignalCandidate, context_snapshot: dict) -> AIAdviceResult:
        """Query specialized Desk AI (ScalpingAI vs CoreIntradayAI) with strict timeout isolation."""
        start_ms = int(__import__("time").time() * 1000)
        try:
            from app.ai.schemas import MarketContext, RegimeObject, OptionsContext, Regime, Direction, VolatilityLevel, Decision
            from app.ai.scalping_ai import scalping_ai
            from app.ai.core_intraday_ai import core_intraday_ai

            is_scalp = getattr(candidate, "is_scalp", False) or candidate.timeframe in ("1M", "3M")
            regime_str = str(context_snapshot.get("regime") or "RANGE").upper()
            regime_enum = Regime.TREND if "TREND" in regime_str else Regime.RANGE

            # Un-coerced Market Regime direction: purely based on market state, NOT candidate.direction
            if "UP" in regime_str or "BULL" in regime_str:
                regime_dir = Direction.BULLISH
            elif "DOWN" in regime_str or "BEAR" in regime_str:
                regime_dir = Direction.BEARISH
            else:
                regime_dir = Direction.NEUTRAL

            regime_obj = RegimeObject(
                regime=regime_enum,
                direction=regime_dir,
                strength=int(candidate.regime_score or 70),
                volatility=VolatilityLevel.HIGH if "VOL" in regime_str else VolatilityLevel.MEDIUM,
            )

            # Un-coerced Options context direction: purely based on F&O indicators, NOT candidate.direction
            fno_info = context_snapshot.get("fno", {})
            pcr_oi_val = float(fno_info.get("pcr", 1.0) or 1.0)
            if pcr_oi_val >= 1.20:
                fno_dir = "BULLISH"
            elif pcr_oi_val <= 0.80:
                fno_dir = "BEARISH"
            else:
                fno_dir = "NEUTRAL"

            options_ctx = OptionsContext(
                pcr_oi=pcr_oi_val,
                pcr_volume=float(fno_info.get("pcr_volume", 1.0) or 1.0),
                atm_iv=float(fno_info.get("atm_iv", 14.5) or 14.5),
                direction=fno_dir,
            )

            indicators = context_snapshot.get("indicators", {})
            market_ctx = MarketContext(
                symbol=str(candidate.underlying),
                current_price=float(candidate.spot_price),
                market_status="OPEN",
                structure_1m=str(context_snapshot.get("mtf", {}).get("1m_bias", "")),
                structure_5m=str(context_snapshot.get("mtf", {}).get("overall_bias", "")),
                vwap=float(context_snapshot.get("vwap") or candidate.spot_price),
                atr=float(indicators.get("volatility", {}).get("atr") or candidate.risk_points or 20.0),
                volume=float(indicators.get("volume", {}).get("ratio") or indicators.get("volume_ratio", 1.0) or 1.0),
                momentum=float(indicators.get("momentum", {}).get("adx") or 20.0),
                support_resistance=indicators.get("support_resistance", {}),
                regime=regime_obj,
                options_context=options_ctx,
            )

            # Route by desk with strict timeouts
            timeout_budget = 0.5 if is_scalp else 1.5
            if is_scalp:
                signal = await asyncio.wait_for(
                    scalping_ai.generate(
                        symbol=candidate.underlying,
                        regime=regime_enum,
                        market_context=market_ctx,
                    ),
                    timeout=timeout_budget,
                )
            else:
                signal = await asyncio.wait_for(
                    core_intraday_ai.generate(
                        symbol=candidate.underlying,
                        regime=regime_enum,
                        market_context=market_ctx,
                    ),
                    timeout=timeout_budget,
                )

            latency = int(__import__("time").time() * 1000) - start_ms

            # Check if AI returned NO_TRADE because of unconfigured provider
            if signal.decision == Decision.NO_TRADE and any("No AI provider" in r for r in signal.reasons):
                return AIAdviceResult(
                    status="UNAVAILABLE",
                    latency_ms=latency,
                    rationale="AI provider offline or not configured — deterministic fallback active",
                )

            # Direction reconciliation
            is_call = "CALL" in candidate.direction
            aligned = (is_call and signal.decision == Decision.LONG) or (not is_call and signal.decision == Decision.SHORT)

            base_confidence = float(signal.calibrated_confidence or signal.raw_confidence or 70.0)
            if aligned:
                score = min(95.0, max(50.0, base_confidence))
            else:
                # Disagreement or NO_TRADE
                score = max(20.0, 100.0 - base_confidence) if signal.decision != Decision.NO_TRADE else 50.0

            return AIAdviceResult(
                status="AVAILABLE",
                score=round(score, 1),
                confidence=round(score / 100.0, 2),
                rationale="; ".join(signal.reasons) or f"AI desk evaluated {signal.decision.value}",
                risk_flags=list(getattr(signal, "invalidation", [])),
                latency_ms=latency,
            )
        except asyncio.TimeoutError:
            latency = int(__import__("time").time() * 1000) - start_ms
            logger.info("ai_advisory_timeout_fallback", candidate_id=candidate.candidate_id, latency_ms=latency)
            return AIAdviceResult(status="TIMEOUT", latency_ms=latency, rationale="AI advisory timed out — deterministic fallback active")
        except Exception as e:
            latency = int(__import__("time").time() * 1000) - start_ms
            logger.debug("ai_advisory_error_fallback", error=str(e), latency_ms=latency)
            return AIAdviceResult(status="UNAVAILABLE", latency_ms=latency, rationale=f"AI advisory unavailable ({str(e)})")

    def fuse(
        self,
        candidate: SignalCandidate,
        ai_result: Optional[AIAdviceResult] = None,
        ml_prediction: Optional[dict] = None,
    ) -> float:
        """Compute final fused confidence score with dynamic weight renormalization (§16).

        Missing AI/ML haircuts (§35): AI unavailable → −8pts, F&O degraded → −10pts,
        VWAP degraded → −10pts. Prevents silent renormalization inflation.
        """
        active_weights = {
            "technical": DEFAULT_WEIGHTS["technical"],
            "mtf": DEFAULT_WEIGHTS["mtf"],
            "fno": DEFAULT_WEIGHTS["fno"],
            "regime": DEFAULT_WEIGHTS["regime"],
        }
        scores = {
            "technical": candidate.technical_score,
            "mtf": candidate.mtf_score,
            "fno": candidate.fno_score,
            "regime": candidate.regime_score,
        }

        ai_available = bool(ai_result and ai_result.status == "AVAILABLE" and ai_result.score is not None)
        if ai_available:
            active_weights["ai"] = self.ai_weight
            scores["ai"] = ai_result.score  # type: ignore[union-attr]

        if ml_prediction and ml_prediction.get("is_available"):
            active_weights["ml"] = 0.07
            is_call = "CALL" in candidate.direction
            scores["ml"] = float(ml_prediction.get("bullish_pct", 50.0) if is_call else ml_prediction.get("bearish_pct", 50.0))

        # Dynamic weight renormalization (§16): weights strictly sum to 1.0
        total_w = sum(active_weights.values())
        norm_weights = {k: v / total_w for k, v in active_weights.items()}

        fused = sum(scores[k] * norm_weights[k] for k in active_weights)
        if not ai_available:
            fused -= AI_UNAVAILABLE_HAIRCUT
        if getattr(candidate, "fno_degraded", False):
            fused -= FNODEGRADED_HAIRCUT
        if getattr(candidate, "vwap_degraded", False):
            fused -= VWAPDEGRADED_HAIRCUT
        return round(float(max(5.0, min(98.0, fused))), 1)


confluence_engine = ConfluenceEngine()
