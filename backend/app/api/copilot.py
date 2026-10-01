"""Copilot Intelligence API (spec Â§27).

  POST /api/copilot/analyze        structured analysis (chat/analyze/briefing)
  POST /api/copilot/chat           conversational follow-up (uses prior context)
  GET  /api/copilot/predictions    audit list (paginated, filterable)
  POST /api/copilot/predictions/outcome   append an outcome (never overwrites)
  GET  /api/copilot/evaluation     measured metrics only (sample size gated)
  GET  /api/copilot/health         readiness (sources + dataset presence)

All quantitative answers come from the orchestrator; the API layer only
validates, envelopes and observes.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Body, Depends, Header, Query

from app.api.envelope import envelope
from app.copilot.models import (
    CopilotAnalyzeRequest,
    CopilotChatRequest,
    PredictionOutcomeRequest,
)
from app.copilot.orchestrator import copilot_orchestrator
from app.copilot.sanitizer import sanitize_payload
from app.core.security import AuthUser, get_current_user
from app.models.market import DataStatus

logger = structlog.get_logger()

router = APIRouter(prefix="/api/copilot", tags=["copilot"])
_PROVIDER = "copilot_intelligence_engine"


def _ok(data: object, status: DataStatus = DataStatus.LIVE) -> dict:
    return envelope(sanitize_payload(data), provider=_PROVIDER, status=status)


def _forward_keys(payload: object, key: str | None, gemini: str | None, openai: str | None) -> None:
    if key and not getattr(payload, "openrouter_api_key", None):
        setattr(payload, "openrouter_api_key", key)
    if gemini and not getattr(payload, "gemini_api_key", None):
        setattr(payload, "gemini_api_key", gemini)
    if openai and not getattr(payload, "openai_api_key", None):
        setattr(payload, "openai_api_key", openai)


@router.post("/analyze")
async def analyze_market(
    payload: CopilotAnalyzeRequest = Body(...),
    x_openrouter_key: str | None = Header(default=None, alias="X-OpenRouter-Key"),
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
    x_openai_key: str | None = Header(default=None, alias="X-OpenAI-Key"),
    user: AuthUser | None = Depends(get_current_user),
) -> dict:
    """Run a full copilot analysis (intent â†’ evidence â†’ structured response)."""
    _forward_keys(payload, x_openrouter_key, x_gemini_key, x_openai_key)
    response = await copilot_orchestrator.analyze(payload)
    status = DataStatus.LIVE if response.meta.data_freshness == "LIVE" else DataStatus.DEGRADED
    return _ok(response, status=status)


@router.post("/chat")
async def chat_follow_up(
    payload: CopilotChatRequest = Body(...),
    x_openrouter_key: str | None = Header(default=None, alias="X-OpenRouter-Key"),
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
    x_openai_key: str | None = Header(default=None, alias="X-OpenAI-Key"),
    user: AuthUser | None = Depends(get_current_user),
) -> dict:
    """Conversational follow-up with structured-context carry-over."""
    _forward_keys(payload, x_openrouter_key, x_gemini_key, x_openai_key)
    response = await copilot_orchestrator.analyze_chat(payload)
    status = DataStatus.LIVE if response.meta.data_freshness == "LIVE" else DataStatus.DEGRADED
    return _ok(response, status=status)


@router.get("/predictions")
async def list_predictions(
    symbol: str | None = Query(default=None),
    horizon: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user: AuthUser | None = Depends(get_current_user),
) -> dict:
    """List stored predictions (newest first)."""
    from app.copilot.audit import copilot_audit_store

    items = await copilot_audit_store.list_predictions(symbol=symbol, horizon=horizon, limit=limit)
    return _ok({"predictions": items, "count": len(items)})


@router.post("/predictions/outcome")
async def record_prediction_outcome(
    payload: PredictionOutcomeRequest = Body(...),
    user: AuthUser | None = Depends(get_current_user),
) -> dict:
    """Append an outcome to a stored prediction (append-only)."""
    from app.copilot.audit import copilot_audit_store

    result = await copilot_audit_store.record_outcome(
        prediction_id=payload.prediction_id,
        outcome=payload.outcome,
        realized_return_pct=payload.realized_return_pct,
        realized_direction=payload.realized_direction,
        level_result=payload.level_result,
        notes=payload.notes,
    )
    return _ok(result)


@router.get("/evaluation")
async def evaluation_summary(
    symbol: str | None = Query(default=None),
    horizon: str | None = Query(default=None),
    window_days: int = Query(default=30, ge=1, le=365),
    user: AuthUser | None = Depends(get_current_user),
) -> dict:
    """Measured evaluation metrics â€” populated only when outcomes exist."""
    from app.copilot.audit import copilot_audit_store

    summary = await copilot_audit_store.evaluation_summary(symbol=symbol, horizon=horizon, window_days=window_days)
    status = DataStatus.LIVE if summary.get("available") else DataStatus.OFFLINE
    return _ok(summary, status=status)


@router.get("/health")
async def copilot_health(
    user: AuthUser | None = Depends(get_current_user),
) -> dict:
    """Readiness snapshot: which evidence sources are reachable right now."""
    from app.copilot.market_context import SOURCE_LABELS

    checks = {source: "wired" for source in ("quote", "regime", "options", "futures", "flow")}
    try:
        from app.market_core.data.dataset_manager import DatasetManager

        manager = DatasetManager()
        historical = {symbol: bool(manager.exists(symbol, "1m")) for symbol in ("NIFTY", "BANKNIFTY", "SENSEX")}
    except Exception:
        historical = {symbol: False for symbol in ("NIFTY", "BANKNIFTY", "SENSEX")}
    return _ok(
        {
            "sources": {
                source: {"status": status, "label": SOURCE_LABELS.get(source, source)}
                for source, status in checks.items()
            },
            "historical_datasets": historical,
            "orchestrator": "ready",
        }
    )
