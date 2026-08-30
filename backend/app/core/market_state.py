"""
Market State Versioning — §6

Every significant market state receives a unique identifier: state_version

When an AI request is triggered:
1. Capture the exact state.
2. Store state_version.
3. Store trigger timestamp.
4. Store trigger price.
5. Store trigger ATR.
6. Send the immutable snapshot to the AI.

AI response must contain or be associated with that state_version.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class MarketState(BaseModel):
    """
    Compact structured MarketState payload per §21.
    Sent as immutable snapshot to AI.
    """
    state_version: int = Field(description="Monotonic unique market state identifier")
    timestamp: datetime = Field(description="ISO timestamp of state capture")
    symbol: str = Field(description="e.g. NIFTY")
    current_price: float
    regime: str = Field(description="e.g. TRENDING_UP, RANGING, VOLATILE")
    mtf: dict[str, str] = Field(default_factory=dict, description="1m/5m/15m/1h bias")
    technical: dict[str, Any] = Field(default_factory=dict, description="RSI, MACD, VWAP, ATR etc")
    direction_model: dict[str, float] = Field(default_factory=dict, description="prob_up/prob_down")
    tsfm: dict[str, float] = Field(default_factory=dict, description="p10/p50/p90")
    orderflow: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    futures: dict[str, Any] = Field(default_factory=dict)
    news: list[Any] = Field(default_factory=list)
    # Trigger snapshot fields (§23 staleness guard)
    trigger_price: float | None = None
    trigger_atr: float | None = None
    trigger_timestamp: datetime | None = None
    # Optional position context (§30) — informational only
    position_context: dict[str, Any] | None = None
    # Correlation ID for observability §40
    analysis_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    # Model metadata
    direction_model_version: str | None = None
    direction_model_timestamp: datetime | None = None

    model_config = {"extra": "allow"}


# Global monotonic counter for state_version
_state_counter: int = 0
_state_hash_cache: dict[str, int] = {}


def _next_state_version() -> int:
    global _state_counter
    _state_counter += 1
    # Ensure uniqueness across restarts by mixing timestamp
    base = int(datetime.now(timezone.utc).timestamp() * 1000) % 100000
    return _state_counter * 100000 + base


def hash_market_state(raw: dict) -> str:
    """Deterministic hash for deduplication (§7)."""
    # Stable JSON representation
    import json
    serialized = json.dumps(raw, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def capture_market_state(
    symbol: str,
    current_price: float,
    atr: float,
    regime: str,
    mtf: dict,
    technical: dict,
    direction_model: dict,
    tsfm: dict,
    orderflow: dict | None = None,
    options: dict | None = None,
    futures: dict | None = None,
    news: list | None = None,
    position_context: dict | None = None,
) -> MarketState:
    """
    Capture immutable snapshot per §6 steps 1-6.
    Stores state_version, trigger timestamp/price/ATR.
    """
    now = datetime.now(timezone.utc)
    sv = _next_state_version()
    state = MarketState(
        state_version=sv,
        timestamp=now,
        symbol=symbol,
        current_price=current_price,
        regime=regime,
        mtf=mtf or {},
        technical=technical or {},
        direction_model=direction_model or {},
        tsfm=tsfm or {},
        orderflow=orderflow or {},
        options=options or {},
        futures=futures or {},
        news=news or [],
        trigger_price=current_price,
        trigger_atr=atr,
        trigger_timestamp=now,
        position_context=position_context,
        analysis_id=str(uuid.uuid4()),
    )
    return state


def validate_state_version_match(request_version: int, response_version: int | None) -> bool:
    """Check AI response is associated with correct state_version."""
    if response_version is None:
        return False
    return request_version == response_version
