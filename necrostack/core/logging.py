"""Structured JSON logging for NecroStack."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

# Dynamically derive standard LogRecord attributes at module import time
# This ensures future Python additions (like taskName) are automatically handled
_STANDARD_LOGRECORD_KEYS: frozenset[str] = frozenset(
    logging.LogRecord(
        name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
    ).__dict__.keys()
)


class JSONFormatter(logging.Formatter):
    """JSON formatter with UTC ISO8601 timestamps."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Add standard NecroStack fields if present
        for field in ("event_id", "event_type", "organ", "emitted"):
            if hasattr(record, field):
                log_data[field] = getattr(record, field)

        # Add any extra fields passed via extra={}
        for key, value in vars(record).items():
            if key not in _STANDARD_LOGRECORD_KEYS and key not in log_data:
                log_data[key] = value

        try:
            return json.dumps(log_data, default=str)
        except Exception:
            # Fallback to safe string representation if serialization fails
            return str(log_data)


def _setup_json_handler(logger: logging.Logger, level: int) -> None:
    """Configure a logger with JSON formatting.

    Args:
        logger: The logger to configure.
        level: The logging level to set.
    """
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


def configure_spine_logger(level: int = logging.INFO) -> logging.Logger:
    """Configure and return the default Spine logger with JSON formatting.

    Args:
        level: The logging level to set. Defaults to logging.INFO.
    """
    logger = logging.getLogger("necrostack.spine")
    _setup_json_handler(logger, level)
    return logger


def get_logger(name: str = "necrostack", level: int = logging.INFO) -> logging.Logger:
    """Get a logger with JSON formatting.

    Args:
        name: The logger name. Defaults to "necrostack".
        level: The logging level to set. Defaults to logging.INFO.
    """
    logger = logging.getLogger(name)
    _setup_json_handler(logger, level)
    return logger
