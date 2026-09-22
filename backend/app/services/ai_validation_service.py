"""
DROID Trade Thesis & Setup Invalidation Auditor Service
Audits user-proposed trades against live market structure, option OI walls,
and volatility dynamics to detect traps and score trade validity.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
import structlog

from app.models.ai import (
    AITradeValidationRequest,
    AITradeValidationResponse,
)
from app.services.regime_service import regime_service
from app.services.options_service import options_service
from app.ai.registry import create_provider_for_test

logger = structlog.get_logger()


class AITradeValidationService:
    """Pre-trade audit and risk gatekeeper."""

    async def validate_trade(
        self,
        request: AITradeValidationRequest,
    ) -> AITradeValidationResponse:
        symbol = request.symbol.upper().replace(" 50", "")

        # 1. Fetch live market structure
        regime = await regime_service.classify_market_regime(symbol)
        chain = None
        analytics = None
        try:
            chain = await options_service.get_option_chain_matrix(symbol)
            analytics = chain.analytics
        except Exception:
            pass

        # Calculate basic deterministic R:R
        risk = abs(request.entry_price - request.stop_loss)
        reward = abs(request.target_price - request.entry_price)
        rr_calc = round(reward / risk, 2) if risk > 0 else 0.0

        spot = regime.spot_price
        r1 = regime.key_levels.classic_pivots.r1
        s1 = regime.key_levels.classic_pivots.s1
        poc = regime.key_levels.poc
        # Honesty: IV/PCR defaults are ASSUMPTIONS when chain unavailable.
        _iv_assumed = analytics is None
        atm_iv = analytics.atm_iv if analytics else 14.5
        pcr = analytics.pcr_oi if analytics else 1.0
        if _iv_assumed:
            logger.warning(
                "validation_iv_pcr_assumed_not_measured",
                atm_iv=atm_iv,
                pcr=pcr,
                reason="options-chain-unavailable",
            )

        system_prompt = """You are DROID Trade Thesis Auditor, a rigorous risk-manager and institutional trade validator.
Your goal is to find flaws, hidden option writer walls, fakeouts, and structural invalidations in proposed trades.

RULES:
1. Grounding: Cross-examine the trade's entry, stop loss, and target against:
   - Classic Pivots & Volume Profile POC
   - Directional trend (ADX & Supertrend)
   - Option Open Interest walls (Call Resistance vs Put Support)
2. Score: Assign a 0-100 quality score. High quality (>=75) requires R:R >= 1.5 and alignment with underlying regime.
3. Decision: CONFIRM (score>=75) | WATCH (55-74) | REJECT (<55) | UNCERTAIN (insufficient data).
4. Return ONLY valid JSON:
{
  "decision": "CONFIRM",
  "score": 82,
  "technical_alignment": "Strong: Long setup aligns with 15m Supertrend Bullish and bounce from S1.",
  "derivatives_alignment": "Supportive: Heavy Put OI buildup at 24,800 acts as structural floor.",
  "volatility_regime_check": "VIX at 13.8 is stable, favorable for directional trend continuation.",
  "invalidation_conditions": ["15m candle close below 24,780", "Aggressive Call writing surge at 24,900 strike"],
  "warning_traps": ["Upcoming RBI policy rate announcement in 2 days may induce theta chop"],
  "executive_verdict": "High-probability long setup with clean 1:2.8 R:R and solid options buffer."
}
"""

        user_prompt = f"""PROPOSED TRADE TO AUDIT:
- Symbol: {symbol} (Spot: ₹{spot})
- Direction: {request.direction} | Timeframe: {request.timeframe}
- Proposed Entry: ₹{request.entry_price}
- Proposed Stop Loss: ₹{request.stop_loss} (Risk: {round(risk, 2)} pts)
- Proposed Target: ₹{request.target_price} (Reward: {round(reward, 2)} pts)
- Calculated R:R: 1:{rr_calc}
- Trader Thesis Notes: {request.thesis_notes or 'Standard breakout / pullback continuation'}

LIVE MARKET CONTEXT:
- Regime: {regime.regime_state} (Confidence: {regime.confidence_score}%)
- Supertrend: {regime.indicators.supertrend_direction} (₹{regime.indicators.supertrend_value})
- ADX (14): {regime.indicators.adx_14} | RSI: {regime.indicators.rsi_14}
- Classic Pivots: Pivot ₹{regime.key_levels.classic_pivots.pivot}, R1 ₹{r1}, S1 ₹{s1}
- Volume Profile: POC ₹{poc}, VAH ₹{regime.key_levels.vah}, VAL ₹{regime.key_levels.val}
- ATM IV: {atm_iv}% | PCR (OI): {pcr}
"""

        provider_name = (request.provider or "openrouter").lower()
        try:
            provider = create_provider_for_test(
                provider_name,
                model=request.model,
                openRouterApiKey=request.openrouter_api_key,
                geminiApiKey=request.gemini_api_key,
            )

            if provider_name == "openrouter":
                import httpx
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {"Authorization": f"Bearer {provider.api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": provider.model,
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    "temperature": 0.2,
                }
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    content = resp.json()["choices"][0]["message"]["content"]
            elif provider_name == "gemini":
                import httpx
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{provider.model}:generateContent?key={provider.api_key}"
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
                    "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2},
                }
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(url, json=payload)
                    content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            else:
                raise ValueError(f"Provider {provider_name} not supported")

            c = content.strip()
            if c.startswith("```"):
                parts = c.split("```")
                if len(parts) >= 2:
                    c = parts[1]
                    if c.lstrip().startswith("json"):
                        c = c.lstrip()[4:]
                    c = c.strip()
                else:
                    c = c.strip("`").strip()

            parsed = json.loads(c)

            return AITradeValidationResponse(
                symbol=symbol,
                decision=parsed.get("decision", "WATCH"),
                score=int(parsed.get("score", 70)),
                risk_reward_calculated=rr_calc,
                technical_alignment=parsed.get("technical_alignment", "Aligned with trend structure."),
                derivatives_alignment=parsed.get("derivatives_alignment", "Options open interest supportive."),
                volatility_regime_check=parsed.get("volatility_regime_check", "IV in normal range."),
                invalidation_conditions=parsed.get("invalidation_conditions", [f"Breach of stop loss at ₹{request.stop_loss}"]),
                warning_traps=parsed.get("warning_traps", []),
                executive_verdict=parsed.get("executive_verdict", "Trade setup evaluated."),
                timestamp=datetime.now(timezone.utc),
                provider_used=f"{provider_name}:{getattr(provider, 'model', '')}",
            )

        except Exception as e:
            logger.error("trade_validation_failed", error=str(e))
            # Deterministic fallback: LABELED degraded + non-actionable.
            # Never auto-CONFIRM on LLM failure: WATCH/UNCERTAIN only, requires
            # explicit user confirmation. Silent CONFIRM would be actionable.
            return AITradeValidationResponse(
                symbol=symbol,
                decision="WATCH",
                score=50,
                risk_reward_calculated=rr_calc,
                technical_alignment=f"[DEGRADED FALLBACK — LLM unavailable, non-actionable] R:R of 1:{rr_calc} evaluated against Spot ₹{spot}. IV assumed {atm_iv} (available={not _iv_assumed}).",
                derivatives_alignment="Options data verification unavailable — fallback rules only (DEGRADED).",
                volatility_regime_check="Volatility check unavailable — LLM failed (DEGRADED).",
                invalidation_conditions=[f"Stop loss trigger at ₹{request.stop_loss}"],
                warning_traps=[
                    "DEGRADED deterministic fallback — requires explicit user confirmation before any action.",
                    "Ensure position sizing adheres to maximum 1% portfolio risk.",
                ],
                executive_verdict=f"Deterministic audit (DEGRADED, non-actionable): R:R 1:{rr_calc}. LLM failed — user must confirm.",
                timestamp=datetime.now(timezone.utc),
                provider_used="deterministic_fallback-degraded-nonactionable",
            )


ai_validation_service = AITradeValidationService()
