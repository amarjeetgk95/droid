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
                # Ollama may wrap JSON in markdown
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]
                    response_text = response_text.strip()
                parsed_json = json.loads(response_text)
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
