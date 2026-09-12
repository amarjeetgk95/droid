"""Shared API response envelope helpers.

Every router used to hand-roll a private ``_meta()``/``_make_meta()`` plus the
``{"data": ..., "error": None, "meta": ...}`` dict on each endpoint. This module
is the single source of that contract (see ``app.models.market.ApiResponse``):

    {"data": <model_dump(mode="json") or plain>, "error": None, "meta": {provider, timestamp, status}}

Errors stay as FastAPI ``HTTPException`` → ``{"detail": ...}`` (the frontend
``lib/api/client.ts`` already reads ``detail``); an unhandled-exception hook in
``app.main`` converts stray exceptions to the same shape so routers no longer
need try/except wrappers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from app.models.market import ApiMeta, DataStatus


def make_meta(
    provider: str = "fyers",
    status: DataStatus = DataStatus.LIVE,
) -> ApiMeta:
    """Build the standard ``ApiMeta`` block."""
    return ApiMeta(provider=provider, timestamp=datetime.now(timezone.utc), status=status)


def envelope(
    data: Any,
    provider: str,
    status: DataStatus = DataStatus.LIVE,
) -> dict:
    """Wrap ``data`` (pydantic model, list of models, or plain JSON-able) in the standard envelope."""
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    elif isinstance(data, (list, tuple)):
        data = [d.model_dump(mode="json") if isinstance(d, BaseModel) else d for d in data]
    return {
        "data": data,
        "error": None,
        "meta": make_meta(provider, status).model_dump(),
    }
