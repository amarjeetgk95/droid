"""
Direct Provider: Novita AI — §11
OpenAI-compatible endpoint with Novita specifics.
"""
from app.ai.providers.openai_compatible import OpenAICompatibleProvider


class NovitaProvider(OpenAICompatibleProvider):
    _provider_name = "novita"
    provider_label = "Novita"
    api_key_setting = "novita_api_key"
    model_setting = "novita_model"
    base_url_setting = "novita_base_url"
    default_model = "meta-llama/llama-3.3-70b-instruct"
    default_base_url = "https://api.novita.ai/v3/openai"
    # Novita generally supports OpenAI-compatible; use prompted JSON to be safe.
    use_structured_outputs = False
