from datetime import datetime, timezone
from app.ai.base import BaseLLMProvider
from app.models.ai import AIInsightResponse, MarketBias


class MockLLMProvider(BaseLLMProvider):
    """Deterministic, grounded Mock LLM provider for quantitative insights."""

    @property
    def provider_name(self) -> str:
        return "mock_ai"

    async def generate_analysis(
        self,
        symbol: str,
        system_prompt: str,
        user_prompt: str,
    ) -> AIInsightResponse:
        """Parse grounded prompt indicators and generate structured report."""
        # Derive bias from prompt tokens
        if "TRENDING_BULLISH" in user_prompt or "Long Buildup" in user_prompt:
            bias: MarketBias = "BULLISH"
            conf = 88.0
            exec_summary = f"{symbol} displays constructive bullish market structure. Positive Basis with Long Buildup in futures confirms institutional accumulation above central pivot levels."
            strat = "Bull Call Spreads, Bull Put Credit Spreads, or trailing long delta futures above nearest support."
        elif "TRENDING_BEARISH" in user_prompt or "Short Buildup" in user_prompt:
            bias = "BEARISH"
            conf = 88.0
            exec_summary = f"{symbol} exhibits heavy institutional distribution. Futures short buildup and downward expansion below Value Area POC imply supply pressure."
            strat = "Bear Put Spreads, Bear Call Credit Spreads, or short delta hedging at resistance boundaries."
        elif "COMPRESSION_SQUEEZE" in user_prompt or "VOLATILE_EXPANSION" in user_prompt:
            bias = "VOLATILE"
            conf = 84.0
            exec_summary = f"{symbol} is in a pronounced volatility transition. Contracted Bollinger Bandwidth implies an explosive breakout is imminent."
            strat = "Long Straddles, Long Strangles, or breakout delta debit strategies with wide stops."
        else:
            bias = "NEUTRAL"
            conf = 80.0
            exec_summary = f"{symbol} is oscillating within a defined horizontal range. Subdued ADX and stable India VIX favor theta decay and rangebound mean reversion."
            strat = "Iron Condors, Iron Butterflies, and Short Strangles with wide wing protection."

        return AIInsightResponse(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            market_bias=bias,
            confidence=conf,
            executive_summary=exec_summary,
            options_interpretation=(
                f"Options market microstructure shows active strike clustering around the Max Pain level. "
                f"PCR levels indicate balanced positioning, with Put writing providing solid support near Value Area Low."
            ),
            futures_flow_analysis=(
                f"Futures term structure reflects consistent cost of carry. "
                f"Cumulative Open Interest positioning shows disciplined institutional rollover pace in line with 3-month historical benchmarks."
            ),
            regime_and_levels=(
                f"Price action is interacting closely with Volume Profile POC and Classic Floor Pivots. "
                f"Key resistance sits at nearest pivot R1, while support is anchored firmly at nearest pivot S1."
            ),
            recommended_strategy_framework=strat,
            risk_management_notes=(
                f"Strict invalidation is advised if spot price decisively breaches key support/resistance boundaries. "
                f"Position size must not exceed 2% of allocated research risk capital."
            ),
            disclaimer=(
                "This AI analysis is strictly for quantitative research, backtesting, and educational purposes. "
                "It does not constitute financial advice, buy/sell recommendations, or performance guarantees."
            ),
            provider_used="mock_ai",
        )
