import json
import httpx
from datetime import datetime, timezone
from app.ai.base import BaseLLMProvider
from app.models.ai import AIInsightResponse
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
        # Some free models (e.g. Novita-routed ling-3.0-flash-fin:free) do NOT support response_format
        # We try with json_object first, then fallback to plain prompt if provider returns INVALID_REQUEST_BODY structured-outputs
        base_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt + "\n\nRESPONSE RULE: Output ONLY valid JSON object with keys: market_bias, confidence, executive_summary, options_interpretation, futures_flow_analysis, regime_and_levels, recommended_strategy_framework, risk_management_notes, disclaimer. No markdown, no extra text."},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        payload_with_json = {**base_payload, "response_format": {"type": "json_object"}}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Attempt 1: with structured-outputs
                resp = await client.post(url, json=payload_with_json, headers=headers)
                # Auto-fallback if model doesn't support structured-outputs (common on free/Novita models)
                if resp.status_code == 400 and "structured-outputs" in resp.text:
                    logger.warning("openrouter_structured_not_supported_fallback", model=self.model, error=resp.text[:300])
                    resp = await client.post(url, json=base_payload, headers=headers)
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
                # Strict JSON schema validation – fail honestly if missing required fields
                required_fields = ["market_bias", "confidence", "executive_summary", "options_interpretation", "futures_flow_analysis", "regime_and_levels", "recommended_strategy_framework", "risk_management_notes"]
                missing = [f for f in required_fields if f not in parsed or parsed.get(f) in (None, "")]
                if missing:
                    raise ValueError(f"OpenRouter response missing required fields: {missing}. Got keys: {list(parsed.keys())}. Raw: {json.dumps(parsed)[:400]}")
                # Validate market_bias literal
                if parsed.get("market_bias") not in ("BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"):
                    raise ValueError(f"OpenRouter returned invalid market_bias '{parsed.get('market_bias')}'. Expected BULLISH|BEARISH|NEUTRAL|VOLATILE. Raw: {json.dumps(parsed)[:300]}")
                try:
                    conf_val = float(parsed.get("confidence", 80.0))
                except Exception:
                    raise ValueError(f"OpenRouter confidence must be numeric, got '{parsed.get('confidence')}'. Raw: {json.dumps(parsed)[:300]}")
                if not (0 <= conf_val <= 100):
                    raise ValueError(f"OpenRouter confidence out of range 0-100: {conf_val}. Raw: {json.dumps(parsed)[:300]}")
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
