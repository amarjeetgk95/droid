"""
Backtesting / Outcome Logging — §38

For every AI event store:
state_version, timestamp, symbol, market state, technical features, LightGBM probability,
P10/P50/P90, AI provider/model/task/bias/confidence breakdown, trigger reason, risk calculations,
execution outcome.

When prediction horizon completes, store:
actual movement, max favorable excursion, max adverse excursion, target/invalidation outcome.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger()

# In-memory log (persist to DB in production)
_outcome_logs: list[dict] = []


def log_ai_event(
    state_version: int,
    timestamp: datetime,
    symbol: str,
    market_state: dict,
    technical_features: dict | None,
    direction_prob: dict | None,
    tsfm_forecast: dict | None,
    ai_provider: str,
    ai_model: str,
    ai_task: str,
    ai_bias: str,
    confidence_breakdown: dict | None,
    trigger_reason: str,
    risk_calculations: dict | None,
    analysis_id: str,
) -> dict:
    entry = {
        "state_version": state_version,
        "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
        "symbol": symbol,
        "market_state": market_state,
        "technical_features": technical_features,
        "direction_model": direction_prob,
        "tsfm": tsfm_forecast,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "ai_task": ai_task,
        "ai_bias": ai_bias,
        "confidence_breakdown": confidence_breakdown,
        "trigger_reason": trigger_reason,
        "risk_calculations": risk_calculations,
        "analysis_id": analysis_id,
        "outcome": None,  # filled later when horizon completes
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    _outcome_logs.insert(0, entry)
    if len(_outcome_logs) > 500:
        _outcome_logs.pop()
    logger.info("ai_outcome_logged", state_version=state_version, symbol=symbol, analysis_id=analysis_id)
    return entry


def log_horizon_outcome(
    analysis_id: str,
    actual_movement: float | None,
    max_favorable_excursion: float | None = None,
    max_adverse_excursion: float | None = None,
    target_outcome: str | None = None,
    invalidation_outcome: str | None = None,
) -> dict | None:
    for entry in _outcome_logs:
        if entry.get("analysis_id") == analysis_id:
            entry["outcome"] = {
                "actual_movement": actual_movement,
                "max_favorable_excursion": max_favorable_excursion,
                "max_adverse_excursion": max_adverse_excursion,
                "target_outcome": target_outcome,
                "invalidation_outcome": invalidation_outcome,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            logger.info("horizon_outcome_logged", analysis_id=analysis_id, actual_movement=actual_movement)
            return entry
    return None


def get_outcome_logs(limit: int = 50, symbol: str | None = None) -> list[dict]:
    logs = _outcome_logs
    if symbol:
        logs = [l for l in logs if l.get("symbol", "").upper() == symbol.upper()]
    return logs[:limit]
