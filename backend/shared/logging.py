"""Structured logging configuration with structlog.

Environment variables:
- LOG_FORMAT: "json" for production log aggregation, "console" or unset for
  human-readable colored output.
- LOG_LEVEL: "DEBUG", "INFO" (default), "WARNING", "ERROR", or "CRITICAL".
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from collections.abc import MutableMapping
    from typing import Any

LOG_FILE_TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"

_VALID_LOG_FORMATS = {"json", "console", ""}
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _serialize_enums(
    _logger: object,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Replace Enum instances with their .value for readable log output."""
    for key, value in event_dict.items():
        if isinstance(value, Enum):
            event_dict[key] = value.value
        elif isinstance(value, dict):
            event_dict[key] = {k: v.value if isinstance(v, Enum) else v for k, v in value.items()}
    return event_dict


def _is_test() -> bool:
    return "pytest" in sys.modules


def _resolve_json_mode() -> bool:
    value = os.environ.get("LOG_FORMAT", "").lower()
    if value not in _VALID_LOG_FORMATS:
        msg = f"Invalid LOG_FORMAT={value!r}. Must be 'json', 'console', or unset."
        raise ValueError(msg)
    return value == "json"


def _resolve_log_level() -> int:
    """Resolve log level from LOG_LEVEL env var. Defaults to INFO."""
    value = os.environ.get("LOG_LEVEL", "INFO").upper()
    if value not in _VALID_LOG_LEVELS:
        msg = f"Invalid LOG_LEVEL={value!r}. Must be one of {', '.join(sorted(_VALID_LOG_LEVELS))}."
        raise ValueError(msg)
    return getattr(logging, value)


def _build_stdlib_formatter(*, json_mode: bool, colors: bool = False) -> logging.Formatter:
    """Build a stdlib ProcessorFormatter for handler output."""
    if json_mode:
        return structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
        )
    return structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=colors),
        ],
    )


def setup_logging(
    log_dir: Path | str | None = None,
    level: int | None = None,
) -> Path | None:
    """Configure structlog with stdout and optional file output.

    Log level is resolved from the LOG_LEVEL env var (default: INFO).
    When log_dir is provided, creates a datetime-stamped log file
    inside that directory. Returns the log file path if created,
    None otherwise.
    """
    json_mode = _resolve_json_mode()

    if level is None:
        level = _resolve_log_level()

    # Configure structlog pipeline.
    # format_exc_info is intentionally NOT here — it runs in ProcessorFormatter
    # to avoid double-processing tracebacks in file output.
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _serialize_enums,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    # Configure stdlib root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    # Silence noisy HTTP client internals (httpx logs every request,
    # httpcore logs raw TCP send/receive details).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    stdout_formatter = _build_stdlib_formatter(json_mode=json_mode, colors=sys.stdout.isatty())

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(stdout_formatter)
    root_logger.addHandler(stdout_handler)

    if log_dir is not None and not _is_test():
        dir_path = Path(log_dir)
        dir_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(tz=UTC).strftime(LOG_FILE_TIMESTAMP_FORMAT)
        file_path = dir_path / f"{timestamp}.log"
        file_formatter = _build_stdlib_formatter(json_mode=json_mode, colors=False)
        file_handler = logging.FileHandler(file_path)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        return file_path

    return None
