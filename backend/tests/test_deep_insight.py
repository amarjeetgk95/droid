import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.ai.schemas import AISignal, Decision, SetupType, Regime, ValidationStatus, ExecutionDecision

client = TestClient(app)


def test_deep_insight_without_keys():
    """Endpoint responds and reports provider error when no key is configured."""
    resp = client.get("/api/v1/ai/deep-insight/NIFTY")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["symbol"] == "NIFTY"
    assert "market" in data
    assert "setup" in data
    assert "ai_view" in data


def test_deep_insight_forwards_credentials():
    """Verify deep-insight endpoint forwards X-OpenRouter-Key down to deep_insight_service."""
    mock_signal = AISignal(
        symbol="NIFTY",
        decision=Decision.LONG,
        setup_type=SetupType.BREAKOUT,
        regime=Regime.TREND,
        raw_confidence=85,
        calibrated_confidence=82,
        entry=24100.0,
        stop_loss=24050.0,
        target=24200.0,
        ttl_seconds=300,
        reasons=["Strong breakout above resistance"],
        invalidation=["Close below 24050"],
        provider="openrouter",
        model="anthropic/claude-3.7-sonnet",
        validation_result=ValidationStatus.PASS,
    )
    mock_exec = ExecutionDecision(decision="PASS", signal_id=mock_signal.signal_id)

    with patch("app.ai.ai_evaluator.AIEvaluator.evaluate", new_callable=AsyncMock) as mock_eval:
        mock_eval.return_value = (mock_signal, mock_exec)
        resp = client.get(
            "/api/v1/ai/deep-insight/NIFTY",
            headers={"X-OpenRouter-Key": "sk-or-v1-testkey1234567890abcdef"},
        )
        assert resp.status_code == 200
        mock_eval.assert_called_once()
        _, kwargs = mock_eval.call_args
        assert kwargs.get("openrouter_api_key") == "sk-or-v1-testkey1234567890abcdef"
        data = resp.json()["data"]
        assert data["setup"]["entry_zone"] == "24100"
        assert data["setup"]["setup_type"] == "BREAKOUT"
        assert data["ai_view"]["bias"] == "LONG"
