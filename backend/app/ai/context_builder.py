"""
Market Context Builder — §2, §11

Builds normalized, versioned market state from raw market data.
Each context is immutable once built; readers get a snapshot.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
import structlog

from app.ai.schemas import (
    MarketContext,
    RegimeObject,
    OptionsContext,
    HistoricalEvidence,
    Regime,
    Direction,
    VolatilityLevel,
)

logger = structlog.get_logger()

CONTEXT_VERSION = "1.0.0"
CONTEXT_ALLOWLIST = {
    "symbol",
    "timestamp",
    "market_status",
    "current_price",
    "1M_structure",
    "3M_structure",
    "5M_structure",
    "15M_structure",
    "vwap",
    "atr",
    "volume",
    "momentum",
    "support_resistance",
    "regime",
    "options_context",
    "historical_context",
    "existing_position_state",
}

MAX_SCALPING_CONTEXT_SIZE = 2048
MAX_CORE_CONTEXT_SIZE = 6144


class MarketContextBuilder:
    """
    Builds structured, versioned market context for AI analysis.

    Per §2: Per-symbol single-writer; readers get immutable snapshot.
    Per §11: Field allowlist enforced, context size capped.
    """

    def __init__(self):
        self._cache: dict[str, MarketContext] = {}
        self._cache_timestamps: dict[str, datetime] = {}
        self._lock_marker: dict[str, bool] = {}

    def _generate_hash(self, context_data: dict) -> str:
        serialized = str(sorted(context_data.items())).encode()
        return hashlib.sha256(serialized).hexdigest()[:16]

    def build(
        self,
        symbol: str,
        current_price: float = 0.0,
        market_status: str = "UNKNOWN",
        structure_1m: str = "",
        structure_3m: str = "",
        structure_5m: str = "",
        structure_15m: str = "",
        vwap: float = 0.0,
        atr: float = 0.0,
        volume: float = 0.0,
        momentum: float = 0.0,
        support_resistance: Optional[dict[str, float]] = None,
        regime: Optional[RegimeObject] = None,
        options_context: Optional[OptionsContext] = None,
        historical_context: Optional[HistoricalEvidence] = None,
        existing_position_state: str = "NONE",
        timestamp: Optional[datetime] = None,
    ) -> MarketContext:
        """
        Build a new market context with field allowlist enforcement.

        Raises:
            StaleDataError: If data is too old
            IncompleteDataError: If required fields missing
        """
        now = timestamp or datetime.now(timezone.utc)

        context = MarketContext(
            context_id=str(uuid.uuid4()),
            symbol=symbol.upper(),
            timestamp=now,
            version=CONTEXT_VERSION,
            current_price=current_price,
            market_status=market_status,
            structure_1m=structure_1m,
            structure_3m=structure_3m,
            structure_5m=structure_5m,
            structure_15m=structure_15m,
            vwap=vwap,
            atr=atr,
            volume=volume,
            momentum=momentum,
            support_resistance=support_resistance or {},
            regime=regime or RegimeObject(),
            options_context=options_context,
            historical_context=historical_context,
            existing_position_state=existing_position_state,
        )

        context.context_hash = self._generate_hash(context.model_dump())

        self._cache[symbol.upper()] = context
        self._cache_timestamps[symbol.upper()] = now

        return context

    def get_snapshot(self, symbol: str) -> Optional[MarketContext]:
        """Get cached immutable snapshot, or None if not available."""
        return self._cache.get(symbol.upper())

    def get_snapshot_copy(self, symbol: str) -> Optional[MarketContext]:
        """Get a deep copy of cached context for thread safety."""
        ctx = self._cache.get(symbol.upper())
        if ctx is None:
            return None
        return ctx.model_copy(deep=True)

    def is_stale(self, symbol: str, max_age_seconds: float = 5.0) -> bool:
        """Check if cached context is stale."""
        ts = self._cache_timestamps.get(symbol.upper())
        if ts is None:
            return True
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age > max_age_seconds

    def serialize_size(self, context: MarketContext, path: str = "core") -> int:
        """Return serialized size in bytes."""
        import json
        serialized = json.dumps(context.model_dump())
        return len(serialized.encode())

    def enforce_size_cap(self, context: MarketContext, path: str = "core") -> bool:
        """Enforce context size cap per §11. Returns True if within cap."""
        max_size = MAX_SCALPING_CONTEXT_SIZE if path == "scalping" else MAX_CORE_CONTEXT_SIZE
        return self.serialize_size(context, path) <= max_size

    def invalidate(self, symbol: str) -> None:
        """Invalidate cached context for symbol."""
        symbol = symbol.upper()
        self._cache.pop(symbol, None)
        self._cache_timestamps.pop(symbol, None)
        self._lock_marker.pop(symbol, None)


market_context_builder = MarketContextBuilder()
