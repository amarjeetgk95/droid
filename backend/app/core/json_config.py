"""Canonical JSON config loader for backend config files.

Before this module, every consumer re-implemented its own path search over
``config/<name>.json`` with different (and sometimes contradictory) failure
semantics: ``signals/confluence.py`` fail-closed at import, ``algo/signal_fusion.py``
silently fell back to inline defaults, and the risk/event services each had
their own search order and fallback dict. This module is the single search,
single cache, and single explicit failure policy:

- ``required=True``  -> fail closed: raise :class:`JSONConfigError` (a
  ``RuntimeError``) naming the config, the searched candidates, and the last
  read error.
- ``required=False`` -> fail open: log ``json_config_fallback_default`` at
  warning level (never silently), then return ``default``.

Search order (first existing, readable JSON object wins):

1. ``<backend>/config/<name>``  -- module-relative; ``backend`` is the package
   root. This is the historical ``Path(__file__).resolve().parents[2]`` path.
2. ``<repo>/config/<name>``     -- module-relative repo root (deployment-level
   override used by the event engine).
3. ``backend/config/<name>``    -- cwd-relative (process started at repo root).
4. ``config/<name>``            -- cwd-relative (process started in ``backend/``).

``search_paths`` accepts explicit file paths (``config_file``/``config_path``
constructor overrides); an entry pointing at an existing directory has ``name``
appended. Explicit paths are tried before the canonical locations, preserving
the old "caller override first, standard locations second" behavior.

Reads are cached per resolved path. Every successful return is a deep copy, so
callers may mutate the returned mapping without poisoning the cache or each
other. Missing files are never cached; ``cache=False`` re-reads every call.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

__all__ = [
    "DEFAULT_SEARCH_DIRS",
    "JSONConfigError",
    "clear_json_config_cache",
    "load_json_config",
]

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_SEARCH_DIRS: tuple[Path, ...] = (
    _BACKEND_ROOT / "config",
    _REPO_ROOT / "config",
    Path("backend") / "config",
    Path("config"),
)

_CACHE: dict[Path, dict[str, Any]] = {}

_MAX_ERROR_CHARS = 200


class JSONConfigError(RuntimeError):
    """Raised by ``load_json_config(..., required=True)`` on a missing/invalid config."""


def clear_json_config_cache() -> None:
    """Drop every cached payload (tests, or an intentional config reload)."""
    _CACHE.clear()


def _candidate_paths(name: str, search_paths: Sequence[str | Path] | None) -> list[Path]:
    candidates: list[Path] = []
    for entry in search_paths or ():
        p = Path(entry)
        candidates.append(p / name if p.is_dir() else p)
    candidates.extend(directory / name for directory in DEFAULT_SEARCH_DIRS)
    return candidates


def _fail_or_default(
    name: str,
    searched: list[Path],
    reason: str,
    default: Any,
    required: bool,
) -> Any:
    searched_str = [str(p) for p in searched]
    if required:
        logger.error(
            "json_config_required_missing",
            name=name,
            searched=searched_str,
            reason=reason,
        )
        raise JSONConfigError(
            f"{name}: no readable JSON config found and required=True "
            f"(searched: {searched_str}; last error: {reason})"
        )
    logger.warning(
        "json_config_fallback_default",
        name=name,
        searched=searched_str,
        reason=reason,
        fallback="default",
    )
    return copy.deepcopy(default)


def load_json_config(
    name: str,
    *,
    required: bool = False,
    search_paths: Sequence[str | Path] | None = None,
    default: Any = None,
    cache: bool = True,
) -> Any:
    """Load ``name`` from the canonical config locations.

    Returns the parsed JSON object. On missing/unreadable/invalid config:
    raises :class:`JSONConfigError` when ``required`` is True, otherwise logs a
    warning and returns a deep copy of ``default``. Successful reads are cached
    by resolved path and always returned as deep copies.
    """
    candidates = _candidate_paths(name, search_paths)
    last_error: str | None = None

    for path in candidates:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path

        if cache:
            cached = _CACHE.get(resolved)
            if cached is not None:
                logger.debug("json_config_cache_hit", name=name, path=str(resolved))
                return copy.deepcopy(cached)

        if not path.is_file():
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            last_error = str(e)[:_MAX_ERROR_CHARS]
            logger.warning(
                "json_config_read_error",
                name=name,
                path=str(path),
                error=last_error,
            )
            continue

        if not isinstance(data, dict):
            last_error = f"root is {type(data).__name__}, expected object"
            logger.warning(
                "json_config_invalid_root",
                name=name,
                path=str(path),
                root_type=type(data).__name__,
            )
            continue

        if cache:
            _CACHE[resolved] = data
        logger.info("json_config_loaded", name=name, path=str(resolved), cache_enabled=bool(cache))
        return copy.deepcopy(data)

    return _fail_or_default(
        name,
        candidates,
        last_error or "no candidate file exists",
        default,
        required,
    )
