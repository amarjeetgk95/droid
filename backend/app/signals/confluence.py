"""
Institutional Confluence Engine with Strict AI Advisory Isolation
Weights:
  - Technical: 40%
  - MTF: 20%
  - F&O: 20%
  - Regime: 10%
  - AI Advisory: <= 10% (Capped, 1500ms timeout)
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Optional, Any
import structlog
from pydantic import BaseModel, Field

from app.signals.strategies.base import SignalCandidate

logger = structlog.get_logger()

DEFAULT_WEIGHTS = {
    "technical": 0.40,
    "mtf": 0.20,
    "fno": 0.20,
    "regime": 0.10,
    "ai": 0.10,
}


class AIAdviceResult(BaseModel):
    status: str = "UNAVAILABLE"  # AVAILABLE, UNAVAILABLE, TIMEOUT, ERROR
    score: Optional[float] = None
    confidence: Optional[float] = None
    rationale: Optional[str] = None
    risk_flags: list[str] = Field(default_factory=list)
    latency_ms: int = 0


class ConfluenceEngine:
    """
    Evaluates multi-domain confluence and applies advisory AI scoring with strict isolation.
    """

    def __init__(self, ai_weight: float = 0.10):
        assert 0.0 <= ai_weight <= 0.10, "AI weight cannot exceed 0.10 (10%) per master contract §35"
        self.ai_weight = ai_weight

    async def fetch_ai_advisory(self, candidate: SignalCandidate, context_snapshot: dict) -> AIAdviceResult:
        """Query AI service with strict 1500ms timeout. Defaults to UNAVAILABLE on failure."""
        start_ms = int(__import__("time").time() * 1000)
        try:
            from app.services.ai_service import ai_service
            # Wrap AI call in 1500ms timeout
            async def _call():
                # Provide structured prompt to AI service
                summary = f"Validate {candidate.strategy} {candidate.direction} on {candidate.underlying} at {candidate.spot_price}. Technical: {candidate.technical_score}, MTF: {candidate.mtf_score}, FNO: {candidate.fno_score}."
                return await ai_service.get_quick_bias(summary)

            raw_res = await asyncio.wait_for(_call(), timeout=1.5)
            latency = int(__import__("time").time() * 1000) - start_ms
            score = float(raw_res.get("score", 70.0)) if isinstance(raw_res, dict) else 70.0
            return AIAdviceResult(
                status="AVAILABLE",
                score=score,
                confidence=float(raw_res.get("confidence", 0.75)) if isinstance(raw_res, dict) else 0.75,
                rationale=raw_res.get("rationale") if isinstance(raw_res, dict) else "AI confirmation supportive",
                risk_flags=raw_res.get("risk_flags", []) if isinstance(raw_res, dict) else [],
                latency_ms=latency,
            )
        except asyncio.TimeoutError:
            latency = int(__import__("time").time() * 1000) - start_ms
            logger.info("ai_advisory_timeout_fallback", candidate_id=candidate.candidate_id, latency_ms=latency)
            return AIAdviceResult(status="TIMEOUT", latency_ms=latency, rationale="AI advisory timed out (>1500ms) — deterministic fallback active")
        except Exception as e:
            latency = int(__import__("time").time() * 1000) - start_ms
            logger.debug("ai_advisory_error_fallback", error=str(e), latency_ms=latency)
            return AIAdviceResult(status="UNAVAILABLE", latency_ms=latency, rationale=f"AI advisory unavailable ({str(e)})")

    def fuse(self, candidate: SignalCandidate, ai_result: Optional[AIAdviceResult] = None) -> float:
        """Compute final fused confidence score."""
        w_tech = DEFAULT_WEIGHTS["technical"]
        w_mtf = DEFAULT_WEIGHTS["mtf"]
        w_fno = DEFAULT_WEIGHTS["fno"]
        w_regime = DEFAULT_WEIGHTS["regime"]
        w_ai = self.ai_weight

        if ai_result and ai_result.status == "AVAILABLE" and ai_result.score is not None:
            fused = (
                (candidate.technical_score * w_tech) +
                (candidate.mtf_score * w_mtf) +
                (candidate.fno_score * w_fno) +
                (candidate.regime_score * w_regime) +
                (ai_result.score * w_ai)
            )
        else:
            # Re-normalize deterministic weights to sum to 1.0 without AI
            det_sum = w_tech + w_mtf + w_fno + w_regime
            fused = (
                (candidate.technical_score * (w_tech / det_sum)) +
                (candidate.mtf_score * (w_mtf / det_sum)) +
                (candidate.fno_score * (w_fno / det_sum)) +
                (candidate.regime_score * (w_regime / det_sum))
            )

        return round(float(fused), 1)

    async def fetch_historical_evidence(self, candidate: SignalCandidate, candles: list) -> Optional[dict]:
        """Query Historical Intelligence Engine (HIE) in Mode B for candidate setup evidence (§24)."""
        try:
            from app.historical_intelligence import hie_service, CandleData
            hie_candles = [
                CandleData(
                    timestamp_utc=int(c.timestamp.timestamp() * 1000) if hasattr(c, "timestamp") else 0,
                    open=c.open,
                    high=c.high,
                    low=c.low,
                    close=c.close,
                    volume=float(c.volume),
                )
                for c in candles
            ]
            res = await hie_service.analyze_state(
                instrument=candidate.underlying,
                candles=hie_candles,
                mode="CANDIDATE",
                candidate_meta={"strategy_id": candidate.strategy},
            )
            return res.model_dump(mode="json")
        except Exception as e:
            logger.debug("hie_candidate_evidence_failed", error=str(e))
            return None


confluence_engine = ConfluenceEngine()

