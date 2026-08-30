"""
Tests for Supabase / PostgreSQL repositories:
- AlertRepository
- PaperTradingRepository
- MLRepository
- AIRepository
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from app.repositories.alert_repository import AlertRepository
from app.repositories.paper_repository import PaperTradingRepository
from app.repositories.ml_repository import MLRepository
from app.repositories.ai_repository import AIRepository
from app.models.alert import AlertPayload
from app.models.paper import VirtualOrder, VirtualPosition
from app.models.ml import MLPredictionResponse, MLFeatureContribution
from app.models.ai import AIInsightResponse


def create_mock_session():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    return mock_session


class TestAlertRepository:
    """Test AlertRepository async database operations."""

    @pytest.mark.asyncio
    async def test_create_and_get_alert_rule(self):
        mock_session = create_mock_session()
        user_id = uuid4()
        payload = AlertPayload(
            name="Test NIFTY Alert",
            symbol="NIFTY",
            alert_type="PRICE_LEVEL",
            condition="GREATER_THAN",
            threshold=25500.0,
            channel="IN_APP",
        )

        rule = await AlertRepository.create(mock_session, user_id, payload)
        assert rule.name == "Test NIFTY Alert"
        assert rule.symbol == "NIFTY"
        assert rule.threshold == 25500.0
        assert mock_session.add.called
        assert mock_session.commit.called


class TestPaperTradingRepository:
    """Test PaperTradingRepository async database operations."""

    @pytest.mark.asyncio
    async def test_portfolio_lifecycle(self):
        mock_session = create_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        user_id = uuid4()
        portfolio = await PaperTradingRepository.get_or_create_portfolio(mock_session, user_id)
        assert portfolio.user_id == user_id
        assert portfolio.virtual_capital == 1000000.0
        assert mock_session.add.called

    @pytest.mark.asyncio
    async def test_save_virtual_order(self):
        mock_session = create_mock_session()
        user_id = uuid4()
        order = VirtualOrder(
            order_id="ORD-TEST12",
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol="NIFTY 25000 CE",
            underlying="NIFTY",
            side="BUY",
            order_type="MARKET",
            product="INTRADAY",
            quantity=50,
            price=150.0,
            status="FILLED",
            fill_price=150.0,
        )

        db_order = await PaperTradingRepository.save_order(mock_session, user_id, order)
        assert db_order.order_id == "ORD-TEST12"
        assert db_order.quantity == 50
        assert mock_session.add.called


class TestMLRepository:
    """Test MLRepository async persistence."""

    @pytest.mark.asyncio
    async def test_save_prediction(self):
        mock_session = create_mock_session()
        prediction = MLPredictionResponse(
            symbol="NIFTY",
            timestamp=datetime.now(timezone.utc),
            spot_price=24850.0,
            bullish_pct=65.0,
            neutral_pct=20.0,
            bearish_pct=15.0,
            trend_strength=72.0,
            confidence_score=80.0,
            predicted_bias="BULLISH",
            market_regime="TRENDING_BULLISH",
            top_features=[
                MLFeatureContribution(
                    feature_name="Supertrend",
                    value=24700.0,
                    contribution=0.25,
                    description="Bullish filter",
                )
            ],
        )

        db_pred = await MLRepository.save_prediction(mock_session, prediction)
        assert db_pred.symbol == "NIFTY"
        assert db_pred.bullish_pct == 65.0
        assert db_pred.predicted_bias == "BULLISH"
        assert mock_session.add.called


class TestAIRepository:
    """Test AIRepository async persistence."""

    @pytest.mark.asyncio
    async def test_save_ai_report(self):
        mock_session = create_mock_session()
        report = AIInsightResponse(
            symbol="NIFTY",
            timestamp=datetime.now(timezone.utc),
            market_bias="BULLISH",
            confidence=85.0,
            executive_summary="Institutional call buying detected near key support.",
            options_interpretation="PCR rising above 1.2",
            futures_flow_analysis="Long buildup observed",
            regime_and_levels="Above VWAP and 20 EMA",
            recommended_strategy_framework="Bull Call Spread",
            risk_management_notes="Strict stop loss below 24,700",
            provider_used="gemini",
        )

        db_report = await AIRepository.save_report(mock_session, report)
        assert db_report.symbol == "NIFTY"
        assert db_report.market_bias == "BULLISH"
        assert db_report.confidence == 85.0
        assert mock_session.add.called
