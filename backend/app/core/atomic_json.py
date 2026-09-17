"""Shared atomic JSON persistence primitives.

Single implementation for the "write temp file, flush, os.replace" pattern
used by state/ledger/cache persistence across the backend. Consolidates the
previously divergent behaviors:

- unique per-attempt temp file (no cross-writer collisions),
- ``os.replace`` atomic swap (works whether or not the target exists),
- configurable ``indent`` / ``default`` / ``ensure_ascii`` / ``sort_keys``,
- ``PermissionError`` retries with a small backoff (Windows sharing
  violations on replace),
- stale ``<stem>.*.tmp`` cleanup for crashed writers,
- structured logging on the final failure; callers get ``bool`` instead of
  an exception so best-effort persistence stays non-fatal.

Writes never raise for ordinary failures: they log and return ``False``.
Callers that must surface an error can check the return value.
"""
from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

__all__ = ["atomic_write_json", "read_json"]

_DEFAULT_ERROR_CHARS = 200


def _log_failure(
    log_event: str,
    log_level: str,
    target: Path,
    error: BaseException,
    max_error_chars: int | None,
    attempts: int,
) -> None:
    err = str(error)
    if max_error_chars is not None:
        err = err[:max_error_chars]
    log = getattr(logger, log_level, None) or logger.warning
    log(log_event, path=str(target), error=err, attempts=attempts)


def _cleanup_stale_tmp(target: Path, max_age_seconds: float) -> None:
    """Best-effort removal of tmp files left by crashed writers."""
    try:
        now = time.time()
        for stale in target.parent.glob(f"{target.stem}.*.tmp"):
            try:
                if (now - stale.stat().st_mtime) > max_age_seconds:
                    stale.unlink()
            except Exception as e:
                logger.debug(
                    "atomic_json_stale_tmp_cleanup_failed",
                    path=str(stale),
                    error=str(e)[:150],
                )
    except Exception as e:
        logger.debug("atomic_json_stale_tmp_cleanup_glob_failed", error=str(e)[:150])


def atomic_write_json(
    path: str | Path,
    payload: Any,
    *,
    indent: int | None = None,
    default: Callable[[Any], Any] | None = str,
    ensure_ascii: bool = True,
    sort_keys: bool = False,
    retries: int = 2,
    retry_delay: float = 0.05,
    stale_tmp_seconds: float = 60.0,
    cleanup_stale: bool = True,
    create_parents: bool = False,
    log_event: str = "atomic_json_write_failed",
    log_level: str = "warning",
    max_error_chars: int | None = _DEFAULT_ERROR_CHARS,
) -> bool:
    """Atomically serialize ``payload`` to ``path`` as UTF-8 JSON.

    Returns ``True`` on success. On failure logs ``log_event`` at
    ``log_level`` (with ``path``/``error``/``attempts``) and returns
    ``False``; the target file is left untouched (last good copy wins).
    """
    target = Path(path)
    written = False
    attempts = 0
    last_error: BaseException | None = None
    try:
        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(retries + 1):
            attempts = attempt + 1
            tmp = target.with_name(f"{target.stem}.{os.getpid()}.{time.time_ns()}.tmp")
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(
                        payload,
                        f,
                        indent=indent,
                        default=default,
                        ensure_ascii=ensure_ascii,
                        sort_keys=sort_keys,
                    )
                os.replace(tmp, target)
                written = True
                break
            except PermissionError as e:
                last_error = e
                if attempt < retries:
                    time.sleep(retry_delay * (2 ** attempt))
            except Exception as e:
                last_error = e
                break
    except Exception as e:
        last_error = e

    if not written:
        if last_error is not None:
            _log_failure(
                log_event,
                log_level,
                target,
                last_error,
                max_error_chars,
                attempts,
            )
        return False

    if cleanup_stale:
        _cleanup_stale_tmp(target, stale_tmp_seconds)
    return True


def read_json(
    path: str | Path,
    *,
    default: Any = None,
    log_event: str = "atomic_json_read_failed",
    log_level: str = "debug",
    max_error_chars: int | None = _DEFAULT_ERROR_CHARS,
) -> Any:
    """Best-effort JSON read.

    Returns the decoded value, or ``default`` when the file is missing or
    unreadable/corrupt (missing files never log; corrupt files log at
    ``log_level``). Never raises for ordinary I/O/parse failures.
    """
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception as e:
        err = str(e)
        if max_error_chars is not None:
            err = err[:max_error_chars]
        log = getattr(logger, log_level, None) or logger.debug
        log(log_event, path=str(path), error=err)
        return default
