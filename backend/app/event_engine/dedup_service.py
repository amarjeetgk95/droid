from __future__ import annotations

import difflib
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
import structlog

from app.event_engine.models import (
    CanonicalEvent,
    DeduplicationMatch,
    RawSourceEvent,
)

logger = structlog.get_logger()

# Known entity normalization map
ENTITY_ALIASES: dict[str, str] = {
    "RESERVE BANK OF INDIA": "RBI",
    "RESERVE BANK": "RBI",
    "CENTRAL BANK OF INDIA": "CENTRAL_BANK_IN",
    "SECURITIES AND EXCHANGE BOARD OF INDIA": "SEBI",
    "NATIONAL STOCK EXCHANGE": "NSE",
    "BOMBAY STOCK EXCHANGE": "BSE",
    "MINISTRY OF FINANCE": "MOF_INDIA",
}


class DeduplicationService:
    """Canonical Identity & Multi-Source Deduplication Engine (§6).
    
    Prevents duplicate entries across multiple ingestion sources (e.g., RBI Official +
    News + Exchange Feeds) without losing original source records.
    """

    def normalize_entity(self, raw_entity: str) -> str:
        """Normalize issuer/entity names into standardized keys."""
        cleaned = re.sub(r"[^A-Z0-9\s]", "", raw_entity.upper()).strip()
        return ENTITY_ALIASES.get(cleaned, cleaned)

    def normalize_subject(self, text: str) -> str:
        """Strip punctuation and stop words for fuzzy similarity comparison."""
        lowered = text.lower()
        cleaned = re.sub(r"[^\w\s]", " ", lowered)
        tokens = [w for w in cleaned.split() if len(w) > 2 and w not in {"the", "and", "for", "with", "from"}]
        return " ".join(tokens)

    def calculate_text_similarity(self, text1: str, text2: str) -> float:
        """String similarity ratio using Gestalt pattern matching."""
        s1 = self.normalize_subject(text1)
        s2 = self.normalize_subject(text2)
        if not s1 or not s2:
            return 0.0
        return difflib.SequenceMatcher(None, s1, s2).ratio()

    def classify_match(
        self,
        candidate_event: CanonicalEvent,
        existing_event: CanonicalEvent,
    ) -> DeduplicationMatch:
        """Determine relationship between an incoming candidate and an existing event (§6).
        
        Evaluates:
          - Canonical ID match -> EXACT_DUPLICATE
          - Normalized entity & type match + close time window + subject similarity:
              * > 0.85 similarity within 6 hours -> EXACT_DUPLICATE
              * > 0.65 similarity within 24 hours -> PROBABLE_DUPLICATE
              * > 0.40 similarity within 7 days -> POSSIBLE_MATCH
              * Otherwise -> UNRELATED
        """
        # Exact canonical ID match is always exact duplicate
        if candidate_event.canonical_event_id == existing_event.canonical_event_id:
            return "EXACT_DUPLICATE"

        cand_entity = self.normalize_entity(candidate_event.entity_id)
        exist_entity = self.normalize_entity(existing_event.entity_id)

        # Different entities cannot be duplicates
        if cand_entity != exist_entity:
            return "UNRELATED"

        # Time difference in minutes
        t1 = candidate_event.event_timestamp
        t2 = existing_event.event_timestamp
        delta_seconds = abs((t1 - t2).total_seconds())
        delta_hours = delta_seconds / 3600.0

        similarity = self.calculate_text_similarity(candidate_event.title, existing_event.title)

        # Same entity, same event type
        is_same_type = candidate_event.event_type == existing_event.event_type
        is_same_sub_type = (
            candidate_event.sub_type and existing_event.sub_type and 
            candidate_event.sub_type == existing_event.sub_type
        )

        # EXACT DUPLICATE: Same date, same sub-type or very high title similarity within 6h
        if is_same_type and (
            (is_same_sub_type and delta_hours <= 12) or 
            (similarity >= 0.85 and delta_hours <= 6)
        ):
            return "EXACT_DUPLICATE"

        # PROBABLE DUPLICATE: Moderate similarity within 24 hours
        if is_same_type and delta_hours <= 24 and (similarity >= 0.60 or is_same_sub_type):
            return "PROBABLE_DUPLICATE"

        # POSSIBLE MATCH: Related topic/entity within 7 days that requires human review
        if delta_hours <= 168 and (similarity >= 0.40 or is_same_sub_type):
            return "POSSIBLE_MATCH"

        return "UNRELATED"


dedup_service = DeduplicationService()
