"""
Observability — §40

Every major pipeline event must be traceable:
market state → forecast → trigger → AI request → AI response → validation →
stale check → risk check → order decision → broker event → position outcome

Use a shared correlation ID such as: analysis_id to link entire lifecycle.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger()


from pydantic import BaseModel as _BaseModel

class PipelineEvent(_BaseModel):
    analysis_id: str
    stage: str
    timestamp: datetime
    duration_ms: int | None = None
    payload: dict[str, Any] = {}
    status: str = "ok"

    model_config = {"extra": "allow"}  # type: ignore

# In-memory trace store (optionally persist to DB)
_trace_store: dict[str, list[dict]] = {}


def new_analysis_id() -> str:
    return str(uuid.uuid4())


def log_pipeline_event(
    analysis_id: str,
    stage: str,
    payload: dict[str, Any] | None = None,
    status: str = "ok",
    duration_ms: int | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    event = {
        "analysis_id": analysis_id,
        "stage": stage,
        "timestamp": now.isoformat(),
        "payload": payload or {},
        "status": status,
        "duration_ms": duration_ms,
    }
    if analysis_id not in _trace_store:
        _trace_store[analysis_id] = []
    _trace_store[analysis_id].append(event)
    # Structured log for external observability
    logger.info("pipeline_event", analysis_id=analysis_id, stage=stage, status=status, duration_ms=duration_ms)
    return event


def get_trace(analysis_id: str) -> list[dict]:
    return _trace_store.get(analysis_id, [])


def get_all_traces(limit: int = 50) -> list[dict]:
    # Return most recent traces
    all_events = []
    for aid, events in list(_trace_store.items())[-limit:]:
        all_events.append({"analysis_id": aid, "events": events})
    return all_events


class Timer:
    def __init__(self, analysis_id: str, stage: str):
        self.analysis_id = analysis_id
        self.stage = stage
        self.start = time.perf_counter()

    def stop(self, payload: dict | None = None, status: str = "ok") -> dict:
        duration_ms = int((time.perf_counter() - self.start) * 1000)
        return log_pipeline_event(self.analysis_id, self.stage, payload, status, duration_ms)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc:
            self.stop({"error": str(exc)[:300]}, status="error")
        else:
            self.stop()
