"""
Direct Provider: NVIDIA — §11
NVIDIA NIM / AI Foundation Models (OpenAI-compatible)
"""
from app.ai.providers.openai_compatible import OpenAICompatibleProvider


class NvidiaProvider(OpenAICompatibleProvider):
    _provider_name = "nvidia"
    provider_label = "NVIDIA"
    api_key_setting = "nvidia_api_key"
    model_setting = "nvidia_model"
    base_url_setting = "nvidia_base_url"
    default_model = "meta/llama-3.1-70b-instruct"
    default_base_url = "https://integrate.api.nvidia.com/v1"
    json_prompt_suffix = "\n\nReturn ONLY valid JSON object. No markdown."
