"""
DROID Options Strategy Architect Service
Synthesizes options chain, IV rank, regime S/R, and user outlook to construct
mathematically sound, defined-risk multi-leg options strategies.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
import structlog

from app.models.ai import (
    AIOptionsStrategyRequest,
    AIOptionsStrategyRecommendation,
    AIOptionLeg,
)
from app.services.regime_service import regime_service
from app.services.options_service import options_service
from app.ai.registry import create_provider_for_test

logger = structlog.get_logger()


class AIOptionsStrategyService:
    """Specialized engine for structuring options strategies."""

    async def recommend_strategy(
        self,
        request: AIOptionsStrategyRequest,
    ) -> AIOptionsStrategyRecommendation:
        symbol = request.symbol.upper().replace(" 50", "")

        # 1. Fetch live quantitative context
        regime = await regime_service.classify_market_regime(symbol)
        chain = None
        analytics = None
        strikes = None
        try:
            chain = await options_service.get_option_chain_matrix(symbol)
            analytics = chain.analytics
            strikes = chain.strikes
        except Exception as e:
            logger.warning("strategy_options_fetch_failed", error=str(e))

        spot = regime.spot_price
        atm_iv = analytics.atm_iv if analytics else 14.5
        pcr = analytics.pcr_oi if analytics else 1.0
        r1 = regime.key_levels.classic_pivots.r1
        s1 = regime.key_levels.classic_pivots.s1
        poc = regime.key_levels.poc

        system_prompt = """You are DROID Options Strategy Architect, an elite derivatives structuring engine specializing in Indian Index F&O (NIFTY / BANKNIFTY).
Your task is to recommend the optimal multi-leg options strategy conforming strictly to the quantitative state (ATM IV, IV Rank, Support/Resistance walls, PCR, and Trend Regime).

RULES:
1. Always choose risk-defined structures (Debit Spreads, Credit Spreads, Iron Condors, Iron Butterflies, Calendars, Ratio Spreads) unless outlook specifically calls for long gamma.
2. Align legs with real market strike steps (e.g. NIFTY strikes are multiples of 50 or 100; BANKNIFTY multiples of 100).
3. Return ONLY a single valid JSON object matching this schema:
{
  "strategy_name": "Bull Put Credit Spread",
  "market_outlook": "Moderately Bullish above 24,800 with high IV contraction edge",
  "legs": [
    {"strike": 24800, "option_type": "PE", "action": "SELL", "estimated_premium": 85.0, "delta": -0.35, "theta": 12.0},
    {"strike": 24600, "option_type": "PE", "action": "BUY", "estimated_premium": 28.0, "delta": -0.15, "theta": -4.0}
  ],
  "max_profit_pts": "57 pts (₹1,425/lot)",
  "max_loss_pts": "143 pts (₹3,575/lot)",
  "risk_reward_ratio": "1:2.5",
  "breakevens": [24743.0],
  "net_debit_credit_pts": 57.0,
  "net_delta": 0.20,
  "net_theta": 8.0,
  "rationale": "Strong put OI concentration at 24,800 + upward trending 50-EMA support makes selling the 24,800 PE high probability.",
  "entry_rules": ["Enter on pullback to 24,850 support", "Ensure ATM IV >= 14%"],
  "exit_rules": ["Take profit at 70% max credit", "Stop loss if underlying breaks below 24,700 with 15m candle close"],
  "risk_management": "Do not carry naked short options into major policy events."
}
"""

        user_prompt = f"""MARKET DOSSIER FOR STRATEGY STRUCTURING:
- Symbol: {symbol}
- Spot LTP: ₹{spot}
- Requested Outlook: {request.outlook}
- User Notes / Intent: {request.custom_query or 'Optimal multi-leg structure based on market regime'}
- Risk Tolerance: {request.max_risk_tolerance}
- Target Expiry DTE: {request.target_dte or 'Nearest Weekly Expiry'}
- Technical Regime: {regime.regime_state} (Confidence: {regime.confidence_score}%)
- ATM IV: {atm_iv}% | PCR (OI): {pcr}
- Classical Pivot Levels: Pivot ₹{regime.key_levels.classic_pivots.pivot}, R1 ₹{r1}, S1 ₹{s1}
- Volume Profile POC: ₹{poc} (VAH: ₹{regime.key_levels.vah}, VAL: ₹{regime.key_levels.val})
"""

        provider_name = (request.provider or "openrouter").lower()
        provider = create_provider_for_test(
            provider_name,
            model=request.model,
            openRouterApiKey=request.openrouter_api_key,
            geminiApiKey=request.gemini_api_key,
        )

        try:
            # We use analyze or direct inference
            market_state = {
                "symbol": symbol,
                "spot": spot,
                "outlook": request.outlook,
                "atm_iv": atm_iv,
                "pcr": pcr,
                "pivots": {"r1": r1, "s1": s1, "poc": poc},
            }
            # For Gemini / OpenRouter
            if hasattr(provider, "generate_analysis"):
                # Use provider chat completions or generate_analysis fallback
                pass

            # Call provider via standard chat or analyze
            if provider_name == "openrouter":
                import httpx
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {provider.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": provider.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.2,
                }
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code != 200:
                        raise ValueError(f"OpenRouter error: {resp.text[:200]}")
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
                    if resp.status_code != 200:
                        raise ValueError(f"Gemini error: {resp.text[:200]}")
                    content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            else:
                raise ValueError(f"Provider {provider_name} not supported for strategy structurer")

            # Clean json
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

            legs = []
            for l in parsed.get("legs", []):
                legs.append(AIOptionLeg(
                    strike=float(l.get("strike", spot)),
                    option_type=l.get("option_type", "CE"),
                    action=l.get("action", "BUY"),
                    expiry=l.get("expiry"),
                    estimated_premium=float(l.get("estimated_premium", 0.0)),
                    delta=float(l.get("delta")) if l.get("delta") is not None else None,
                    theta=float(l.get("theta")) if l.get("theta") is not None else None,
                ))

            return AIOptionsStrategyRecommendation(
                symbol=symbol,
                strategy_name=parsed.get("strategy_name", "Structured Option Spread"),
                market_outlook=parsed.get("market_outlook", request.outlook),
                legs=legs,
                max_profit_pts=str(parsed.get("max_profit_pts", "Limited")),
                max_loss_pts=str(parsed.get("max_loss_pts", "Defined")),
                risk_reward_ratio=str(parsed.get("risk_reward_ratio", "1:2")),
                breakevens=[float(b) for b in parsed.get("breakevens", [])],
                net_debit_credit_pts=float(parsed.get("net_debit_credit_pts", 0.0)),
                net_delta=float(parsed.get("net_delta", 0.0)),
                net_theta=float(parsed.get("net_theta", 0.0)),
                rationale=parsed.get("rationale", ""),
                entry_rules=parsed.get("entry_rules", []),
                exit_rules=parsed.get("exit_rules", []),
                risk_management=parsed.get("risk_management", ""),
                timestamp=datetime.now(timezone.utc),
                provider_used=f"{provider_name}:{getattr(provider, 'model', '')}",
            )

        except Exception as e:
            logger.error("strategy_recommendation_failed", error=str(e))
            # Graceful deterministic fallback
            return AIOptionsStrategyRecommendation(
                symbol=symbol,
                strategy_name="Bull Put Spread (Deterministic Fallback)",
                market_outlook="Bullish Support Defense",
                legs=[
                    AIOptionLeg(strike=round(spot - 100, -1), option_type="PE", action="SELL", estimated_premium=60.0),
                    AIOptionLeg(strike=round(spot - 300, -1), option_type="PE", action="BUY", estimated_premium=20.0),
                ],
                max_profit_pts="40 pts",
                max_loss_pts="160 pts",
                risk_reward_ratio="1:4",
                breakevens=[round(spot - 60, 2)],
                net_debit_credit_pts=40.0,
                rationale=f"Automated fallback strategy based on S1 support ₹{s1} and Spot ₹{spot}.",
                entry_rules=["Enter when price tests S1 support"],
                exit_rules=["Exit on 50% premium decay or break of S2"],
                risk_management="Defined risk spread.",
                timestamp=datetime.now(timezone.utc),
                provider_used="deterministic_fallback",
            )


ai_strategy_service = AIOptionsStrategyService()
