from __future__ import annotations

import abc
import hashlib
from typing import Any, Optional
from datetime import datetime, timezone
import structlog

from app.event_engine.models import RawSourceEvent, CanonicalEvent

logger = structlog.get_logger()


class EventSourceAdapter(abc.ABC):
    """Abstract Base Class for all event source adapters (§5).
    
    Guarantees consistent ingest, source integrity validation, 
    canonical identity derivation, and normalized representations.
    """

    def __init__(self, source_name: str, config: Optional[dict[str, Any]] = None):
        self.source_name = source_name
        self.config = config or {}
        self.logger = logger.bind(source=source_name)

    @abc.abstractmethod
    async def fetch(self) -> list[dict[str, Any]]:
        """Fetch raw unparsed events from the upstream source."""
        raise NotImplementedError

    @abc.abstractmethod
    def normalize(self, raw_item: dict[str, Any]) -> RawSourceEvent:
        """Normalize raw source payload into standard RawSourceEvent format."""
        raise NotImplementedError

    @abc.abstractmethod
    def validate(self, raw_source_event: RawSourceEvent) -> tuple[bool, Optional[str]]:
        """Validate source record integrity, signatures, and essential schema fields."""
        raise NotImplementedError

    @abc.abstractmethod
    def identify(self, raw_source_event: RawSourceEvent) -> str:
        """Generate a deterministic identity fingerprint for the event from source attributes."""
        raise NotImplementedError

    def compute_hash(self, *components: str) -> str:
        """Helper to create deterministic normalized SHA-256 fingerprint."""
        raw_str = "|".join(c.strip().upper() for c in components if c)
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]
