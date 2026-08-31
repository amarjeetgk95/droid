"""
AI Confirmation Engine — §§35,36,37,38,39,40,67,68
AI as confirmation/reasoning layer, not primary market-data engine.
Compact structured MarketContext → AI horizon evaluation.
Strict schema, NOT_ELIGIBLE on bad data, handles disagreement, never override deterministic safety.
"""
from __future__ import annotations

import time
import json
from dataclasses import dataclass, field
from typing import Literal, Any
from enum import Enum

AIDecision = Literal["CONFIRM", "REJECT", "WATCH", "UNCERTAIN"]
AIStatus = Literal["CONFIRMED", "REJECTED", "WATCH", "UNCERTAIN", "NOT_ELIGIBLE", "ERROR", "UNAVAILABLE", "TIMEOUT"]

@dataclass
class HorizonAIOutput:
    decision: AIDecision
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"
    confidence: int = 0
    horizon_minutes: int | None = None  # 10 for short, 119 for continuation
    max_holding_minutes: int | None = None
    reasoning: list[str] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "decision": self.decision,
            "direction": self.direction,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "invalidation_conditions": self.invalidation_conditions,
        }
        if self.horizon_minutes is not None: d["horizon_minutes"] = self.horizon_minutes
        if self.max_holding_minutes is not None: d["max_holding_minutes"] = self.max_holding_minutes
        return d

@dataclass
class AIConfirmationResponse:
    short_horizon: HorizonAIOutput
    continuation: HorizonAIOutput
    overall_assessment: dict[str, Any]
    ai_status: AIStatus = "CONFIRMED"
    error: str | None = None

@dataclass
class AIConfirmationRequest:
    instrument: str
    asset_class: str
    market_session: str
    data_freshness: str
    data_quality: str
    market_regime: str
    price_action: dict
    structure: str
    momentum: str
    volume: str
    futures: str | None = None
    options_oi: dict | None = None
    vwap: str | None = None
    volatility: str | None = None
    liquidity: str | None = None
    support_resistance: dict | None = None
    cross_market: dict | None = None
    synchronization_status: str = "UNKNOWN"
    supporting_evidence: list[dict] = field(default_factory=list)
    contradictory_evidence: list[dict] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    stale_evidence: list[str] = field(default_factory=list)
    proposed_setup: dict | None = None  # breakout output
    short_horizon_proposed: dict | None = None
    continuation_proposed: dict | None = None


class AIConfirmationEngine:
    """
    ValidatesMarketContext → calls AI provider → strict schema validation → structured output.
    Returns NOT_ELIGIBLE if critical data invalid (§38).
    """

    # Critical data gate — do not allow AI to create false confidence (§38)
    INELIGIBLE_FRESHNESS = {"STALE", "FEED_DEGRADED", "SEQUENCE_GAP", "DISCONNECTED", "INVALID", "SNAPSHOT_UNSYNCED", "CONTRACT_SPEC_MISSING"}

    def is_eligible(self, req: AIConfirmationRequest) -> tuple[bool, str | None]:
        if req.data_freshness in self.INELIGIBLE_FRESHNESS or req.data_quality in ("STALE", "INVALID", "FEED_DEGRADED", "SEQUENCE_GAP"):
            return False, f"AI_STATUS=NOT_ELIGIBLE data_freshness={req.data_freshness} data_quality={req.data_quality}"
        if req.synchronization_status == "CROSS_MARKET_DATA_NOT_SYNCHRONIZED" and req.cross_market and req.cross_market.get("uses_cross_market"):
            return False, "AI_STATUS=NOT_ELIGIBLE CROSS_MARKET_DATA_NOT_SYNCHRONIZED"
        if "CONTRACT_SPEC_MISSING" in req.missing_evidence:
            return False, "AI_STATUS=NOT_ELIGIBLE CONTRACT_SPEC_MISSING"
        return True, None

    def build_prompt_context(self, req: AIConfirmationRequest) -> dict:
        """Compact structured context — do not send uncontrolled raw streams (§35)"""
        return {
            "instrument": req.instrument,
            "asset_class": req.asset_class,
            "market_session": req.market_session,
            "data_freshness": req.data_freshness,
            "data_quality": req.data_quality,
            "market_regime": req.market_regime,
            "price_action": req.price_action,
            "structure": req.structure,
            "momentum": req.momentum,
            "volume": req.volume,
            "futures": req.futures,
            "options_oi": req.options_oi,
            "vwap": req.vwap,
            "volatility": req.volatility,
            "liquidity": req.liquidity,
            "support_resistance": req.support_resistance,
            "cross_market": req.cross_market,
            "synchronization_status": req.synchronization_status,
            "supporting_evidence": req.supporting_evidence,
            "contradictory_evidence": req.contradictory_evidence,
            "missing_evidence": req.missing_evidence,
            "stale_evidence": req.stale_evidence,
            "proposed_setup": req.proposed_setup,
            "short_horizon_proposed": req.short_horizon_proposed,
            "continuation_proposed": req.continuation_proposed,
        }

    def validate_response_schema(self, raw: dict | str) -> tuple[bool, dict | None, str | None]:
        """
        Strict schema validation (§39). Allowed decisions CONFIRM/REJECT/WATCH/UNCERTAIN.
        If validation fails → AI_STATUS = ERROR (§39).
        """
        # Parse if string
        parsed: dict
        if isinstance(raw, str):
            try:
                # Strip fences
                s = raw.strip()
                if s.startswith("```"):
                    # remove markdown fences
                    lines = s.split("\n")
                    # strip first and last fence lines
                    if lines[0].startswith("```"): lines = lines[1:]
                    if lines and lines[-1].strip().startswith("```"): lines = lines[:-1]
                    s = "\n".join(lines)
                parsed = json.loads(s)
            except Exception as e:
                return False, None, f"AI_SCHEMA_ERROR invalid JSON: {e}"
        else:
            parsed = raw

        # Required top-level keys
        for key in ("short_horizon", "continuation", "overall_assessment"):
            if key not in parsed:
                return False, None, f"AI_SCHEMA_ERROR missing key {key}"

        allowed = {"CONFIRM", "REJECT", "WATCH", "UNCERTAIN"}
        for horizon_key in ("short_horizon", "continuation"):
            h = parsed[horizon_key]
            if not isinstance(h, dict):
                return False, None, f"AI_SCHEMA_ERROR {horizon_key} not object"
            if "decision" not in h or h["decision"] not in allowed:
                return False, None, f"AI_SCHEMA_ERROR {horizon_key}.decision must be one of {allowed}"
            if "direction" in h and h["direction"] not in ("BULLISH", "BEARISH", "NEUTRAL"):
                return False, None, f"AI_SCHEMA_ERROR {horizon_key}.direction invalid"
            if "confidence" in h:
                c = h["confidence"]
                if not isinstance(c, (int, float)) or not (0 <= c <= 100):
                    return False, None, f"AI_SCHEMA_ERROR {horizon_key}.confidence 0-100"
            if "reasoning" in h and not isinstance(h["reasoning"], list):
                return False, None, f"AI_SCHEMA_ERROR {horizon_key}.reasoning must be list"
            if "invalidation_conditions" in h and not isinstance(h["invalidation_conditions"], list):
                return False, None, f"AI_SCHEMA_ERROR {horizon_key}.invalidation_conditions must be list"

        overall = parsed["overall_assessment"]
        if not isinstance(overall, dict):
            return False, None, "AI_SCHEMA_ERROR overall_assessment not object"

        return True, parsed, None

    async def confirm(
        self,
        req: AIConfirmationRequest,
        timeout_s: float = 15.0,
        ai_provider_callable=None,  # async def(prompt_ctx)->dict|str
    ) -> AIConfirmationResponse:
        eligible, reason = self.is_eligible(req)
        if not eligible:
            return AIConfirmationResponse(
                short_horizon=HorizonAIOutput(decision="REJECT", reasoning=[reason or "not eligible"], invalidation_conditions=[]),
                continuation=HorizonAIOutput(decision="REJECT", reasoning=[reason or "not eligible"], invalidation_conditions=[]),
                overall_assessment={"market_bias": "NEUTRAL", "breakout_quality": 0, "false_breakout_risk": 100},
                ai_status="NOT_ELIGIBLE",
                error=reason,
            )
        if ai_provider_callable is None:
            # No AI configured — explicit UNAVAILABLE, never mock (§67)
            return AIConfirmationResponse(
                short_horizon=HorizonAIOutput(decision="UNCERTAIN", reasoning=["AI unavailable — no provider configured"], invalidation_conditions=[]),
                continuation=HorizonAIOutput(decision="UNCERTAIN", reasoning=["AI unavailable"], invalidation_conditions=[]),
                overall_assessment={"market_bias": "NEUTRAL", "breakout_quality": 0, "false_breakout_risk": 50},
                ai_status="UNAVAILABLE",
                error="AI_UNAVAILABLE no provider",
            )
        # Build compact context
        prompt_ctx = self.build_prompt_context(req)
        # Call AI with timeout
        try:
            import asyncio
            raw = await asyncio.wait_for(ai_provider_callable(prompt_ctx), timeout=timeout_s)
        except asyncio.TimeoutError:
            return AIConfirmationResponse(
                short_horizon=HorizonAIOutput(decision="UNCERTAIN", reasoning=["AI timeout"], invalidation_conditions=[]),
                continuation=HorizonAIOutput(decision="UNCERTAIN", reasoning=["AI timeout"], invalidation_conditions=[]),
                overall_assessment={"market_bias": "NEUTRAL", "breakout_quality": 0, "false_breakout_risk": 50},
                ai_status="TIMEOUT",
                error="AI_TIMEOUT",
            )
        except Exception as e:
            return AIConfirmationResponse(
                short_horizon=HorizonAIOutput(decision="UNCERTAIN", reasoning=[f"AI provider error: {e}"], invalidation_conditions=[]),
                continuation=HorizonAIOutput(decision="UNCERTAIN", reasoning=[f"AI provider error: {e}"], invalidation_conditions=[]),
                overall_assessment={"market_bias": "NEUTRAL", "breakout_quality": 0, "false_breakout_risk": 50},
                ai_status="ERROR",
                error=f"AI_PROVIDER_ERROR {e}",
            )
        # Schema validation
        ok, parsed, err = self.validate_response_schema(raw)
        if not ok:
            return AIConfirmationResponse(
                short_horizon=HorizonAIOutput(decision="UNCERTAIN", reasoning=[err or "schema error"], invalidation_conditions=[]),
                continuation=HorizonAIOutput(decision="UNCERTAIN", reasoning=[err or "schema error"], invalidation_conditions=[]),
                overall_assessment={"market_bias": "NEUTRAL", "breakout_quality": 0, "false_breakout_risk": 50},
                ai_status="ERROR",
                error=err,
            )
        assert parsed is not None
        # Map to structured outputs
        sh = parsed["short_horizon"]
        co = parsed["continuation"]
        overall = parsed["overall_assessment"]
        return AIConfirmationResponse(
            short_horizon=HorizonAIOutput(
                decision=sh["decision"], direction=sh.get("direction", "NEUTRAL"),
                confidence=int(sh.get("confidence", 0)),
                horizon_minutes=sh.get("horizon_minutes", 10),
                max_holding_minutes=sh.get("max_holding_minutes"),
                reasoning=sh.get("reasoning", []), invalidation_conditions=sh.get("invalidation_conditions", []),
            ),
            continuation=HorizonAIOutput(
                decision=co["decision"], direction=co.get("direction", "NEUTRAL"),
                confidence=int(co.get("confidence", 0)),
                horizon_minutes=co.get("horizon_minutes"),
                max_holding_minutes=co.get("max_holding_minutes", 119),
                reasoning=co.get("reasoning", []), invalidation_conditions=co.get("invalidation_conditions", []),
            ),
            overall_assessment=overall,
            ai_status="CONFIRMED" if any(h.get("decision") == "CONFIRM" for h in (sh, co)) else "UNCERTAIN",
        )

    # Synchronous helper for deterministic fallback (rule-based) — used when AI not configured but need to evaluate
    def deterministic_fallback(self, req: AIConfirmationRequest, short_status: str, cont_status: str, confidence_short: int, confidence_cont: int) -> AIConfirmationResponse:
        """
        Not a mock AI — deterministic mapping from quantitative horizon statuses.
        Used only when provider unavailable and caller explicitly requests deterministic evaluation.
        Must be marked as such.
        """
        def map_status(s: str) -> AIDecision:
            if s == "CONFIRMED": return "CONFIRM"
            if s == "REJECTED": return "REJECT"
            if s == "WATCH": return "WATCH"
            return "UNCERTAIN"
        # Note: caller must handle UNAVAILABLE propagation — this helper is for testing/backtest
        return AIConfirmationResponse(
            short_horizon=HorizonAIOutput(decision=map_status(short_status), confidence=confidence_short, horizon_minutes=10),
            continuation=HorizonAIOutput(decision=map_status(cont_status), confidence=confidence_cont, max_holding_minutes=119),
            overall_assessment={"market_bias": "NEUTRAL", "breakout_quality": 50, "false_breakout_risk": 50, "source": "deterministic_fallback"},
            ai_status="UNAVAILABLE",
            error="deterministic fallback — not AI confirmation",
        )


ai_confirmation_engine = AIConfirmationEngine()
