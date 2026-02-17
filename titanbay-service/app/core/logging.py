"""
Production-grade logging configuration.

Implements industry-standard practices:
- **Rotating file handler** — ``RotatingFileHandler`` with configurable max size
  and backup count, preventing log files from consuming all disk space.
- **JSON structured logging** — Machine-parsable JSON log lines for log
  aggregation platforms (ELK, Datadog, Splunk, CloudWatch).
- **Console handler** — Human-readable coloured output for local development.
- **Debug toggle** — ``DEBUG=true`` env var switches all loggers to DEBUG level
  and enables SQL echo, without code changes.
- **Request-ID correlation** — Logs include the request ID from middleware
  context for distributed tracing.

Usage:
    Call ``setup_logging()`` once during application startup (in ``main.py``).
    All modules that call ``logging.getLogger(__name__)`` will automatically
    inherit the configured handlers and formatters.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

from app.core.config import settings

# ── Log directory — created relative to the project root ──
LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs"
)


class JSONFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.

    Structured logging is the industry standard for production services because:
    - Log aggregation platforms (ELK, Datadog, Splunk) can parse fields automatically.
    - Queries like ``level:ERROR AND service:titanbay`` become trivial.
    - Stack traces are embedded in the JSON ``exception`` field, not spread
      across multiple lines that break log parsers.

    Output example::

        {"timestamp": "2025-02-17T10:30:00.123Z", "level": "INFO",
         "logger": "app.services.fund_service", "message": "Created fund ...",
         "module": "fund_service", "function": "create_fund", "line": 42}
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include request_id if present (set by middleware)
        request_id = getattr(record, "request_id", None)
        if request_id:
            log_entry["request_id"] = request_id

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include any extra fields
        for key in ("status_code", "method", "path", "elapsed_ms", "client_ip"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, default=str)


class ConsoleFormatter(logging.Formatter):
    """
    Human-readable formatter for terminal output during local development.

    Uses colour codes (ANSI) to highlight log levels for quick visual scanning.
    """

    COLOURS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self.COLOURS.get(record.levelname, self.RESET)
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # Include request_id if available
        request_id = getattr(record, "request_id", None)
        rid_str = f" [{request_id[:8]}]" if request_id else ""

        base = (
            f"{timestamp} | {colour}{record.levelname:<8}{self.RESET} | "
            f"{record.name}{rid_str} | {record.getMessage()}"
        )
        if record.exc_info and record.exc_info[0] is not None:
            base += "\n" + self.formatException(record.exc_info)
        return base


def setup_logging() -> None:
    """
    Configure the root logger with console + rotating file handlers.

    Call once during application startup. Subsequent calls are idempotent
    (handlers are checked before adding).

    Configuration (via environment variables / ``Settings``):
    - ``DEBUG=true`` → All loggers set to DEBUG, SQL echo enabled.
    - ``LOG_LEVEL`` → Override the root log level (default: INFO).
    - ``LOG_FILE_MAX_BYTES`` → Max size per log file before rotation (default: 10 MB).
    - ``LOG_FILE_BACKUP_COUNT`` → Number of rotated files to keep (default: 5).
    """
    root_logger = logging.getLogger()

    # Prevent duplicate handlers on repeated calls
    if root_logger.handlers:
        return

    level = (
        logging.DEBUG
        if settings.DEBUG
        else getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    )
    root_logger.setLevel(level)

    # ── Console handler (human-readable) ──
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(ConsoleFormatter())
    root_logger.addHandler(console_handler)

    # ── Rotating file handler (JSON structured) ──
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        filename=os.path.join(LOG_DIR, "titanbay.log"),
        maxBytes=settings.LOG_FILE_MAX_BYTES,
        backupCount=settings.LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(file_handler)

    # ── Error-only file (separate stream for alerting/monitoring) ──
    error_handler = RotatingFileHandler(
        filename=os.path.join(LOG_DIR, "titanbay-error.log"),
        maxBytes=settings.LOG_FILE_MAX_BYTES,
        backupCount=settings.LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(error_handler)

    # ── Suppress noisy third-party loggers ──
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.DEBUG else logging.WARNING
    )

    root_logger.info(
        "Logging initialized — level=%s, file=%s, max_size=%s MB, backups=%d",
        logging.getLevelName(level),
        os.path.join(LOG_DIR, "titanbay.log"),
        settings.LOG_FILE_MAX_BYTES // (1024 * 1024),
        settings.LOG_FILE_BACKUP_COUNT,
    )
