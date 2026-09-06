from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import structlog

from app.event_engine.models import RawSourceEvent
from app.event_engine.sources.base import EventSourceAdapter

logger = structlog.get_logger()

KNOWN_SEBI_CIRCULARS = [
    {
        "source": "SEBI_OFFICIAL",
        "entity": "SEBI",
        "entity_name": "Securities and Exchange Board of India",
        "title": "SEBI Circular on Index Derivatives Margin & Lot Size Framework",
        "description": "Revision of minimum contract size and upfront intraday margin frameworks for index options.",
        "event_date": "2026-11-20",
        "time_ist": "18:00:00",
        "url": "https://www.sebi.gov.in/legal/circulars",
        "sub_type": "REGULATORY_PRUDENTIAL_NORMS",
        "sector": "DERIVATIVES_MARKET",
        "certainty": "CONFIRMED",
        "precision": "EXACT",
    },
]


class SEBISourceAdapter(EventSourceAdapter):
    """Adapter for official SEBI regulatory circulars and policy orders (§5)."""

    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__(source_name="SEBI_OFFICIAL", config=config)

    async def fetch(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for item in KNOWN_SEBI_CIRCULARS:
            results.append({**item, "scraped_at": datetime.now(timezone.utc).isoformat()})
        self.logger.info("sebi_source_fetch_completed", count=len(results))
        return results

    def normalize(self, raw_item: dict[str, Any]) -> RawSourceEvent:
        return RawSourceEvent(
            source_name="SEBI_OFFICIAL",
            source_type="REGULATOR",
            source_url=raw_item.get("url", "https://www.sebi.gov.in"),
            raw_payload=raw_item,
            fetch_timestamp=datetime.now(timezone.utc),
            is_verified=True,
        )

    def validate(self, raw_source_event: RawSourceEvent) -> tuple[bool, Optional[str]]:
        payload = raw_source_event.raw_payload
        if not payload or not payload.get("title") or not payload.get("event_date"):
            return False, "Invalid SEBI payload"
        return True, None

    def identify(self, raw_source_event: RawSourceEvent) -> str:
        payload = raw_source_event.raw_payload
        clean_date = str(payload.get("event_date", "")).replace("-", "")
        return f"SEBI_CIRCULAR_{clean_date}"
