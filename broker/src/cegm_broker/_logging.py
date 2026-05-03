"""Structured JSONL logging.

Every log record is one JSON object per line, written to both stderr and a
daily-rotated file under ``%LOCALAPPDATA%\\CEGM\\logs\\``. Stdout is
deliberately untouched — even though our default transport is HTTP, we
preserve the option to switch to MCP stdio later, and stray stdout would
corrupt that.

Usage::

    from cegm_broker._logging import configure_logging, get_logger

    configure_logging("info")
    log = get_logger(__name__)
    log.info("broker.starting", extra={"port": 27077})
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from cegm_broker._paths import daily_log_file, ensure_dir, logs_dir

_RESERVED_RECORD_FIELDS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class _JsonFormatter(logging.Formatter):
    """Format ``LogRecord`` as a single JSON line.

    Keeps the schema minimal (``ts``, ``level``, ``logger``, ``event``) and
    promotes anything passed via ``extra=`` into the top-level object. The
    ``event`` field is the human-meaningful message slug — callers should
    pass dotted lower_snake (e.g. ``broker.tool_called``) so logs can be
    grepped and aggregated easily.
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds")
        # ``isoformat`` on a UTC datetime gives ``+00:00``; canonicalize to ``Z``.
        ts = ts.replace("+00:00", "Z")

        payload: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


def configure_logging(level: str = "info") -> None:
    """Install JSON handlers on the root logger.

    Idempotent: a second call replaces the previously installed handlers.
    """
    log_level = _LEVELS.get(level.lower(), logging.INFO)
    formatter = _JsonFormatter()

    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(log_level)

    ensure_dir(logs_dir())
    file_handler = logging.FileHandler(daily_log_file(), encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(stderr_handler)
    root.addHandler(file_handler)
    root.setLevel(log_level)

    # Quiet uvicorn's noisy default access log; we re-emit relevant traffic
    # through our own structured channel.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper so callers don't import ``logging`` directly."""
    return logging.getLogger(name)
