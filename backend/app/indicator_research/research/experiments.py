"""Experiment persistence and export (§7 of the workflow, Phase 7).

An experiment is the whole research configuration plus the result summary that
came out of it — instrument, timeframe, date range, indicator specs and
parameters, both rule sets, execution and cost settings, the metric block and
the validation report. Storing the summary rather than the full trade list keeps
files small and makes a saved experiment a statement of *what was tested*; the
trade detail can always be regenerated because the configuration is complete.

Writes go through the shared atomic JSON writer, so a crash mid-save cannot
leave a half-written experiment that fails to parse on the next read.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import structlog

from app.core.atomic_json import atomic_write_json, read_json

logger = structlog.get_logger(__name__)

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

#: Metric columns exported to CSV, in a stable order.
_EXPORT_METRIC_KEYS: tuple[str, ...] = (
    "n_trades",
    "win_rate_pct",
    "net_profit",
    "total_return_pct",
    "profit_factor",
    "expectancy_per_trade",
    "payoff_ratio",
    "avg_win",
    "avg_loss",
    "max_drawdown_pct",
    "max_drawdown_duration_bars",
    "sharpe_annualized",
    "sortino_annualized",
    "annualized_return_pct",
    "total_costs",
    "cost_drag_pct",
    "exposure_pct",
    "avg_bars_held",
    "avg_mae_pct",
    "avg_mfe_pct",
    "long_trades",
    "short_trades",
)


def experiments_dir() -> Path:
    """Directory holding saved experiments.

    Follows the repository convention of ``<data root>/experiments/<module>``
    next to the historical store, and is overridable for tests and deployments.
    """
    override = os.getenv("INDICATOR_RESEARCH_EXPERIMENTS_DIR")
    if override:
        path = Path(override)
    else:
        try:
            from app.historical_data.storage.paths import resolve_historical_data_dir

            path = resolve_historical_data_dir().parent / "experiments" / "indicator_research"
        except Exception:  # pragma: no cover - path module always importable in app
            path = Path.cwd() / "data" / "experiments" / "indicator_research"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path_for(experiment_id: str) -> Path:
    if not _SAFE_ID.match(experiment_id):
        raise ValueError(
            "Experiment id must be 1-64 characters of letters, digits, hyphen or "
            "underscore."
        )
    return experiments_dir() / f"{experiment_id}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_experiment(
    payload: Mapping[str, Any],
    *,
    experiment_id: str | None = None,
    name: str | None = None,
    notes: str | None = None,
    tags: Sequence[str] | None = None,
    result_summary: Mapping[str, Any] | None = None,
    validation: Mapping[str, Any] | None = None,
    data_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist one experiment configuration and its summary."""
    config = dict(payload or {})
    if not config:
        raise ValueError("An experiment needs a configuration to save.")

    identifier = experiment_id or f"exp_{uuid.uuid4().hex[:12]}"
    path = _path_for(identifier)
    existing_raw = read_json(path, default=None)
    existing: dict[str, Any] = existing_raw if isinstance(existing_raw, dict) else {}
    created_at = existing.get("created_at") or _now()

    record = {
        "id": identifier,
        "name": name if name is not None else existing.get("name"),
        "notes": notes if notes is not None else existing.get("notes"),
        "tags": list(tags) if tags is not None else list(existing.get("tags") or []),
        "config": config,
        "result_summary": dict(result_summary or {}),
        "validation": dict(validation or {}),
        "data_provenance": dict(data_provenance or {}),
        "created_at": created_at,
        "updated_at": _now(),
        "schema_version": 1,
    }
    if not record["name"]:
        record["name"] = _suggest_name(config)

    if not atomic_write_json(path, record, indent=2, create_parents=True):
        raise RuntimeError(f"Failed to write experiment '{identifier}' to disk")
    logger.info("indicator_research_experiment_saved", experiment_id=identifier)
    return summarize_record(record)


def _suggest_name(config: Mapping[str, Any]) -> str:
    specs = config.get("indicators") or []
    first = specs[0] if isinstance(specs, list) and specs else {}
    indicator_id = (first or {}).get("indicator_id", "indicator") if isinstance(first, dict) else "indicator"
    instrument = config.get("instrument", "?")
    timeframe = config.get("timeframe", "?")
    return f"{instrument} {timeframe} {indicator_id}"


def _load_record(experiment_id: str) -> dict[str, Any] | None:
    try:
        path = _path_for(experiment_id)
    except ValueError:
        return None
    data = read_json(path, default=None)
    return data if isinstance(data, dict) else None


def get_experiment(experiment_id: str) -> dict[str, Any] | None:
    """Full stored record, or ``None`` when it does not exist."""
    return _load_record(experiment_id)


def summarize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Compact view for list endpoints (no full config)."""
    config = record.get("config") or {}
    specs = config.get("indicators") or []
    first = specs[0] if isinstance(specs, list) and specs else {}
    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "notes": record.get("notes"),
        "tags": list(record.get("tags") or []),
        "instrument": config.get("instrument"),
        "timeframe": config.get("timeframe"),
        "date_range": config.get("date_range"),
        "indicator_id": (first or {}).get("indicator_id") if isinstance(first, dict) else None,
        "indicator_params": (first or {}).get("params") if isinstance(first, dict) else None,
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "result_summary": record.get("result_summary") or {},
        "validation": record.get("validation") or {},
    }


def list_experiments(limit: int = 100) -> list[dict[str, Any]]:
    """Saved experiments, newest first."""
    records: list[dict[str, Any]] = []
    for path in experiments_dir().glob("*.json"):
        data = read_json(path, default=None)
        if isinstance(data, dict) and data.get("id"):
            records.append(data)
    records.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
    return [summarize_record(r) for r in records[: max(1, limit)]]


def delete_experiment(experiment_id: str) -> bool:
    try:
        path = _path_for(experiment_id)
    except ValueError:
        return False
    try:
        path.unlink()
        logger.info("indicator_research_experiment_deleted", experiment_id=experiment_id)
        return True
    except FileNotFoundError:
        return False


def rename_experiment(experiment_id: str, name: str | None, notes: str | None) -> dict[str, Any]:
    record = _load_record(experiment_id)
    if record is None:
        raise ValueError(f"Experiment '{experiment_id}' was not found")
    if name is not None:
        record["name"] = name
    if notes is not None:
        record["notes"] = notes
    record["updated_at"] = _now()
    if not atomic_write_json(_path_for(experiment_id), record, indent=2):
        raise RuntimeError("Failed to update the experiment")
    return summarize_record(record)


def export_experiment(experiment_id: str, fmt: str = "json") -> tuple[bytes, str, str]:
    """Export one experiment as JSON or a single-row metrics CSV.

    Returns ``(content, media_type, filename)``.
    """
    record = _load_record(experiment_id)
    if record is None:
        raise ValueError(f"Experiment '{experiment_id}' was not found")

    if fmt.lower() == "csv":
        # Two sections: the configuration that produced the numbers, then the
        # numbers. An exported metric without its configuration is unreadable a
        # week later, so the config is never dropped to save columns.
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        config = record.get("config") or {}
        rules = config.get("rules") or {}
        validation = record.get("validation") or {}
        metrics = record.get("result_summary") or {}

        writer.writerow(["section", "key", "value"])
        writer.writerow(["experiment", "id", record.get("id")])
        writer.writerow(["experiment", "name", record.get("name")])
        writer.writerow(["experiment", "created_at", record.get("created_at")])
        writer.writerow(["experiment", "updated_at", record.get("updated_at")])
        writer.writerow(["data", "instrument", config.get("instrument")])
        writer.writerow(["data", "timeframe", config.get("timeframe")])
        writer.writerow(["data", "date_range", json.dumps(config.get("date_range") or {}, separators=(",", ":"))])
        writer.writerow(["data", "indicators", json.dumps(config.get("indicators") or [], separators=(",", ":"))])
        writer.writerow(["signal", "long", json.dumps(rules.get("long"), separators=(",", ":"))])
        writer.writerow(["signal", "short", json.dumps(rules.get("short"), separators=(",", ":"))])
        writer.writerow(["execution", "settings", json.dumps(config.get("settings") or {}, separators=(",", ":"))])
        writer.writerow(["validation", "badge", validation.get("badge")])
        writer.writerow(["validation", "no_lookahead", validation.get("no_lookahead")])
        writer.writerow(["validation", "repaint_free", validation.get("repaint_free")])
        writer.writerow(["validation", "scope", validation.get("scope")])
        for key in _EXPORT_METRIC_KEYS:
            if key in metrics:
                writer.writerow(["metric", key, metrics[key]])
        return (
            buffer.getvalue().encode("utf-8"),
            "text/csv",
            f"{experiment_id}.csv",
        )

    content = json.dumps(record, indent=2, default=str).encode("utf-8")
    return content, "application/json", f"{experiment_id}.json"


__all__ = [
    "delete_experiment",
    "experiments_dir",
    "export_experiment",
    "get_experiment",
    "list_experiments",
    "rename_experiment",
    "save_experiment",
    "summarize_record",
]
