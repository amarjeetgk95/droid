import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock
from app.models.ai import (
    AIInsightResponse,
    AIOptionsStrategyRecommendation,
    AITradeValidationResponse,
    AIDailyBriefingResponse,
    coerce_to_text,
    coerce_to_string_list,
)
from app.ai.openrouter import OpenRouterProvider


def test_coerce_to_text_primitives():
    assert coerce_to_text(None) == ""
    assert coerce_to_text("") == ""
    assert coerce_to_text("  simple text  ") == "simple text"
    assert coerce_to_text(12345) == "12345"
    assert coerce_to_text(12.34) == "12.34"


def test_coerce_to_text_list():
    input_list = [
        "The compression squeeze indicates tight range.",
        "Limit capital deployment until expansion.",
    ]
    res = coerce_to_text(input_list)
    assert "• The compression squeeze indicates tight range." in res
    assert "• Limit capital deployment until expansion." in res


def test_coerce_to_text_dict():
    input_dict = {
        "regime": "COMPRESSION_SQUEEZE",
        "breakout_notes": "Wait until breakout resolves.",
    }
    res = coerce_to_text(input_dict)
    assert "Regime: COMPRESSION_SQUEEZE" in res
    assert "Breakout Notes: Wait until breakout resolves." in res


def test_ai_insight_response_ling_flash_fin_payload():
    """
    Test exact scenario reported with inclusionai/ling-3.0-flash-fin:free
    where regime_and_levels and recommended_strategy_framework were dicts,
    and risk_management_notes was a list.
    """
    raw_payload = {
        "symbol": "NIFTY",
        "market_bias": "BULLISH",
        "confidence": 85.0,
        "executive_summary": "NIFTY is consolidating near upper resistance.",
        "simple_takeaway": "NIFTY is holding strong. Watch 24,800 as support.",
        "options_interpretation": "Heavy put writing at 24,700.",
        "futures_flow_analysis": "Long buildup observed in current contract.",
        "regime_and_levels": {
            "regime": "COMPRESSION_SQUEEZE",
            "support": 24700,
            "resistance": 24900,
            "notes": "Watch until the breakout resolves.",
        },
        "recommended_strategy_framework": {
            "primary_playbook": "Given low vol, use Bull Call Spreads.",
            "alternative": "Sell OTM strikes near expiry.",
        },
        "risk_management_notes": [
            "The compression squeeze warrants tight stops.",
            "Maintain minimal capital deployment.",
        ],
        "disclaimer": "Quantitative analysis for research only.",
        "provider_used": "openrouter:inclusionai/ling-3.0-flash-fin:free",
    }

    insight = AIInsightResponse(**raw_payload)
    assert isinstance(insight.regime_and_levels, str)
    assert isinstance(insight.recommended_strategy_framework, str)
    assert isinstance(insight.risk_management_notes, str)

    assert "Regime: COMPRESSION_SQUEEZE" in insight.regime_and_levels
    assert "Support: 24700" in insight.regime_and_levels
    assert "Primary Playbook: Given low vol" in insight.recommended_strategy_framework
    assert "• The compression squeeze warrants tight stops." in insight.risk_management_notes
    assert "• Maintain minimal capital deployment." in insight.risk_management_notes


def test_confidence_coercion_and_clamping():
    # Percentage string
    assert AIInsightResponse(confidence="85%").confidence == 85.0
    # Probability (0 < p <= 1) -> percentage
    assert AIInsightResponse(confidence=0.82).confidence == 82.0
    # String probability
    assert AIInsightResponse(confidence="0.75").confidence == 75.0
    # Direct float
    assert AIInsightResponse(confidence=90.0).confidence == 90.0
    # Clamping
    assert AIInsightResponse(confidence=150.0).confidence == 100.0
    assert AIInsightResponse(confidence=-10.0).confidence == 0.0
    # Fallback for garbage
    assert AIInsightResponse(confidence="unknown").confidence == 75.0
    assert AIInsightResponse(confidence=None).confidence == 75.0


def test_market_bias_normalization():
    assert AIInsightResponse(market_bias="bullish").market_bias == "BULLISH"
    assert AIInsightResponse(market_bias="BUY").market_bias == "BULLISH"
    assert AIInsightResponse(market_bias="STRONG_BUY").market_bias == "BULLISH"
    assert AIInsightResponse(market_bias="bearish").market_bias == "BEARISH"
    assert AIInsightResponse(market_bias="SELL").market_bias == "BEARISH"
    assert AIInsightResponse(market_bias="VOLATILITY").market_bias == "VOLATILE"
    assert AIInsightResponse(market_bias="choppy").market_bias == "VOLATILE"
    assert AIInsightResponse(market_bias="sideways").market_bias == "NEUTRAL"
    assert AIInsightResponse(market_bias="").market_bias == "NEUTRAL"


@pytest.mark.asyncio
async def test_openrouter_provider_generate_with_ling_payload():
    provider = OpenRouterProvider(
        api_key="sk-or-test-dummy-key-12345",
        model="inclusionai/ling-3.0-flash-fin:free",
    )

    fake_response_content = {
        "market_bias": "NEUTRAL",
        "confidence": "78%",
        "executive_summary": "Market is in range compression.",
        "simple_takeaway": "NIFTY is quiet. Watch 24,700 support.",
        "options_interpretation": "Balanced CE and PE open interest.",
        "futures_flow_analysis": "Neutral rollover pace.",
        "regime_and_levels": {
            "regime": "COMPRESSION_SQUEEZE",
            "notes": "Wait until the breakout resolves.",
        },
        "recommended_strategy_framework": {
            "primary_playbook": "Iron condor or wait for expansion.",
        },
        "risk_management_notes": [
            "Keep positions light.",
            "Exit on break below 24,650.",
        ],
        "disclaimer": "Quantitative analysis for research only.",
    }

    import json
    from unittest.mock import MagicMock
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(fake_response_content),
                }
            }
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_post_resp
        insight = await provider.generate_analysis("NIFTY", "system prompt", "user prompt")

        assert insight.symbol == "NIFTY"
        assert insight.confidence == 78.0
        assert insight.market_bias == "NEUTRAL"
        assert "Regime: COMPRESSION_SQUEEZE" in insight.regime_and_levels
        assert "Primary Playbook: Iron condor" in insight.recommended_strategy_framework
        assert "• Keep positions light." in insight.risk_management_notes
