import pytest
from datetime import datetime, timezone

from app.event_engine.models import CanonicalEvent
from app.event_engine.scoring_service import scoring_service


def test_three_dimension_independence():
    """Spec §1: Treat EVENT IMPORTANCE, EXPECTED MARKET IMPACT, TRADING OPPORTUNITY
    as three completely independent dimensions. They must not be collapsed into a single score.
    """
    event = CanonicalEvent(
        canonical_event_id="RBI_MPC_20261009",
        title="RBI Monetary Policy Committee Resolution Oct 2026",
        event_type="CENTRAL_BANK",
        sub_type="MONETARY_POLICY_RATE_DECISION",
        entity_id="RBI",
        event_timestamp=datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc),
        metadata={"source_name": "RBI_OFFICIAL", "policy_action_type": "REPO_RATE_DECISION"},
    )

    scorecard = scoring_service.score_event(event, market_data_available=False)

    # 1. Event Importance must be calculated objectively based on rules/weights
    assert scorecard.importance.final_score > 70.0
    assert scorecard.importance.source_authority == 100.0
    assert scorecard.importance.scope == 95.0

    # 2. Market Impact must remain INSUFFICIENT_DATA in Phase 1 (no fabrication)
    assert scorecard.market_impact.status == "INSUFFICIENT_DATA"
    assert scorecard.market_impact.final_score is None

    # 3. Trading Opportunity must return INSUFFICIENT_DATA and enforce NO_TRADE
    assert scorecard.opportunity.status == "INSUFFICIENT_DATA"
    assert scorecard.opportunity.final_score is None
    assert scorecard.opportunity.final_decision == "NO_TRADE"

    # Core spec validation:
    # High Importance + High Impact + No Valid Setup = NO TRADE
    assert scorecard.final_decision == "NO_TRADE"


def test_hard_gate_enforcement():
    """Spec §16: A high numeric Opportunity Score must not override hard constraints.
    If a mandatory gate fails: Decision = NO_TRADE regardless of raw Opportunity Score.
    """
    event = CanonicalEvent(
        canonical_event_id="RBI_MPC_20261009",
        title="RBI MPC",
        event_type="CENTRAL_BANK",
        entity_id="RBI",
        event_timestamp=datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc),
    )

    # When market data is unavailable, MARKET_DATA_VALID gate fails
    opportunity = scoring_service.calculate_opportunity_score(event, market_data_available=False)
    assert "MARKET_DATA_VALID" in opportunity.failed_gates
    assert opportunity.final_decision == "NO_TRADE"


def test_missing_data_never_fabricated():
    """Spec §33: Never substitute fabricated data. Use INSUFFICIENT_DATA instead of zero."""
    event = CanonicalEvent(
        canonical_event_id="RBI_MPC_20261009",
        title="RBI MPC",
        event_type="CENTRAL_BANK",
        entity_id="RBI",
        event_timestamp=datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc),
    )

    market_impact = scoring_service.calculate_market_impact_score(event)
    assert market_impact.final_score is not 0.0
    assert market_impact.final_score is None
    assert market_impact.status == "INSUFFICIENT_DATA"
