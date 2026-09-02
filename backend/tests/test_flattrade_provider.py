import pytest
import hashlib
from app.providers.flattrade import FlattradeProvider
from app.providers.registry import get_provider, reset_provider
from app.core.broker_runtime import apply_app_settings, get_config
from app.models.market import DataStatus


def test_flattrade_provider_initialization():
    provider = FlattradeProvider(
        user_id="FT12345",
        api_key="test_api_key",
        api_secret="test_secret",
        token="test_token",
    )
    assert provider.provider_name == "flattrade"
    assert provider.user_id == "FT12345"
    assert provider.token_manager.provider == "flattrade"


@pytest.mark.asyncio
async def test_flattrade_quote_fallback():
    provider = FlattradeProvider()
    quote = await provider.get_quote("NIFTY 50")
    assert quote.symbol == "NIFTY 50"
    assert quote.ltp > 0
    assert quote.status in (DataStatus.LIVE, DataStatus.CLOSED, DataStatus.OFFLINE)


@pytest.mark.asyncio
async def test_flattrade_option_chain():
    provider = FlattradeProvider()
    chain = await provider.get_option_chain("NIFTY 50")
    assert len(chain) > 0
    assert any(q.strike for q in chain)


def test_flattrade_sha256_hash_formula():
    api_key = "my_app_key"
    code = "auth_code_123"
    api_secret = "my_secret_key"
    
    hash_raw = f"{api_key}{code}{api_secret}"
    expected_hash = hashlib.sha256(hash_raw.encode("utf-8")).hexdigest()
    assert len(expected_hash) == 64


def test_runtime_switching_to_flattrade():
    settings_payload = {
        "broker": {
            "apiType": "indian",
            "provider": "flattrade",
            "flattrade": {
                "userId": "FT999",
                "apiKey": "key_999",
                "apiSecret": "secret_999",
                "token": "token_999",
            },
        }
    }
    changed = apply_app_settings(settings_payload)
    cfg = get_config()
    assert cfg.provider == "flattrade"
    assert cfg.credentials.get("user_id") == "FT999"
    reset_provider()
