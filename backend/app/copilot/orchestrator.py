"""Copilot Orchestrator (spec §4, §39).

The only path from a user question to a structured copilot answer:

  USER → intent router → parallel market context → feature fusion
  → levels → confluence → scenario/prediction engine → signal gates
  → invalidation → LLM explanation → structured response → prediction audit.

The LLM synthesizes quantitative evidence; it is never the source of truth.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import structlog

from app.copilot.confluence import evaluate_confluence
from app.copilot.enums import (
    ANALOG_ENGINE_VERSION,
    CALIBRATION_VERSION,
    COPILOT_VERSION,
    DIRECTION_LABEL,
    DIRECTION_TONE,
    FEATURE_ENGINE_VERSION,
    GATE_ENGINE_VERSION,
    HORIZON_LABELS,
    PREDICTION_ENGINE_VERSION,
    PROMPT_VERSION,
)
from app.copilot.explanation import deterministic_explanation, explanation_layer
from app.copilot.feature_fusion import derive_factors
from app.copilot.historical_analog import historical_analog_engine
from app.copilot.intent_router import TOOL_GATHERERS, IntentContext, intent_router
from app.copilot.invalidation import build_invalidation
from app.copilot.levels import build_levels, evaluate_breakout
from app.copilot.market_context import market_context_builder
from app.copilot.models import (
    CopilotAnalysisResponse,
    CopilotAnalyzeRequest,
    CopilotAuditRecord,
    CopilotChatRequest,
    CopilotEvidence,
    CopilotMeta,
    CopilotSummary,
    CopilotVersions,
    Factor,
    IntentDecision,
    MarketContext,
)
from app.copilot.prediction import prediction_engine
from app.copilot.sanitizer import sanitize_text
from app.copilot.scenarios import probability_available
from app.copilot.validation import signal_validation_engine

logger = structlog.get_logger()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class CopilotOrchestrator:
    """Runs the full evidence pipeline and returns a structured response."""

    def __init__(
        self,
        router: Any = None,
        context_builder: Any = None,
        predictor: Any = None,
    ) -> None:
        self._router = router or intent_router
        self._contexts = context_builder or market_context_builder
        self._engine = predictor or prediction_engine

    # ------------------------------------------------------------------ #
    async def analyze(self, request: CopilotAnalyzeRequest) -> CopilotAnalysisResponse:
        started = time.perf_counter()
        request_id = _new_id("cop")

        decision = self._router.decide(
            request.query or "",
            IntentContext(ui_symbol=(request.symbol or "NIFTY").upper()),
            symbol=None,
            requested_horizon=request.horizon,
            requested_intent=request.intent,
        )
        log_kwargs = {
            "request_id": request_id,
            "intent": decision.intent,
            "symbol": decision.symbol,
            "horizon": decision.horizon,
            "tools": decision.tool_plan,
        }

        gatherers = self._gatherers_for(decision)
        try:
            ctx = await self._contexts.build(decision.symbol, decision.horizon, gatherers, use_cache=True)
        except Exception as exc:  # a totally dead feed still yields a structured answer
            logger.warning("copilot_context_failed", error=str(exc)[:200], **log_kwargs)
            ctx = MarketContext(symbol=decision.symbol, horizon=decision.horizon)  # type: ignore[arg-type]

        if decision.requires_historical:
            try:
                ctx.historical = await historical_analog_engine.query(decision.symbol, decision.horizon)
            except Exception as exc:  # optional evidence, never fatal
                logger.info("copilot_historical_failed", error=str(exc)[:160])
        else:
            ctx.historical.message = "Historical analogs were not requested for this intent."

        factors = derive_factors(ctx)
        levels = build_levels(ctx)
        confluence = evaluate_confluence(factors)

        # Breakout feasibility for an explicit level (BREAKOUT_ANALYSIS).
        breakout = evaluate_breakout(ctx, decision.breakout_level) if decision.requires_breakout else {}

        factors = derive_factors(ctx)
        levels = build_levels(ctx)
        confluence = evaluate_confluence(factors)

        breakout = evaluate_breakout(ctx, decision.breakout_level) if decision.requires_breakout else {}

        prediction, scenarios, prediction_warnings = await self._engine.predict(ctx, levels, confluence, factors)
        invalidation = build_invalidation(ctx, confluence, levels)
        evidence = self._evidence(factors, confluence)

        validation_result = None
        if decision.requires_signal_validation:
            try:
                signal = signal_validation_engine.resolve_signal(
                    decision.symbol,
                    signal_id=request.signal_id,
                    direction=self._hinted_direction(request.query or ""),
                    entry=request.entry_price,
                    stop=request.stop_loss,
                    target=request.target_price,
                )
                validation_result = signal_validation_engine.evaluate(ctx, factors, confluence, signal, levels)
            except Exception as exc:
                logger.info("copilot_validation_failed", error=str(exc)[:160])

        payload = self._llm_payload(decision, ctx, factors, confluence, levels, scenarios, evidence, validation_result, breakout)
        explanation, explanation_source, explanation_warnings = ("", "DETERMINISTIC", ["Explanation disabled."])
        if request.explain:
            provider = request.provider or "openrouter"
            explanation, explanation_source, explanation_warnings = await explanation_layer.explain(
                payload,
                provider=provider,
                model=request.model,
                keys={
                    "openrouter_api_key": request.openrouter_api_key,
                    "gemini_api_key": request.gemini_api_key,
                    "openai_api_key": request.openai_api_key,
                    "ollama_base_url": request.ollama_base_url,
                    "ollama_model": request.ollama_model,
                },
            )
        explanation, _flags = sanitize_text(explanation)

        latency_ms = int((time.perf_counter() - started) * 1000)
        analysis_id = _new_id("ana")
        response = self._assemble(
            decision=decision,
            ctx=ctx,
            factors=factors,
            confluence=confluence,
            levels=levels,
            scenarios=scenarios,
            evidence=evidence,
            validation_result=validation_result,
            invalidation=invalidation,
            prediction=prediction,
            explanation=explanation,
            explanation_source=explanation_source,
            breakout=breakout,
            warnings=[*decision.warnings, *prediction_warnings, *explanation_warnings],
            latency_ms=latency_ms,
            analysis_id=analysis_id,
            provider=(request.provider or "openrouter"),
            model=request.model,
        )

        try:
            await self._audit(response, ctx, factors, prediction, decision)
        except Exception as exc:  # audit must never break the response
            logger.info("copilot_audit_failed", error=str(exc)[:160])

        tools_ok = [s.source for s in ctx.data_quality.sources if s.status in ("FRESH", "STALE")]
        tools_failed = [s.source for s in ctx.data_quality.sources if s.status in ("UNAVAILABLE", "ERROR")]
        logger.info(
            "copilot_analysis_completed",
            request_id=request_id,
            intent=decision.intent,
            symbol=decision.symbol,
            horizon=decision.horizon,
            tools_requested=decision.tool_plan,
            tools_successful=tools_ok,
            tools_failed=tools_failed,
            latency_ms=latency_ms,
            model_used=request.model,
            prediction_engine_version=PREDICTION_ENGINE_VERSION,
        )
        return response

    # ------------------------------------------------------------------ #
    async def analyze_chat(self, request: CopilotChatRequest) -> CopilotAnalysisResponse:
        """Conversational follow-up that reuses prior structured context.

        "Why bearish?" / "What would invalidate it?" are answered from the
        current evidence: symbol/horizon carry over and the response is rebuilt
        from the same pipeline rather than from free-form chat memory.
        """
        turns = [t for t in (request.messages or []) if (t.content or "").strip()]
        last_user = next((t.content for t in reversed(turns) if t.role == "user"), "")
        inferred = self._followup_kind(last_user)
        previous_id = request.previous_analysis_id

        if inferred == "invalidate":
            payload = CopilotAnalyzeRequest(
                symbol=request.symbol,
                query=(last_user or "market outlook") + " invalidation triggers",
                horizon=request.horizon,
                depth=request.depth,
                provider=request.provider,
                model=request.model,
                allow_paid=request.allow_paid,
                explain=request.explain,
                openrouter_api_key=request.openrouter_api_key,
                gemini_api_key=request.gemini_api_key,
                openai_api_key=request.openai_api_key,
                ollama_base_url=request.ollama_base_url,
                ollama_model=request.ollama_model,
                previous_analysis_id=previous_id,
            )
            return await self.analyze(payload)

        return await self.analyze(
            CopilotAnalyzeRequest(
                symbol=request.symbol,
                query=(last_user or "market status") + (" why explain evidence" if inferred == "why" else ""),
                horizon=request.horizon,
                depth=request.depth,
                provider=request.provider,
                model=request.model,
                allow_paid=request.allow_paid,
                explain=True,
                openrouter_api_key=request.openrouter_api_key,
                gemini_api_key=request.gemini_api_key,
                openai_api_key=request.openai_api_key,
                ollama_base_url=request.ollama_base_url,
                ollama_model=request.ollama_model,
                previous_analysis_id=previous_id,
            )
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _gatherers_for(decision: IntentDecision) -> set[str]:
        gatherers: set[str] = set()
        for tool in decision.tool_plan:
            gatherers.update(TOOL_GATHERERS.get(tool, ()))
        gatherers.discard("historical")  # handled separately (heavyweight, on demand)
        gatherers.add("quote")
        return gatherers

    @staticmethod
    def _hinted_direction(query: str) -> str | None:
        lowered = (query or "").lower()
        if any(token in lowered for token in ("long", "buy", "bullish", "call")):
            return "LONG"
        if any(token in lowered for token in ("short", "sell", "bearish", "put")):
            return "SHORT"
        return None

    @staticmethod
    def _followup_kind(text: str) -> str:
        lowered = (text or "").lower()
        if any(token in lowered for token in ("invalidat", "what would break", "what breaks")):
            return "invalidate"
        if lowered.startswith("why") or "why " in lowered or "explain" in lowered:
            return "why"
        return "fresh"


    # ------------------------------------------------------------------ #
    @staticmethod
    def _evidence(factors: dict[str, Factor], confluence: Any) -> CopilotEvidence:
        bullish: list[str] = []
        bearish: list[str] = []
        neutral: list[str] = []
        for key, factor in factors.items():
            label = key.replace("_", " ").title()
            if factor.state == "BULLISH":
                bullish.append(f"{label} BULLISH ({factor.strength:.2f}) — {factor.evidence[0] if factor.evidence else 'no evidence'}")
            elif factor.state == "BEARISH":
                bearish.append(f"{label} BEARISH ({factor.strength:.2f}) — {factor.evidence[0] if factor.evidence else 'no evidence'}")
            elif factor.state == "NEUTRAL":
                neutral.append(f"{label} NEUTRAL — {factor.evidence[0] if factor.evidence else 'balanced'}")
            else:
                neutral.append(f"{label} unavailable — {(factor.evidence[0] if factor.evidence else 'no data')}")
        return CopilotEvidence(
            bullish=bullish,
            bearish=bearish,
            neutral=neutral,
            conflicts=list(getattr(confluence, "conflicting_factors", []) or []),
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _llm_payload(
        decision: IntentDecision,
        ctx: MarketContext,
        factors: dict[str, Factor],
        confluence: Any,
        levels: Any,
        scenarios: list,
        evidence: CopilotEvidence,
        validation_result: Any,
        breakout: dict,
    ) -> dict:
        """The ONLY payload the LLM ever sees: structured evidence, nothing else."""
        return {
            "symbol": decision.symbol,
            "horizon": decision.horizon,
            "intent": decision.intent,
            "direction": confluence.dominant_state,
            "regime": ctx.regime.name,
            "ltp": ctx.price.ltp,
            "market_state": ctx.model_dump(mode="json"),
            "factors": {key: factor.model_dump(mode="json") for key, factor in factors.items()},
            "confluence": confluence.model_dump(mode="json"),
            "levels": levels.model_dump(mode="json"),
            "scenarios": [s.model_dump(mode="json") for s in scenarios],
            "evidence": evidence.model_dump(mode="json"),
            "historical": ctx.historical.model_dump(mode="json"),
            "validation": validation_result.model_dump(mode="json") if validation_result else None,
            "breakout": breakout,
            "data_quality": ctx.data_quality.model_dump(mode="json"),
        }


    # ------------------------------------------------------------------ #
    def _assemble(
        self,
        decision: IntentDecision,
        ctx: MarketContext,
        factors: dict[str, Factor],
        confluence: Any,
        levels: Any,
        scenarios: list,
        evidence: CopilotEvidence,
        validation_result: Any,
        invalidation: Any,
        prediction: Any,
        explanation: str,
        explanation_source: str,
        breakout: dict,
        warnings: list[str],
        latency_ms: int,
        analysis_id: str,
        provider: str,
        model: str | None,
    ) -> CopilotAnalysisResponse:
        fresh = [s for s in ctx.data_quality.sources if s.status == "FRESH"]
        stale = [s for s in ctx.data_quality.sources if s.status == "STALE"]
        data_freshness = "LIVE" if fresh and not ctx.partial else ("DELAYED" if fresh else ("STALE" if stale else "OFFLINE"))
        if not probability_available(scenarios):
            warnings = [*warnings, "Scenario probabilities unavailable — no calibrated model is wired for this horizon."]

        versions = CopilotVersions(
            copilot=COPILOT_VERSION,
            feature_engine=FEATURE_ENGINE_VERSION,
            prediction_model=getattr(prediction, "model_version", PREDICTION_ENGINE_VERSION),
            calibration=CALIBRATION_VERSION,
            prompt=PROMPT_VERSION,
            analog_engine=ANALOG_ENGINE_VERSION,
            gate_engine=GATE_ENGINE_VERSION,
        )
        confidence_value = self._headline_confidence(prediction, confluence, ctx)
        summary = CopilotSummary(
            regime=ctx.regime.name,
            direction=confluence.dominant_state,
            bias_label=DIRECTION_LABEL.get(confluence.dominant_state, confluence.dominant_state),
            tone=DIRECTION_TONE.get(confluence.dominant_state, "warn"),
            confidence=confidence_value,
            expected_range=dict(getattr(prediction, "expected_range", {}) or {}),
            ltp=ctx.price.ltp,
            change_pct=ctx.price.change_pct,
        )
        return CopilotAnalysisResponse(
            version="1.0",
            meta=CopilotMeta(
                analysis_id=analysis_id,
                symbol=decision.symbol,
                intent=decision.intent,
                horizon=decision.horizon,
                latency_ms=latency_ms,
                sources_count=len(fresh),
                data_freshness=data_freshness,  # type: ignore[arg-type]
                partial=ctx.partial,
                missing_sources=list(ctx.missing_sources),
                versions=versions,
                provider=provider,
                model=model,
                classifier=decision.classifier,
            ),
            summary=summary,
            market_state=ctx,
            factors=factors,
            confluence=confluence,
            levels=levels,
            scenarios=scenarios,
            evidence=evidence,
            historical=ctx.historical,
            validation=validation_result,
            prediction=prediction,
            invalidation=invalidation,
            explanation=explanation,
            explanation_source=explanation_source,
            warnings=[w for w in dict.fromkeys(warnings) if w],
            data_quality=ctx.data_quality,
            tools=[*decision.tool_plan, *([f"breakout:{breakout.get('level')}"] if breakout else [])],
        )

    @staticmethod
    def _headline_confidence(prediction: Any, confluence: Any, ctx: MarketContext) -> float | None:
        confidence = getattr(prediction, "confidence", None)
        model_value = getattr(confidence, "model", None) if confidence else None
        if isinstance(model_value, (int, float)):
            return round(float(model_value), 4)
        # No measured model confidence: blend confluence with data quality.
        quality = {"HIGH": 0.85, "MEDIUM": 0.6, "LOW": 0.35, "UNKNOWN": 0.4}.get(ctx.data_quality.overall, 0.4)
        blended = 0.6 * float(getattr(confluence, "confluence", 0.0) or 0.0) + 0.4 * quality
        if getattr(confluence, "insufficient_evidence", False):
            blended = min(blended, 0.45)
        return round(blended, 4)

    # ------------------------------------------------------------------ #
    @staticmethod
    async def _audit(
        response: CopilotAnalysisResponse,
        ctx: MarketContext,
        factors: dict[str, Factor],
        prediction: Any,
        decision: IntentDecision,
    ) -> None:
        from app.copilot.audit import copilot_audit_store

        record = CopilotAuditRecord(
            prediction_id=_new_id("pred"),
            analysis_id=response.meta.analysis_id,
            symbol=decision.symbol,
            horizon=decision.horizon,
            intent=decision.intent,
            market_context=ctx.model_dump(mode="json"),
            feature_snapshot={key: factor.model_dump(mode="json") for key, factor in factors.items()},
            prediction=prediction.model_dump(mode="json"),
            scenarios=[s.model_dump(mode="json") for s in response.scenarios],
            probabilities=dict(getattr(prediction, "probabilities", {}) or {}),
            levels=response.levels.model_dump(mode="json"),
            confidence=prediction.confidence.model_dump(mode="json"),
            model_version=getattr(prediction, "model_version", PREDICTION_ENGINE_VERSION),
            prompt_version=PROMPT_VERSION,
            copilot_version=COPILOT_VERSION,
        )
        await copilot_audit_store.record_prediction(record)


copilot_orchestrator = CopilotOrchestrator()
