import json
import httpx
from datetime import datetime, timezone
from typing import Any

from app.ai.base import BaseLLMProvider
from app.models.ai import AIInsightResponse
from app.ai.capability_registry import should_use_structured_outputs, validate_no_unsupported_params
import structlog

logger = structlog.get_logger()

class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter Gateway – Claude, DeepSeek, GPT-4o via unified API. No mock fallback."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = (api_key or "").strip()
        self.model = (model or "anthropic/claude-3.7-sonnet").strip()

    @property
    def provider_name(self) -> str:
        return "openrouter"

    async def list_models(self) -> list[dict[str, Any]]:
        from app.services.openrouter_catalog import get_model_catalog
        catalog = await get_model_catalog()
        return catalog.get("models", [])

    async def get_model_info(self, model_id: str) -> dict[str, Any]:
        from app.services.openrouter_catalog import validate_model_or_raise
        try:
            return await validate_model_or_raise(model_id)
        except Exception:
            from app.ai.capability_registry import get_model_capabilities
            return get_model_capabilities(model_id)

    async def test_connection(self) -> dict[str, Any]:
        if not self.api_key:
            return {"success": False, "provider": "openrouter", "error": "API key missing"}
        if not self.api_key.startswith("sk-or-"):
            return {"success": False, "provider": "openrouter", "error": "API key must start with sk-or-"}
        try:
            # Lightweight catalog fetch proves connectivity
            from app.services.openrouter_catalog import get_model_catalog
            catalog = await get_model_catalog()
            return {"success": True, "provider": "openrouter", "model": self.model, "free_count": catalog.get("free_count", 0)}
        except Exception as e:
            return {"success": False, "provider": "openrouter", "error": str(e)[:300]}

    async def analyze(self, market_state: dict, task: str) -> dict:
        from app.ai.prompt_builder import build_system_prompt
        system_prompt = build_system_prompt()
        user_prompt = f"Task: {task}\nMarketState: {json.dumps(market_state, default=str)}"
        insight = await self.generate_analysis(market_state.get("symbol", "NIFTY"), system_prompt, user_prompt)
        return insight.model_dump(mode="json")

    async def generate_analysis(self, symbol: str, system_prompt: str, user_prompt: str) -> AIInsightResponse:
        if not self.api_key:
            raise ValueError("OpenRouter API key is missing. Go to Settings -> AI Engine -> OpenRouter and add your sk-or-v1-... key (from https://openrouter.ai/keys). No .env hardcode required - key is stored via Settings and sent per-request.")
        if not self.api_key.startswith("sk-or-"):
            raise ValueError(f"OpenRouter API key looks invalid (must start with 'sk-or-'). Got: {self.api_key[:12]}... Check Settings -> AI Engine.")

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://fo-droid.web.app",
            "X-Title": "DROID F&O Analysis",
        }
        # Capability-aware protocol per §17-18: Ling 3.0 Flash Fin must NOT receive response_format
        # Otherwise use native structured outputs if supported; else prompted JSON + local validation
        use_structured = should_use_structured_outputs(self.model)
        prompted_suffix = "\n\nReturn ONLY one valid JSON object. Do not use markdown. Do not include explanations outside the JSON. Do not include code fences."
        base_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt + "\n\nRESPONSE RULE: Output ONLY valid JSON object with keys: market_bias, confidence, executive_summary, options_interpretation, futures_flow_analysis, regime_and_levels, recommended_strategy_framework, risk_management_notes, disclaimer. No markdown, no extra text." + ("" if use_structured else prompted_suffix)},
                {"role": "user", "content": user_prompt + ("" if use_structured else prompted_suffix)},
            ],
            "temperature": 0.2,
        }
        if use_structured:
            payload_with_json = {**base_payload, "response_format": {"type": "json_object"}}
            # Ensure we don't send unsupported params when capability says no
            payload_with_json = validate_no_unsupported_params(self.model, payload_with_json)
        else:
            payload_with_json = base_payload  # never send response_format for Ling etc.

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Single attempt based on capability; fallback only if provider still rejects (defensive)
                resp = await client.post(url, json=payload_with_json, headers=headers)
                if use_structured and resp.status_code == 400 and "structured-outputs" in resp.text:
                    logger.warning("openrouter_structured_not_supported_fallback", model=self.model, error=resp.text[:300])
                    resp = await client.post(url, json=base_payload, headers=headers)
                if not use_structured and resp.status_code == 400 and "response_format" in resp.text:
                    # Already not sending, but log
                    logger.warning("openrouter_unexpected_structured_error", model=self.model, error=resp.text[:300])
                if resp.status_code == 401:
                    raise ValueError("OpenRouter: 401 Unauthorized – API key invalid or expired. Check AI Engine settings.")
                if resp.status_code == 402:
                    raise ValueError("OpenRouter: 402 Payment Required – insufficient credits.")
                if resp.status_code == 429:
                    raise ValueError("OpenRouter: 429 Rate Limited – too many requests. Try again in 30s.")
                if resp.status_code != 200:
                    raise ValueError(f"OpenRouter: {resp.status_code} – {resp.text[:600]}")
                data = resp.json()
                try:
                    content = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as e:
                    raise ValueError(f"OpenRouter returned unexpected shape: {json.dumps(data)[:400]}")
                # content may be JSON string
                if isinstance(content, str):
                    # Strip markdown fences if present
                    c = content.strip()
                    if c.startswith("```"):
                        # Remove ```json ... ```
                        parts = c.split("```")
                        # parts[1] may be 'json\n{...}' or just json
                        if len(parts) >= 2:
                            c = parts[1]
                            if c.lstrip().startswith("json"):
                                c = c.lstrip()[4:]
                            c = c.strip()
                        else:
                            c = c.strip("`").strip()
                    try:
                        parsed = json.loads(c)
                    except json.JSONDecodeError as je:
                        raise ValueError(f"OpenRouter returned non-JSON content: {c[:400]} (json error: {je})")
                else:
                    parsed = content
                # Normalize + sanitize before strict validation (free models often return verbose biases / 0-1 confidence)
                # --- market_bias normalization ---
                raw_bias = str(parsed.get("market_bias", "NEUTRAL")).strip()
                bias_upper = raw_bias.upper()
                # Direct match
                if bias_upper in ("BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"):
                    parsed["market_bias"] = bias_upper
                else:
                    # Fuzzy: map verbose like "Cautiously Bullish with Volatility Premium Edge" -> BULLISH
                    if "BULL" in bias_upper:
                        parsed["market_bias"] = "BULLISH"
                    elif "BEAR" in bias_upper:
                        parsed["market_bias"] = "BEARISH"
                    elif "VOLATILE" in bias_upper or "VOLATILITY" in bias_upper:
                        parsed["market_bias"] = "VOLATILE"
                    elif "NEUTRAL" in bias_upper or "SIDEWAYS" in bias_upper or "RANGE" in bias_upper:
                        parsed["market_bias"] = "NEUTRAL"
                    else:
                        # Default to NEUTRAL but keep original for logging
                        logger.warning("openrouter_bias_normalized", raw_bias=raw_bias, normalized="NEUTRAL", model=self.model)
                        parsed["market_bias"] = "NEUTRAL"
                # --- confidence normalization (handle "0.68" vs 68) ---
                try:
                    raw_conf = parsed.get("confidence", 80.0)
                    conf_val = float(str(raw_conf).strip().replace("%",""))
                    # If model returned 0-1 fraction, scale to 0-100
                    if 0 <= conf_val <= 1.0:
                        # Heuristic: 0.68 -> 68, but 1.0 -> 100, 0.5 -> 50; keep 0.0 as 0
                        # Only scale if original was decimal <1 and not already 0-1 edge like 0.9 intended as 0.9% (unlikely)
                        # We treat any 0<val<=1 as fraction
                        if conf_val > 0 and conf_val <= 1.0:
                            conf_val = conf_val * 100
                    parsed["confidence"] = conf_val
                except Exception:
                    raise ValueError(f"OpenRouter confidence must be numeric, got '{parsed.get('confidence')}'. Raw: {json.dumps(parsed)[:300]}")
                if not (0 <= parsed["confidence"] <= 100):
                    raise ValueError(f"OpenRouter confidence out of range 0-100: {parsed['confidence']}. Raw: {json.dumps(parsed)[:300]}")
                conf_val = float(parsed["confidence"])

                # Strict JSON schema validation – fail honestly if missing required fields (after normalization)
                required_fields = ["market_bias", "confidence", "executive_summary", "options_interpretation", "futures_flow_analysis", "regime_and_levels", "recommended_strategy_framework", "risk_management_notes"]
                missing = [f for f in required_fields if f not in parsed or parsed.get(f) in (None, "")]
                if missing:
                    raise ValueError(f"OpenRouter response missing required fields: {missing}. Got keys: {list(parsed.keys())}. Raw: {json.dumps(parsed)[:400]}")
                # Final literal check (should always pass after normalization)
                if parsed.get("market_bias") not in ("BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"):
                    raise ValueError(f"OpenRouter returned invalid market_bias '{parsed.get('market_bias')}'. Expected BULLISH|BEARISH|NEUTRAL|VOLATILE. Raw: {json.dumps(parsed)[:300]}")
                return AIInsightResponse(
                    symbol=symbol,
                    timestamp=datetime.now(timezone.utc),
                    market_bias=parsed.get("market_bias", "NEUTRAL"),
                    confidence=conf_val,
                    executive_summary=parsed.get("executive_summary", ""),
                    options_interpretation=parsed.get("options_interpretation", ""),
                    futures_flow_analysis=parsed.get("futures_flow_analysis", ""),
                    regime_and_levels=parsed.get("regime_and_levels", ""),
                    recommended_strategy_framework=parsed.get("recommended_strategy_framework", ""),
                    risk_management_notes=parsed.get("risk_management_notes", ""),
                    disclaimer=parsed.get("disclaimer", "Quantitative analysis for research only."),
                    provider_used=f"openrouter:{self.model}",
                )
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"OpenRouter request failed: {str(e)[:300]}")
