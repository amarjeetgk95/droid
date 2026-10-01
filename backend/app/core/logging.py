import logging
import os
import time
from logging.handlers import RotatingFileHandler

import structlog

from app.core.config import settings

# Rotating application log: <repo-root>/logs/application.log (+ .1 … .10
# rolls). The path is derived from THIS FILE's location, not the process CWD,
# so every launch path (Start-Backend.cmd, a raw uvicorn command run from any
# directory, a test harness) writes to the same logs\ folder — one place to look.
# The CMD launcher's own window output stays in that window; this file survives it.
# Size-capped rotation bounds disk usage for long trading sessions:
# 10 MB x 10 files ≈ 100 MB worst case, then the oldest roll is dropped.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LOG_DIR = os.environ.get("LOG_DIR") or os.path.join(_REPO_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "application.log")
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 10

# uvicorn's own loggers (startup errors, access log) do not propagate to the
# root logger, so they get the rotating file attached via a bridge filter.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

_FILE_HANDLER: RotatingFileHandler | None = None


def _file_handler() -> RotatingFileHandler | None:
    """Create (once) the rotating application-log file handler.

    Returns None when the log directory cannot be created — logging must
    never take the backend down; stdout/stderr (service.out/err.log under
    WinSW) still capture everything.
    """
    global _FILE_HANDLER
    if _FILE_HANDLER is not None:
        return _FILE_HANDLER
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        # structlog emits fully-rendered lines (ISO timestamp included);
        # keep them byte-for-byte identical to the console stream.
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.setLevel(logging.DEBUG)
        _FILE_HANDLER = handler
        return handler
    except Exception:
        return None


class _UvicornFileBridge(logging.Filter):
    """Pre-render stdlib records into a timestamped line for the shared file.

    uvicorn loggers carry no ISO timestamp and no structlog processors, so a
    plain passthrough would lose timestamps in application.log. The filter
    renders the timestamp/level/name INTO the record message for non-access
    records; access log records are left intact because uvicorn's
    AccessLogFormatter unpacks record.args directly and crashes if they are
    cleared. Uses only record-local data — no shared state, thread-safe.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "uvicorn.access":
            return True
        ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z"
        record.msg = f"{ts} {record.levelname} {record.name}: {record.getMessage()}"
        record.args = None
        return True


def setup_logging() -> None:
    """Configure structured logging.

    Console output (stdout/stderr) is unchanged — under WinSW it lands in
    logs/service.out.log / service.err.log via the wrapper. Additionally a
    size-capped rotating logs/application.log captures the same structured
    events plus uvicorn's own startup/access messages, so the application log
    survives independently of the service wrapper.

    Idempotent: the lifespan (and tests) may call this repeatedly; handlers
    are attached at most once per logger.
    """
    # Ensure stdout can handle utf-8 (arrow, minus etc. in prompts) on Windows cp1252
    try:
        import sys

        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if settings.app_env == "development"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = _file_handler()
    if handler is None:
        return

    root = logging.getLogger()
    if handler not in root.handlers:
        root.addHandler(handler)
    if root.level in (logging.NOTSET, logging.WARNING):
        root.setLevel(logging.INFO)

    for name in _UVICORN_LOGGERS:
        ulogger = logging.getLogger(name)
        if handler not in ulogger.handlers:
            ulogger.addFilter(_UvicornFileBridge())
            ulogger.addHandler(handler)
            # The handler is already on the root logger; propagation would
            # write uvicorn records twice (raw at root, bridged here).
            ulogger.propagate = False
            ulogger.setLevel(logging.INFO)
