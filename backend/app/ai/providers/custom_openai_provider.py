"""
Direct Provider: Custom OpenAI-Compatible — §11

Supports any OpenAI-compatible endpoint (e.g., Together, Anyscale, local vLLM, etc.)
Requires base_url. API key is optional (local servers usually have none).
"""
from app.ai.providers.openai_compatible import OpenAICompatibleProvider


class CustomOpenAICompatibleProvider(OpenAICompatibleProvider):
    _provider_name = "custom_openai"
    provider_label = "Custom"
    api_key_setting = "custom_openai_api_key"
    model_setting = "custom_openai_model"
    base_url_setting = "custom_openai_base_url"
    default_model = "custom-model"
    default_base_url = ""
    require_api_key = False
    require_base_url = True
    json_prompt_suffix = "\n\nReturn ONLY valid JSON object."

    async def test_connection(self) -> dict:
        result = await super().test_connection()
        if result.get("success"):
            result["base_url"] = self.base_url
        return result
