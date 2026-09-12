"""Minimal model registry for 1H Forecast v2.3 (P2-3).

Append-only JSONL at ``backend/app/ml/artifacts/registry.jsonl``. Each line
is one promotion-candidate entry::

    {model_version, dataset_hash, feature_schema, target_spec,
     calibrator_version, git_sha, validation_report_id, decision, timestamp}

Pure file ops only (no DB, no network) so offline validation and unit tests
(with ``tmp_path``) stay fast. FULL-registry hardening (signing, dedupe,
migration) is explicitly deferred.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODEL_DIR = Path(__file__).parent / "artifacts"
MODEL_DIR.mkdir(exist_ok=True)

REGISTRY_PATH = MODEL_DIR / "registry.jsonl"

REQUIRED_KEYS = (
    "model_version",
    "dataset_hash",
    "feature_schema",
    "target_spec",
    "calibrator_version",
    "git_sha",
    "validation_report_id",
    "decision",
    "timestamp",
)


def _default_registry_path(registry_path: Path | str | None) -> Path:
    return Path(registry_path) if registry_path else REGISTRY_PATH


def record_model(entry: dict, registry_path: Path | str | None = None) -> dict:
    """Append one registry entry (JSONL) and return the recorded dict.

    ``entry`` must be a dict; ``timestamp`` (UTC ISO) is added when missing.
    Missing lineage keys default to ``"unknown"``/``None`` rather than
    raising, so callers can record heuristic/unavailable candidates honestly.
    """
    if not isinstance(entry, dict):
        raise ValueError("record_model requires an entry dict")
    path = _default_registry_path(registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    recorded = dict(entry)
    if not recorded.get("timestamp"):
        recorded["timestamp"] = datetime.now(timezone.utc).isoformat()
    for key in REQUIRED_KEYS:
        if key not in recorded:
            recorded[key] = None if key == "validation_report_id" else "unknown"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(recorded) + "\n")
    return recorded


def read_registry(registry_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Read all registry entries (skips blank/corrupt lines)."""
    path = _default_registry_path(registry_path)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out
