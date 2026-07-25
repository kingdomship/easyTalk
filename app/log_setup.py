"""Structured JSON logging with daily rotation.

Configures the "emoji-chat" logger with JSON output to both stdout
(visible in docker logs) and memory/logs/app.YYYY-MM-DD.log (persistent
across container restarts).

Usage:
    from app.log_setup import setup_logging, set_log_level
    setup_logging("/path/to/logs")
"""

import json
import logging
import logging.handlers
import os
import sys
import traceback
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects.

    Standard fields: timestamp, level, logger, message
    Injects request_id from app.tracer.get_request_id().
    Handles exc_info via formatException() separately.
    """

    def format(self, record: logging.LogRecord) -> str:
        try:
            from app.tracer import get_request_id

            rid = get_request_id()
        except Exception:
            rid = ""

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": rid,
        }

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Merge structured extra fields (passed via logger.info("msg", extra={"_extra_": {...}}))
        extra = getattr(record, "_extra_", None)
        if isinstance(extra, dict):
            log_entry.update(extra)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


def setup_logging(log_dir: str, level: str = "INFO") -> None:
    """Configure the emoji-chat logger with JSON output.

    - Creates log_dir if it doesn't exist
    - Daily rotation with 30-day retention
    - Only touches the "emoji-chat" logger (preserves root handlers for uvicorn/httpx/APScheduler)

    Args:
        log_dir: Directory for log files (e.g. "/app/memory/logs")
        level: One of DEBUG, INFO, WARNING, ERROR
    """
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("emoji-chat")
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # JSON formatter for both handlers
    fmt = JsonFormatter()

    # File: daily rotation, keep 30 days
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_dir, "app.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    # Stdout: visible in docker logs
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    stream_handler.setLevel(logging.DEBUG)
    logger.addHandler(stream_handler)

    # Don't propagate to root (root already has basicConfig handler)
    logger.propagate = False


def set_log_level(level: str) -> str:
    """Change the emoji-chat logger level at runtime.

    Returns the new level string, uppercased.
    """
    logger = logging.getLogger("emoji-chat")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return level.upper()
