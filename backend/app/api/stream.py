"""
Unified app stream transport — P1-3 (SSE multiplex) + P1-4 (auth/tickets).

`GET  /api/v1/stream`         — one SSE connection per tab carrying
                                `view.section.changed`, `signal.event`,
                                `hint.raised`, `hint.cleared`, `heartbeat`.
                                Auth is the standard bearer dependency because
                                the frontend consumes it with `fetch()` +
                                `ReadableStream` (D1), which can set headers.
`POST /api/v1/stream/ticket`  — mint a single-use, read-only, 60 s ticket for
                                transports that cannot set headers (the market
                                feed WebSocket, per D1).

Frame shape mirrors `app/signals/sse.py`: every `data:` line is
`{"event", "data", "priority", "seq", "timestamp"}`; the SSE `event:` name is
the same as the inner `event` field.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.security import AuthUser, get_current_user, require_auth
from app.services.app_stream import app_stream_hub, ticket_store

router = APIRouter(prefix="/api/v1", tags=["stream"])


@router.get("/stream")
async def stream_app(user: AuthUser = Depends(get_current_user)) -> StreamingResponse:
    """Live multiplexed SSE feed — one connection per tab (P1-3)."""
    queue = app_stream_hub.subscribe()
    return StreamingResponse(
        app_stream_hub.event_generator(queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/stream/ticket")
async def issue_stream_ticket(
    user: AuthUser = Depends(require_auth),
) -> dict:
    """Mint a single-use, read-only ticket for header-less transports (P1-4)."""
    ticket, expires_in = ticket_store.issue_ticket(user.user_id)
    return {"ticket": ticket, "expires_in": expires_in}
