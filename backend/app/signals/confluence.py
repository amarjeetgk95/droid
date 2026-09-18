"""
Institutional Confluence Engine with Desk-Specific AI & Dynamic Weight Renormalization (§16, §35)
Quality target: 80% win rate.

Unified weights (backend/config/scoring_weights.json v2):
  - Technical: 40%
  - MTF: 20%
  - F&O: 15% (+5% event_risk via overlay sizing, total 20% F&O domain)
  - Regime: 10%
  - AI Advisory: <= 10% (Capped, desk-specific timeout)
  - ML Predictor: <= 7% (When available)

Baseline is neutral (50.0) — each domain must EARN its contribution by scoring > 55.
Scores below 45 are penalized. 2+ penalized domains → −10 fused penalty.
ARMED threshold raised to 78.0.
"""
from __future__ import annotations

import asyncio
from typing import Optional
import structlog
from pydantic import BaseModel, Field

from app.core.json_config import load_json_config
from app.signals.strategies.base import SignalCandidate

logger = structlog.get_logger()


def _load_confluence_config() -> dict:
    # P0-2 FAIL-CLOSE: required=True — a missing file raises JSONConfigError
    # instead of arming on a silent fallback.
    return load_json_config("scoring_weights.json", required=True)


def _validate_confluence_config(config: dict) -> dict:
    """P0-2 FAIL-CLOSE: scoring config is load-bearing. A missing thresholds
    block means we cannot prove the ARMED bar — refuse to start rather than
    arming on a silent 70.0 fallback.
    """
    if not config or "thresholds" not in config or "armed" not in config.get("thresholds", {}):
        raise RuntimeError(
            "scoring_weights.json missing thresholds.armed — fail-closed startup: "
            "refusing to run confluence without an explicit ARMED bar"
        )
    return config


_CONFIG = _validate_confluence_config(_load_confluence_config())
_WF = _CONFIG.get("weights_fraction", {})
_THRESH = _CONFIG.get("thresholds", {})
_PEN = _CONFIG.get("penalties", {})

DEFAULT_WEIGHTS = {
    "technical": float(_WF.get("technical", 0.40)),
    "mtf": float(_WF.get("mtf", 0.20)),
    "fno": float(_WF.get("fno", 0.15)),
    "regime": float(_WF.get("regime", 0.10)),
    "ai": float(_WF.get("ai", 0.10)),
}
# P0-2: ARMED bar is 78.0, hardcoded. The config file must exist (checked
# above) but the bar itself is not negotiable via config drift.
ARMED_THRESHOLD = 78.0
AI_UNAVAILABLE_HAIRCUT = float(_PEN.get("ai_unavailable_haircut", 8.0))
FNODEGRADED_HAIRCUT = float(_PEN.get("fno_degraded_haircut", 10.0))
VWAPDEGRADED_HAIRCUT = float(_PEN.get("vwap_degraded_haircut", 10.0))
# P0-2: degraded feeds must hurt. Cap raised 12 -> 24 so stacked
# AI-missing + FNO-degraded + VWAP-degraded cannot hide behind the cap.
MAX_TOTAL_HAIRCUT = 24.0


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
                # P0-2: an AI that actively OPPOSES the candidate is a hard
                # contrarian flag — never let it score above 44 (penalty zone).
                try:
                    from app.ai.schemas import Decision as _Dec
                    _opposes = (
                        (is_call and signal.decision == _Dec.SHORT)
                        or ((not is_call) and signal.decision == _Dec.LONG)
                    )
                    if _opposes:
                        score = min(float(score), 44.0)
                except Exception as e:
                    logger.debug("ai_opposition_cap_skipped", error=str(e)[:150])

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
        institutional: Optional[dict] = None,
    ) -> float:
        """Compute final fused confidence score with quality-aware weighting.

        Baseline is neutral (50.0) — each domain must EARN its contribution by scoring > 55.
        Scores below 45 are penalized. 2+ penalized domains → −10 fused penalty.
        Missing AI/ML/F&O/VWAP haircuts applied. ARMED threshold is 78.0.

        institutional (optional, PIT-safe only): {"delta": float in [-5,5],
        "applied": bool, "reasons": [...]} from
        app.signals.institutional_overlay.compute_institutional_adjustment.
        Applied AFTER haircuts, capped, never overrides gates. Unverifiable
        (pit_ok False / None) is ignored.
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

        # Quality-aware weighting (P0-2): only domains scoring > 55 earn full
        # weight. 45-55 neutral contributes HALF weight (weak agreement is not
        # confluence). < 45 is an active penalty. 2+ penalties → −10 fused.
        total_w = 0.0
        fused = 0.0
        penalty_count = 0
        contributing_domains = 0
        for domain, w in active_weights.items():
            s = scores.get(domain, 50.0)
            try:
                s = float(s)
            except Exception:
                s = 50.0
            if s >= 55.0:
                fused += s * w
                total_w += w
                contributing_domains += 1
            elif s < 45.0:
                penalty_count += 1
            else:
                # 45-55 neutral: half weight — counts as weak, not full.
                fused += s * (w * 0.5)
                total_w += w * 0.5

        if total_w > 0:
            fused = fused / total_w
        else:
            fused = 50.0

        if penalty_count >= 2:
            fused -= 10.0

        raw_haircut = 0.0
        if not ai_available:
            raw_haircut += AI_UNAVAILABLE_HAIRCUT
        if getattr(candidate, "fno_degraded", False):
            raw_haircut += FNODEGRADED_HAIRCUT
        if getattr(candidate, "vwap_degraded", False):
            raw_haircut += VWAPDEGRADED_HAIRCUT

        # Cap cumulative infrastructure haircut so degraded feeds don't kill high confluence
        fused -= min(raw_haircut, MAX_TOTAL_HAIRCUT)

        # Institutional overlay (PIT-safe, capped +-5, never overrides gates).
        try:
            if isinstance(institutional, dict) and institutional.get("applied"):
                _d = float(institutional.get("delta", 0.0) or 0.0)
                _d = max(-5.0, min(5.0, _d))
                fused += _d
        except Exception as e:
            logger.debug("institutional_overlay_adjust_skipped", error=str(e)[:150])
        # P0-2 ARMED bar: >=3 contributing domains AND zero penalties.
        # Thin or contested confluence can never print an ARMED-grade score —
        # cap it below the bar so the FSM stays VALIDATED (WATCH).
        try:
            if contributing_domains < 3 or penalty_count > 0:
                fused = min(float(fused), ARMED_THRESHOLD - 0.1)
        except Exception as e:
            logger.debug("armed_threshold_cap_skipped", error=str(e)[:150])
        return round(float(max(15.0, min(98.0, fused))), 1)


confluence_engine = ConfluenceEngine()
