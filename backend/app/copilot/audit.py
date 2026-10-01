"""Prediction Audit persistence (spec §14, §15, §35).

Every completed copilot forecast is persistable; after the market period ends
an outcome record is appended. Prediction rows are NEVER overwritten — an
outcome lives in a separate table keyed by prediction_id, and a second outcome
for the same prediction is refused.

Storage reuses the existing DROID PostgreSQL/Supabase infrastructure via raw
SQL (same pattern as `app.signals.signals_persistence`). When no database is
configured, or the copilot tables have not been migrated yet, the store
degrades to an in-memory ring buffer so analyses are never lost and tests stay
hermetic. Nothing here fabricates metrics: aggregates are computed from stored
rows only.
"""
from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from typing import Any

import structlog

from app.copilot.models import CopilotAuditRecord

logger = structlog.get_logger()

_MEMORY_MAX = 200


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dump(payload: Any) -> str:
    try:
        return json.dumps(payload, default=str)
    except Exception:
        return "{}"


def _load(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return raw


class CopilotAuditStore:
    """Persist copilot predictions + append-only outcomes."""

    def __init__(self, max_memory: int = _MEMORY_MAX) -> None:
        self._memory: deque[CopilotAuditRecord] = deque(maxlen=max_memory)

    # ------------------------------------------------------------------ #
    async def _factory(self):  # type: ignore[no-untyped-def]
        try:
            from app.core.database import get_async_session_factory

            return get_async_session_factory()
        except Exception:
            return None

    async def _exec(self, sql: str, params: dict | None = None):  # type: ignore[no-untyped-def]
        """Execute copilot SQL; returns rows for SELECT, None otherwise.

        Returns the sentinel "NO_DB" when persistence is unavailable so callers
        can degrade cleanly instead of raising.
        """
        factory = await self._factory()
        if factory is None:
            return "NO_DB"
        try:
            from sqlalchemy import text as _text

            async with factory() as session:
                result = await session.execute(_text(sql), params or {})
                rows = result.fetchall() if result.returns_rows else None
                await session.commit()
                return rows
        except Exception as exc:  # missing tables / offline DB → degrade
            logger.info("copilot_audit_db_degraded", error=str(exc)[:200])
            return "NO_DB"


    # ------------------------------------------------------------------ #
    async def record_prediction(self, record: CopilotAuditRecord) -> dict:
        """Persist one prediction. Returns {stored, backend, prediction_id}."""
        self._memory.appendleft(record)
        stored = await self._exec(
            """
            INSERT INTO copilot_prediction
                (prediction_id, analysis_id, created_at, symbol, horizon, intent,
                 market_context, feature_snapshot, prediction, scenarios, probabilities,
                 levels, confidence, model_version, prompt_version, copilot_version)
            VALUES
                (:prediction_id, :analysis_id, :created_at, :symbol, :horizon, :intent,
                 CAST(:market_context AS JSONB), CAST(:feature_snapshot AS JSONB),
                 CAST(:prediction AS JSONB), CAST(:scenarios AS JSONB),
                 CAST(:probabilities AS JSONB), CAST(:levels AS JSONB),
                 CAST(:confidence AS JSONB), :model_version, :prompt_version, :copilot_version)
            ON CONFLICT (prediction_id) DO NOTHING
            """,
            {
                "prediction_id": record.prediction_id,
                "analysis_id": record.analysis_id,
                "created_at": record.timestamp,
                "symbol": record.symbol,
                "horizon": record.horizon,
                "intent": record.intent,
                "market_context": _dump(record.market_context),
                "feature_snapshot": _dump(record.feature_snapshot),
                "prediction": _dump(record.prediction),
                "scenarios": _dump(record.scenarios),
                "probabilities": _dump(record.probabilities),
                "levels": _dump(record.levels),
                "confidence": _dump(record.confidence),
                "model_version": record.model_version,
                "prompt_version": record.prompt_version,
                "copilot_version": record.copilot_version,
            },
        )
        return {
            "stored": True,
            "backend": "postgres" if stored != "NO_DB" else "memory",
            "prediction_id": record.prediction_id,
        }


    async def record_outcome(
        self,
        prediction_id: str,
        outcome: str,
        realized_return_pct: float | None = None,
        realized_direction: str | None = None,
        level_result: str | None = None,
        notes: str | None = None,
    ) -> dict:
        """Append an outcome. Never overwrites prediction rows; second outcome refused."""
        for record in list(self._memory):
            if record.prediction_id == prediction_id and record.outcome is None:
                record.outcome = outcome
                record.error_metrics = self._error_metrics(record, realized_return_pct, realized_direction)

        result = await self._exec(
            """
            INSERT INTO copilot_prediction_outcome
                (prediction_id, outcome, realized_return_pct, realized_direction,
                 level_result, notes, evaluated_at)
            VALUES
                (:prediction_id, :outcome, :realized_return_pct, :realized_direction,
                 :level_result, :notes, :evaluated_at)
            ON CONFLICT (prediction_id) DO NOTHING
            RETURNING prediction_id
            """,
            {
                "prediction_id": prediction_id,
                "outcome": outcome,
                "realized_return_pct": realized_return_pct,
                "realized_direction": realized_direction,
                "level_result": level_result,
                "notes": notes,
                "evaluated_at": _utcnow(),
            },
        )
        if result == "NO_DB":
            for record in list(self._memory):
                if record.prediction_id == prediction_id:
                    return {"stored": True, "backend": "memory", "duplicate": False}
            return {"stored": False, "backend": "memory", "duplicate": False, "missing": True}
        return {"stored": True, "backend": "postgres", "duplicate": not bool(result)}


    # ------------------------------------------------------------------ #
    async def get_prediction(self, prediction_id: str) -> dict | None:
        rows = await self._exec(
            "SELECT * FROM copilot_prediction WHERE prediction_id = :prediction_id",
            {"prediction_id": prediction_id},
        )
        if rows == "NO_DB":
            for record in list(self._memory):
                if record.prediction_id == prediction_id:
                    return record.model_dump(mode="json")
            return None
        if not rows:
            return None
        first = rows[0]
        mapping = first._mapping if hasattr(first, "_mapping") else dict(first)
        return self._row_to_dict(mapping)

    async def list_predictions(
        self, symbol: str | None = None, horizon: str | None = None, limit: int = 50
    ) -> list[dict]:
        rows = await self._exec(
            """
            SELECT * FROM copilot_prediction
            WHERE (:symbol IS NULL OR symbol = :symbol)
              AND (:horizon IS NULL OR horizon = :horizon)
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            {"symbol": symbol, "horizon": horizon, "limit": max(1, min(limit, 200))},
        )
        if rows == "NO_DB":
            items = list(self._memory)
            if symbol:
                items = [r for r in items if r.symbol == symbol]
            if horizon:
                items = [r for r in items if r.horizon == horizon]
            return [r.model_dump(mode="json") for r in items[:limit]]
        out: list[dict] = []
        for row in rows or []:
            mapping = row._mapping if hasattr(row, "_mapping") else dict(row)
            out.append(self._row_to_dict(mapping))
        return out

    @staticmethod
    def _error_metrics(
        record: CopilotAuditRecord, realized_return_pct: float | None, realized_direction: str | None
    ) -> dict | None:
        metrics: dict = {}
        expected_range = (record.prediction or {}).get("expected_range") or {}
        low, high = expected_range.get("low"), expected_range.get("high")
        if realized_return_pct is not None and isinstance(low, (int, float)) and isinstance(high, (int, float)):
            metrics["range_covered"] = bool(low <= realized_return_pct <= high)
        predicted_direction = (record.prediction or {}).get("direction")
        if realized_direction and predicted_direction:
            metrics["direction_hit"] = realized_direction == predicted_direction
        predicted_probs = record.probabilities or {}
        if realized_direction and any(isinstance(v, (int, float)) for v in predicted_probs.values()):
            targets = {"BULL": "BULL", "BEAR": "BEAR", "NEUTRAL": "NEUTRAL"}
            if realized_direction in targets:
                vector = [predicted_probs.get("BEAR") or 0.0, predicted_probs.get("NEUTRAL") or 0.0, predicted_probs.get("BULL") or 0.0]
                one_hot = [1.0 if realized_direction == label else 0.0 for label in ("BEAR", "NEUTRAL", "BULL")]
                try:
                    brier = sum((p - o) ** 2 for p, o in zip(vector, one_hot)) / 3.0
                    metrics["brier_score"] = round(brier, 6)
                    metrics["predicted_probability_of_outcome"] = float(predicted_probs.get(realized_direction) or 0.0)
                except Exception:
                    pass
        return metrics or None

    @staticmethod
    def _row_to_dict(mapping: Any) -> dict:
        get = mapping.get if hasattr(mapping, "get") else (lambda k, d=None: mapping[k] if k in mapping else d)
        return {
            "prediction_id": get("prediction_id"),
            "analysis_id": get("analysis_id"),
            "timestamp": str(get("created_at")),
            "symbol": get("symbol"),
            "horizon": get("horizon"),
            "intent": get("intent"),
            "market_context": _load(get("market_context")),
            "feature_snapshot": _load(get("feature_snapshot")),
            "prediction": _load(get("prediction")),
            "scenarios": _load(get("scenarios")),
            "probabilities": _load(get("probabilities")),
            "levels": _load(get("levels")),
            "confidence": _load(get("confidence")),
            "model_version": get("model_version"),
            "prompt_version": get("prompt_version"),
            "copilot_version": get("copilot_version"),
        }

    async def evaluation_summary(
        self, symbol: str | None = None, horizon: str | None = None, window_days: int = 30
    ) -> dict:
        """Aggregate measured metrics from stored rows only.

        No metric is reported without a sample size; no sample → available False.
        """
        rows = await self._exec(
            """
            SELECT p.prediction AS prediction, o.realized_direction AS realized_direction,
                   o.realized_return_pct AS realized_return_pct
            FROM copilot_prediction_outcome o
            JOIN copilot_prediction p ON p.prediction_id = o.prediction_id
            WHERE (:symbol IS NULL OR p.symbol = :symbol)
              AND (:horizon IS NULL OR p.horizon = :horizon)
            ORDER BY o.evaluated_at DESC
            LIMIT 2000
            """,
            {"symbol": symbol, "horizon": horizon},
        )
        if rows == "NO_DB" or not rows:
            memory = [r for r in list(self._memory) if r.outcome]
            if symbol:
                memory = [r for r in memory if r.symbol == symbol]
            if horizon:
                memory = [r for r in memory if r.horizon == horizon]
            return self._aggregate(symbol, horizon, window_days, memory_rows=memory)
        db_rows = []
        for row in rows:
            mapping = row._mapping if hasattr(row, "_mapping") else dict(row)
            prediction = _load(mapping.get("prediction")) or {}
            db_rows.append(
                {
                    "predicted_direction": (prediction or {}).get("direction"),
                    "expected_range": (prediction or {}).get("expected_range"),
                    "probabilities": (prediction or {}).get("probabilities"),
                    "realized_direction": mapping.get("realized_direction"),
                    "realized_return_pct": mapping.get("realized_return_pct"),
                }
            )
        return self._aggregate(symbol, horizon, window_days, db_rows=db_rows)

    @staticmethod
    def _aggregate(
        symbol: str | None,
        horizon: str | None,
        window_days: int,
        memory_rows: list | None = None,
        db_rows: list | None = None,
    ) -> dict:
        sample = 0
        direction_hits = 0
        direction_total = 0
        range_hits = 0
        range_total = 0
        brier_values: list[float] = []

        def _acc(predicted_dir: Any, realized_dir: Any, realized_ret: Any, expected: Any, probs: Any) -> None:
            nonlocal direction_hits, direction_total, range_hits, range_total
            if realized_dir and predicted_dir:
                direction_total += 1
                if realized_dir == predicted_dir:
                    direction_hits += 1
            if realized_ret is not None and isinstance(expected, dict):
                low, high = expected.get("low"), expected.get("high")
                if isinstance(low, (int, float)) and isinstance(high, (int, float)):
                    range_total += 1
                    if low <= realized_ret <= high:
                        range_hits += 1
            if realized_dir and isinstance(probs, dict):
                vector = [probs.get("BEAR") or 0.0, probs.get("NEUTRAL") or 0.0, probs.get("BULL") or 0.0]
                if any(isinstance(v, (int, float)) for v in vector):
                    one_hot = [1.0 if realized_dir == label else 0.0 for label in ("BEAR", "NEUTRAL", "BULL")]
                    brier_values.append(sum((p - o) ** 2 for p, o in zip(vector, one_hot)) / 3.0)

        for row in db_rows or []:
            sample += 1
            _acc(
                row.get("predicted_direction"),
                row.get("realized_direction"),
                row.get("realized_return_pct"),
                row.get("expected_range"),
                row.get("probabilities"),
            )
        for record in memory_rows or []:
            sample += 1
            realized = record.error_metrics or {}
            if "direction_hit" in realized:
                direction_total += 1
                if realized["direction_hit"]:
                    direction_hits += 1
            if "range_covered" in realized:
                range_total += 1
                if realized["range_covered"]:
                    range_hits += 1
            if "brier_score" in realized:
                brier_values.append(float(realized["brier_score"]))

        return {
            "available": sample > 0,
            "window_days": window_days,
            "symbol": symbol,
            "horizon": horizon,
            "sample_size": sample,
            "directional_hit_rate": round(direction_hits / direction_total, 4) if direction_total else None,
            "directional_sample": direction_total,
            "range_coverage": round(range_hits / range_total, 4) if range_total else None,
            "range_sample": range_total,
            "brier_score": round(sum(brier_values) / len(brier_values), 6) if brier_values else None,
            "brier_sample": len(brier_values),
        }


copilot_audit_store = CopilotAuditStore()
