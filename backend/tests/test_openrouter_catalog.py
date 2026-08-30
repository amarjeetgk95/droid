import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.openrouter_catalog import (
    is_free_model,
    categorize_model,
    compute_trading_rank,
    normalize_model,
    select_default_trading_model,
    get_model_catalog,
    validate_model_or_raise,
    clear_cache,
    fetch_openrouter_catalog_raw,
)


# Sample raw models mimicking OpenRouter API
SAMPLE_RAW_FIN_FREE = {
    "id": "inclusionai/ling-3.0-flash-fin:free",
    "name": "Ling 3.0 Flash Fin",
    "description": "Finance-specialized model for trading and investment analysis",
    "pricing": {"prompt": "0", "completion": "0"},
    "context_length": 262144,
    "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
    "supported_parameters": ["tools"],
    "top_provider": {"context_length": 262144},
}

SAMPLE_RAW_REASON_FREE = {
    "id": "deepseek/deepseek-r1:free",
    "name": "DeepSeek R1",
    "description": "Chain-of-thought reasoning model",
    "pricing": {"prompt": "0", "completion": "0"},
    "context_length": 131072,
    "architecture": {"input_modalities": ["text"]},
    "supported_parameters": ["tools", "reasoning"],
}

SAMPLE_RAW_PAID = {
    "id": "anthropic/claude-3.7-sonnet",
    "name": "Claude 3.7 Sonnet",
    "description": "Top tier reasoning",
    "pricing": {"prompt": "0.003", "completion": "0.015"},
    "context_length": 200000,
    "architecture": {"input_modalities": ["text"]},
}

SAMPLE_RAW_GENERAL_FREE = {
    "id": "meta-llama/llama-3.3-70b-instruct:free",
    "name": "Llama 3.3 70B",
    "description": "General purpose instruct",
    "pricing": {"prompt": "0", "completion": "0"},
    "context_length": 131072,
    "architecture": {"input_modalities": ["text"]},
}

SAMPLE_RAW_NONZERO_PROMPT = {
    "id": "openai/gpt-4o",
    "name": "GPT-4o",
    "pricing": {"prompt": "0.0025", "completion": "0"},
    "context_length": 128000,
    "architecture": {"input_modalities": ["text", "image"]},
    "description": "Flagship omni",
}

SAMPLE_RAW_NONZERO_COMPLETION = {
    "id": "qwen/qwen-2.5-72b-instruct:free",
    "name": "Qwen 2.5 72B",
    "pricing": {"prompt": "0", "completion": "0.001"},
    "context_length": 32768,
    "architecture": {"input_modalities": ["text"]},
    "description": "Math & quantitative",
}

SAMPLE_RAW_FREE_WITH_SUFFIX_BUT_PAID = {
    "id": "some/model:free",
    "name": "Some Model Free",
    "description": "Looks free but actually paid",
    "pricing": {"prompt": "0.001", "completion": "0.002"},
    "context_length": 8192,
}

SAMPLE_RAW_INPUT_OUTPUT_VARIANT = {
    "id": "test/model-input-output",
    "name": "Test I/O",
    "pricing": {"input": "0", "output": "0"},
    "context_length": 8192,
    "architecture": {},
}


class TestFreeModelDetection:
    def test_zero_both_is_free(self):
        assert is_free_model(SAMPLE_RAW_FIN_FREE) is True
        assert is_free_model(SAMPLE_RAW_REASON_FREE) is True
        assert is_free_model(SAMPLE_RAW_GENERAL_FREE) is True

    def test_nonzero_input_not_free(self):
        assert is_free_model(SAMPLE_RAW_NONZERO_PROMPT) is False
        assert is_free_model(SAMPLE_RAW_PAID) is False

    def test_nonzero_output_not_free(self):
        assert is_free_model(SAMPLE_RAW_NONZERO_COMPLETION) is False

    def test_free_suffix_only_when_pricing_zero(self):
        # model ends with :free but pricing non-zero -> NOT free
        assert is_free_model(SAMPLE_RAW_FREE_WITH_SUFFIX_BUT_PAID) is False
        # model ends with :free and pricing zero -> free
        assert is_free_model(SAMPLE_RAW_FIN_FREE) is True

    def test_input_output_variant(self):
        assert is_free_model(SAMPLE_RAW_INPUT_OUTPUT_VARIANT) is True

    def test_missing_pricing_not_free(self):
        assert is_free_model({"id": "no-pricing"}) is False
        assert is_free_model({"id": "empty", "pricing": {}}) is False


class TestCategorization:
    def test_finance_specialized(self):
        cat = categorize_model(SAMPLE_RAW_FIN_FREE)
        assert cat == "Finance"

    def test_reasoning(self):
        cat = categorize_model(SAMPLE_RAW_REASON_FREE)
        assert cat == "Reasoning"

    def test_coding(self):
        raw = {"id": "qwen/qwen2.5-coder:free", "name": "Qwen Coder", "description": "coding"}
        assert categorize_model(raw) == "Coding"

    def test_vision_from_architecture(self):
        raw = {"id": "openai/gpt-4o", "name": "GPT-4o", "description": "vision", "architecture": {"input_modalities": ["text", "image"]}}
        assert categorize_model(raw) == "Vision"

    def test_fast(self):
        raw = {"id": "google/gemini-flash", "name": "Flash", "description": "fast model"}
        assert categorize_model(raw) == "Fast"

    def test_unknown_fallback(self):
        raw = {"id": "", "name": "", "description": ""}
        assert categorize_model(raw) == "Unknown"

    def test_general(self):
        raw = {"id": "some/general-model", "name": "General", "description": "general purpose"}
        assert categorize_model(raw) == "General"

    def test_not_all_general_become_finance(self):
        general = {"id": "meta-llama/llama-3.3-70b", "name": "Llama", "description": "general instruct"}
        assert categorize_model(general) != "Finance"


class TestRanking:
    def test_finance_rank_higher_than_general(self):
        fin = normalize_model(SAMPLE_RAW_FIN_FREE)
        gen = normalize_model(SAMPLE_RAW_GENERAL_FREE)
        assert fin["trading_rank"] > gen["trading_rank"]
        assert fin["recommended_for_trading"] is True

    def test_ling_fin_bonus(self):
        m = normalize_model(SAMPLE_RAW_FIN_FREE)
        assert m["trading_rank"] >= 100  # finance base + ling bonus

    def test_reasoning_tool_support_bonus(self):
        m = normalize_model(SAMPLE_RAW_REASON_FREE)
        assert m["trading_rank"] > 80
        assert m["recommended_for_trading"] is True


class TestDefaultModelSelection:
    def test_prefers_finance_free(self):
        fin = normalize_model(SAMPLE_RAW_FIN_FREE)
        reason = normalize_model(SAMPLE_RAW_REASON_FREE)
        gen = normalize_model(SAMPLE_RAW_GENERAL_FREE)
        default = select_default_trading_model([gen, reason, fin])
        assert default["id"] == SAMPLE_RAW_FIN_FREE["id"]

    def test_fallback_to_reasoning_when_no_finance(self):
        reason = normalize_model(SAMPLE_RAW_REASON_FREE)
        gen = normalize_model(SAMPLE_RAW_GENERAL_FREE)
        default = select_default_trading_model([gen, reason])
        assert default["category"] == "Reasoning"

    def test_fallback_to_highest_ranked(self):
        gen1 = normalize_model(SAMPLE_RAW_GENERAL_FREE)
        gen1["trading_rank"] = 50
        gen2 = {**SAMPLE_RAW_GENERAL_FREE, "id": "other/free", "name": "Other"}
        gen2_n = normalize_model(gen2)
        gen2_n["trading_rank"] = 60
        default = select_default_trading_model([gen1, gen2_n])
        assert default["id"] == "other/free"

    def test_no_free_returns_none(self):
        paid = normalize_model(SAMPLE_RAW_PAID)
        assert select_default_trading_model([paid]) is None

    def test_ling_specific_preference(self):
        ling = normalize_model(SAMPLE_RAW_FIN_FREE)
        other_fin = normalize_model({**SAMPLE_RAW_FIN_FREE, "id": "other/finance:free", "name": "Other Fin"})
        # ling should be preferred due to explicit id check
        default = select_default_trading_model([other_fin, ling])
        assert "ling" in default["id"].lower()


class TestCatalogService:
    @pytest.mark.asyncio
    async def test_get_model_catalog_free_only(self):
        await clear_cache()
        mock_raw = [SAMPLE_RAW_FIN_FREE, SAMPLE_RAW_PAID, SAMPLE_RAW_REASON_FREE]
        with patch("app.services.openrouter_catalog.fetch_openrouter_catalog_raw", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_raw
            catalog = await get_model_catalog(free_only=True)
            assert catalog["provider"] == "openrouter"
            assert catalog["free_only"] is True
            # Only free models should be returned
            ids = [m["id"] for m in catalog["models"]]
            assert SAMPLE_RAW_FIN_FREE["id"] in ids
            assert SAMPLE_RAW_REASON_FREE["id"] in ids
            assert SAMPLE_RAW_PAID["id"] not in ids
            assert catalog["free_count"] == 2
            assert catalog["total_count"] == 3  # total before filtering? Actually catalog total is before filter? In our impl total_count is len normalized, free_count filtered. Check.

    @pytest.mark.asyncio
    async def test_get_model_catalog_all(self):
        await clear_cache()
        mock_raw = [SAMPLE_RAW_FIN_FREE, SAMPLE_RAW_PAID]
        with patch("app.services.openrouter_catalog.fetch_openrouter_catalog_raw", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_raw
            catalog = await get_model_catalog(free_only=False, pricing_filter="ALL")
            ids = [m["id"] for m in catalog["models"]]
            assert SAMPLE_RAW_PAID["id"] in ids
            assert SAMPLE_RAW_FIN_FREE["id"] in ids

    @pytest.mark.asyncio
    async def test_cache_used(self):
        await clear_cache()
        mock_raw = [SAMPLE_RAW_FIN_FREE]
        with patch("app.services.openrouter_catalog.fetch_openrouter_catalog_raw", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_raw
            await get_model_catalog(free_only=True)
            assert mock_fetch.call_count == 1
            # Second call within cache window should not fetch
            await get_model_catalog(free_only=True)
            assert mock_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_force_refresh(self):
        await clear_cache()
        mock_raw = [SAMPLE_RAW_FIN_FREE]
        with patch("app.services.openrouter_catalog.fetch_openrouter_catalog_raw", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_raw
            await get_model_catalog(free_only=True)
            assert mock_fetch.call_count == 1
            await get_model_catalog(force_refresh=True, free_only=True)
            assert mock_fetch.call_count == 2

    @pytest.mark.asyncio
    async def test_openrouter_failure_uses_cached(self):
        await clear_cache()
        mock_raw = [SAMPLE_RAW_FIN_FREE, SAMPLE_RAW_REASON_FREE]
        with patch("app.services.openrouter_catalog.fetch_openrouter_catalog_raw", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_raw
            catalog1 = await get_model_catalog(free_only=True)
            assert catalog1["using_cached"] is False
            # Now make fetch fail
            mock_fetch.side_effect = ValueError("OpenRouter: 502 – Bad Gateway")
            catalog2 = await get_model_catalog(force_refresh=True, free_only=True)
            # Should return cached with using_cached True
            assert catalog2["using_cached"] is True
            assert len(catalog2["models"]) == 2

    @pytest.mark.asyncio
    async def test_model_removal_choose_another(self):
        # Simulate selected model disappears
        await clear_cache()
        mock_raw_initial = [SAMPLE_RAW_FIN_FREE, SAMPLE_RAW_REASON_FREE]
        mock_raw_after = [SAMPLE_RAW_REASON_FREE]  # fin disappeared
        with patch("app.services.openrouter_catalog.fetch_openrouter_catalog_raw", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_raw_initial
            await get_model_catalog(free_only=True)
            # Expire cache by clearing or forcing refresh so removal is detected
            await clear_cache()
            mock_fetch.return_value = mock_raw_after
            await get_model_catalog(free_only=False, pricing_filter="ALL")
            # Now request validation for disappeared model -> should try refresh and raise
            with pytest.raises(ValueError, match="not found"):
                await validate_model_or_raise(SAMPLE_RAW_FIN_FREE["id"], free_only=True)
            # But default selection should now pick reasoning
            catalog = await get_model_catalog(force_refresh=True, free_only=True)
            default = catalog["default_model"]
            assert default["id"] == SAMPLE_RAW_REASON_FREE["id"]


class TestPaidProtection:
    @pytest.mark.asyncio
    async def test_free_only_rejects_paid(self):
        await clear_cache()
        mock_raw = [SAMPLE_RAW_FIN_FREE, SAMPLE_RAW_PAID]
        with patch("app.services.openrouter_catalog.fetch_openrouter_catalog_raw", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_raw
            await get_model_catalog(free_only=True)
            with pytest.raises(ValueError, match="Paid models are disabled"):
                await validate_model_or_raise(SAMPLE_RAW_PAID["id"], free_only=True)

    @pytest.mark.asyncio
    async def test_allow_paid_allows(self):
        await clear_cache()
        mock_raw = [SAMPLE_RAW_PAID]
        with patch("app.services.openrouter_catalog.fetch_openrouter_catalog_raw", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_raw
            await get_model_catalog(free_only=False)
            # Should allow paid when free_only False
            m = await validate_model_or_raise(SAMPLE_RAW_PAID["id"], free_only=False)
            assert m["id"] == SAMPLE_RAW_PAID["id"]

    @pytest.mark.asyncio
    async def test_auto_resolves(self):
        await clear_cache()
        mock_raw = [SAMPLE_RAW_FIN_FREE, SAMPLE_RAW_REASON_FREE]
        with patch("app.services.openrouter_catalog.fetch_openrouter_catalog_raw", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_raw
            m = await validate_model_or_raise("auto", free_only=True)
            assert m["is_free"] is True
            assert m["id"] in [SAMPLE_RAW_FIN_FREE["id"], SAMPLE_RAW_REASON_FREE["id"]]

    @pytest.mark.asyncio
    async def test_no_eligible_free_message(self):
        await clear_cache()
        mock_raw = [SAMPLE_RAW_PAID]
        with patch("app.services.openrouter_catalog.fetch_openrouter_catalog_raw", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_raw
            await get_model_catalog(free_only=True)
            with pytest.raises(ValueError, match="No eligible free model"):
                await validate_model_or_raise("auto", free_only=True)
