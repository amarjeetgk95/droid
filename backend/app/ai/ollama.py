import json
import httpx
from datetime import datetime, timezone
from app.ai.base import BaseLLMProvider
from app.models.ai import AIInsightResponse
import structlog

logger = structlog.get_logger()


class OllamaProvider(BaseLLMProvider):
    """Local Ollama – strict mode, no mock fallback. Fails fast with actionable errors."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "deepseek-r1:8b",
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        if not self.base_url:
            self.base_url = "http://localhost:11434"
        self.model = (model or "deepseek-r1:8b").strip()

    @property
    def provider_name(self) -> str:
        return "ollama"

    async def list_models(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self.base_url}/api/tags")
            if r.status_code != 200:
                raise ValueError(f"Ollama {r.status_code}: {r.text[:200]}")
            data = r.json()
            return data.get("models", [])

    async def get_model_info(self, model_id: str) -> dict:
        models = await self.list_models()
        for m in models:
            if m.get("name") == model_id or model_id in m.get("name", ""):
                return m
        return {"name": model_id, "model": model_id}

    async def test_connection(self) -> dict:
        try:
            models = await self.list_models()
            has_model = any(self.model in m.get("name", "") or m.get("name", "") in self.model for m in models)
            return {"success": True, "provider": "ollama", "model": self.model, "installed_models": [m.get("name") for m in models[:5]], "has_model": has_model, "base_url": self.base_url}
        except Exception as e:
            return {"success": False, "provider": "ollama", "error": str(e)[:400], "base_url": self.base_url}

    async def analyze(self, market_state: dict, task: str) -> dict:
        from app.ai.prompt_builder import build_system_prompt
        system_prompt = build_system_prompt()
        user_prompt = f"Task: {task}\nMarketState: {market_state}"
        import json as _j
        insight = await self.generate_analysis(market_state.get("symbol", "NIFTY"), system_prompt, _j.dumps(market_state, default=str))
        return insight.model_dump(mode="json")

    async def _check_connectivity(self):
        # 1. Check if Ollama server is reachable (works for remote URLs, but for localhost from server it will fail – caller must handle)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # /api/tags is lightweight and proves server is up
                r = await client.get(f"{self.base_url}/api/tags")
                if r.status_code != 200:
                    raise ValueError(f"Ollama server at {self.base_url} returned {r.status_code}: {r.text[:200]}")
        except httpx.ConnectError as e:
            raise ValueError(
                f"Ollama not reachable at {self.base_url}. Is Ollama installed and running? "
                f"Install from https://ollama.com, then run `ollama serve` and `ollama pull {self.model}`. "
                f"Detail: {str(e)[:200]}"
            )
        except httpx.TimeoutException:
            raise ValueError(f"Ollama at {self.base_url} timed out (5s). Is the server overloaded or firewalled?")
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Ollama connectivity check failed at {self.base_url}: {str(e)[:300]}")

    async def generate_analysis(
        self,
        symbol: str,
        system_prompt: str,
        user_prompt: str,
    ) -> AIInsightResponse:
        # Strict – no mock fallback
        await self._check_connectivity()

        # Verify model is installed (tags contains model name)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                if r.status_code == 200:
                    tags = r.json()
                    models = [m.get("name", "") for m in tags.get("models", [])]
                    # allow partial match (deepseek-r1:8b matches deepseek-r1:8b, deepseek-r1:latest)
                    if models and not any(self.model in m or m in self.model for m in models):
                        raise ValueError(
                            f"Ollama model '{self.model}' not found on server. Available: {', '.join(models[:5]) or 'none'}. "
                            f"Run `ollama pull {self.model}`."
                        )
        except ValueError:
            raise
        except Exception as e:
            logger.warning("ollama_tags_check_failed", error=str(e))

        # Real generate call
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                prompt_full = f"{system_prompt}\n\nUser Request: {user_prompt}\n\nReturn JSON ONLY matching the required schema: {{market_bias, confidence, executive_summary, options_interpretation, futures_flow_analysis, regime_and_levels, recommended_strategy_framework, risk_management_notes}}"
                payload = {
                    "model": self.model,
                    "prompt": prompt_full,
                    "stream": False,
                    "format": "json",
                }
                res = await client.post(f"{self.base_url}/api/generate", json=payload)
                if res.status_code == 404:
                    raise ValueError(f"Ollama: model '{self.model}' not found (404). Run `ollama pull {self.model}`.")
                if res.status_code != 200:
                    raise ValueError(f"Ollama {res.status_code}: {res.text[:400]}")
                data = res.json()
                response_text = data.get("response", "").strip()
                if not response_text:
                    raise ValueError("Ollama returned empty response.")
                try:
                    parsed_json = json.loads(response_text)
                except json.JSONDecodeError:
                    start_idx = response_text.find("{")
                    end_idx = response_text.rfind("}")
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        try:
                            parsed_json = json.loads(response_text[start_idx : end_idx + 1])
                        except json.JSONDecodeError as je:
                            raise ValueError(f"Ollama returned non-JSON content: {response_text[:300]} (json error: {je})")
                    else:
                        raise ValueError(f"Ollama returned non-JSON content: {response_text[:300]}")

                if not isinstance(parsed_json, dict):
                    raise ValueError(f"Ollama response root is not a JSON object: {type(parsed_json)}")
                # Validate required fields
                required = ["market_bias", "confidence", "executive_summary"]
                missing = [f for f in required if f not in parsed_json]
                if missing:
                    raise ValueError(f"Ollama response missing fields: {missing}. Raw: {response_text[:300]}")
                return AIInsightResponse(
                    symbol=symbol,
                    timestamp=datetime.now(timezone.utc),
                    provider_used=f"ollama:{self.model}",
                    **parsed_json,
                )
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Ollama generate failed at {self.base_url}: {str(e)[:400]}")
