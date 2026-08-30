import pytest
from app.services.regime_service import RegimeService
from app.services.futures_service import FuturesService
from app.ai.prompt_builder import build_system_prompt, build_market_context_prompt


class TestPromptBuilder:
    def test_system_prompt_rules(self):
        sys_prompt = build_system_prompt()
        assert "DROID AI Market Analyst" in sys_prompt
        assert "NEVER predict the future" in sys_prompt
        assert "JSON" in sys_prompt

    @pytest.mark.asyncio
    async def test_market_context_prompt_grounding(self):
        regime_srv = RegimeService()
        futures_srv = FuturesService()

        regime = await regime_srv.classify_market_regime("NIFTY")
        futures = await futures_srv.get_futures_overview("NIFTY")

        prompt = build_market_context_prompt("NIFTY", regime, futures)

        assert "MARKET STATE DOSSIER: NIFTY" in prompt
        assert f"Spot LTP: ₹{regime.spot_price}" in prompt
        assert f"Market Regime: {regime.regime_state}" in prompt
        assert f"RSI (14): {regime.indicators.rsi_14}" in prompt
        assert f"Volume Profile POC: ₹{regime.key_levels.poc}" in prompt
        assert f"Term Structure Curve: {futures.term_structure.curve_state}" in prompt
        assert f"India VIX: {regime.vix_regime.vix_value}" in prompt
