"""
Canonical InstrumentEvent — §5
Every inbound market event first becomes a canonical InstrumentEvent.
Preserves event_time / receive_time / processing_time as separate concepts.
Sequence integrity built-in.
"""
from __future__ import annotations

import uuid
import time
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field

from app.algo.money import D


class EventType(str, Enum):
    TICK = "TICK"
    BAR = "BAR"
    QUOTE = "QUOTE"
    ORDER_BOOK = "ORDER_BOOK"
    OI_UPDATE = "OI_UPDATE"
    FUNDING = "FUNDING"
    LIQUIDATION = "LIQUIDATION"
    SESSION = "SESSION"
    HEARTBEAT = "HEARTBEAT"


class InstrumentEvent(BaseModel):
    """
    Canonical event envelope — §5 minimum fields + extensions.
    All timestamps are integers milliseconds since epoch UTC unless otherwise noted.
    """
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    instrument_id: str
    asset_class: str  # INDEX / CRYPTO
    event_type: EventType = EventType.TICK
    # --- Time model ---
    canonical_timestamp_utc: int  # UTC ms — exchange/authoritative time
    exchange_timestamp: int | None = None  # raw exchange ts (may differ for cross-check)
    received_timestamp_utc: int = Field(default_factory=lambda: int(time.time()*1000))
    # For server processing time use model field below lazily
    processing_timestamp_utc: int | None = None

    sequence_id: int  # deterministic internal monotonic per instrument/source
    source_sequence_id: int | None = None  # original from source if any
    source_id: str = "broker_feed"

    # Payload — price etc. Keep Decimal as strings for serialization safety
    price: str | None = None
    quantity: str | None = None
    volume: int | None = None
    bid: str | None = None
    ask: str | None = None
    # Extra telemetry
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    @classmethod
    def create(
        cls,
        instrument_id: str,
        asset_class: str,
        canonical_timestamp_utc: int,
        sequence_id: int,
        source_id: str = "broker_feed",
        event_type: EventType | str = EventType.TICK,
        exchange_timestamp: int | None = None,
        source_sequence_id: int | None = None,
        price: Any | None = None,
        quantity: Any | None = None,
        volume: int | None = None,
        bid: Any | None = None,
        ask: Any | None = None,
        metadata: dict | None = None,
    ) -> "InstrumentEvent":
        now_ms = int(time.time()*1000)
        if isinstance(event_type, str):
            event_type = EventType(event_type)
        return cls(
            event_id=str(uuid.uuid4()),
            instrument_id=instrument_id.upper(),
            asset_class=asset_class,
            event_type=event_type,
            canonical_timestamp_utc=canonical_timestamp_utc,
            exchange_timestamp=exchange_timestamp if exchange_timestamp is not None else canonical_timestamp_utc,
            received_timestamp_utc=now_ms,
            sequence_id=sequence_id,
            source_sequence_id=source_sequence_id,
            source_id=source_id,
            price=str(D(price)) if price is not None else None,
            quantity=str(D(quantity)) if quantity is not None else None,
            volume=volume,
            bid=str(D(bid)) if bid is not None else None,
            ask=str(D(ask)) if ask is not None else None,
            metadata=metadata or {},
        )

    def mark_processed(self) -> None:
        self.processing_timestamp_utc = int(time.time()*1000)

    @property
    def event_time_dt(self) -> datetime:
        return datetime.fromtimestamp(self.canonical_timestamp_utc/1000, tz=timezone.utc)

    @property
    def received_time_dt(self) -> datetime:
        return datetime.fromtimestamp(self.received_timestamp_utc/1000, tz=timezone.utc)

    def age_ms(self, now_ms: int | None = None) -> int:
        now_ms = now_ms if now_ms is not None else int(time.time()*1000)
        return now_ms - self.canonical_timestamp_utc

    def decimal_price(self) -> Decimal | None:
        return D(self.price) if self.price is not None else None


# Backwards compat alias for older TickEvent code paths
CanonicalEvent = InstrumentEvent
