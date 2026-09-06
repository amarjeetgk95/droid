import pytest
from datetime import datetime, timezone, timedelta

from app.event_engine.sources.rbi import RBISourceAdapter
from app.event_engine.models import CanonicalEvent, RawSourceEvent
from app.event_engine.dedup_service import dedup_service


@pytest.mark.asyncio
async def test_rbi_adapter_fetch_normalize_validate_identify():
    adapter = RBISourceAdapter()
    raw_items = await adapter.fetch()
    assert len(raw_items) > 0

    first_item = raw_items[0]
    norm = adapter.normalize(first_item)
    assert norm.source_name == "RBI_OFFICIAL"
    assert norm.is_verified is True

    valid, err = adapter.validate(norm)
    assert valid is True
    assert err is None

    canon_id = adapter.identify(norm)
    assert canon_id.startswith("RBI_")
    assert "2026" in canon_id or "2027" in canon_id


def test_rbi_adapter_validation_failure_cases():
    adapter = RBISourceAdapter()

    # Empty payload
    empty_event = RawSourceEvent(source_name="RBI", raw_payload={})
    valid, err = adapter.validate(empty_event)
    assert valid is False

    # Bad date format
    bad_date_event = RawSourceEvent(
        source_name="RBI",
        raw_payload={"title": "RBI MPC Meeting", "event_date": "not-a-date"},
    )
    valid, err = adapter.validate(bad_date_event)
    assert valid is False
    assert "Invalid date format" in err


def test_event_deduplication_classes():
    now = datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc)

    e1 = CanonicalEvent(
        canonical_event_id="RBI_MPC_20261009",
        title="RBI Monetary Policy Committee Resolution Oct 2026",
        event_type="CENTRAL_BANK",
        sub_type="MONETARY_POLICY_RATE_DECISION",
        entity_id="RBI",
        event_timestamp=now,
    )

    # Exact duplicate (same ID)
    assert dedup_service.classify_match(e1, e1) == "EXACT_DUPLICATE"

    # Probable duplicate (same entity and type within 12 hours)
    e2 = CanonicalEvent(
        canonical_event_id="NSE_RBI_ANNOUNCEMENT_1009",
        title="RBI MPC Policy Statement Announcement",
        event_type="CENTRAL_BANK",
        sub_type="MONETARY_POLICY_RATE_DECISION",
        entity_id="RBI",
        event_timestamp=now + timedelta(hours=2),
    )
    match_result = dedup_service.classify_match(e2, e1)
    assert match_result in ("EXACT_DUPLICATE", "PROBABLE_DUPLICATE")

    # Unrelated (different entity)
    e3 = CanonicalEvent(
        canonical_event_id="HDFCBANK_EARNINGS_20261015",
        title="HDFC Bank Q2 FY27 Earnings",
        event_type="EARNINGS",
        entity_id="HDFCBANK",
        event_timestamp=now + timedelta(days=6),
    )
    assert dedup_service.classify_match(e3, e1) == "UNRELATED"


def test_verification_status_and_certainty_separation():
    """Spec §7: Verification Status and Event Certainty are independent concepts."""
    event = CanonicalEvent(
        canonical_event_id="RBI_GOV_SPEECH_20261101",
        title="RBI Governor Address at Banking Summit",
        event_type="CENTRAL_BANK",
        entity_id="RBI",
        event_timestamp=datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc),
        verification_status="VERIFIED",
        certainty="APPROXIMATE",
        timestamp_precision="DATE_ONLY",
    )
    assert event.verification_status == "VERIFIED"
    assert event.certainty == "APPROXIMATE"
    assert event.timestamp_precision == "DATE_ONLY"
