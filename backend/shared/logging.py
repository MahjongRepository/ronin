"""
Logging configuration for stdout and file output.
"""

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE_TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"


def _is_test() -> bool:
    return "pytest" in sys.modules


def setup_logging(
    log_dir: Path | str | None = None,
    level: int = logging.INFO,
) -> Path | None:
    """
    Configure root logger with stdout and optional file handlers.

    When log_dir is provided, creates a datetime-stamped log file
    inside that directory (e.g. backend/logs/game/2026-01-31_14-30-00.log).
    Returns the log file path if one was created, None otherwise.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # clear existing handlers to avoid duplicates on repeated calls
    root_logger.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)

    if log_dir is not None and not _is_test():
        dir_path = Path(log_dir)
        dir_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(tz=UTC).strftime(LOG_FILE_TIMESTAMP_FORMAT)
        file_path = dir_path / f"{timestamp}.log"
        file_handler = logging.FileHandler(file_path)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        return file_path

    return None


def rotate_log_file(log_dir: Path | str, name: str | None = None) -> Path | None:
    """
    Replace the current file handler with a new log file.

    Closes the old file handler and creates a fresh one in the same directory.
    When name is provided, uses it as the filename (e.g. game_id).
    Otherwise uses a datetime-stamped filename.
    Returns the new log file path, or None during tests.
    """
    if _is_test():
        return None

    root_logger = logging.getLogger()
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # remove existing file handlers
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            handler.close()
            root_logger.removeHandler(handler)

    dir_path = Path(log_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    filename = name if name is not None else datetime.now(tz=UTC).strftime(LOG_FILE_TIMESTAMP_FORMAT)
    file_path = dir_path / f"{filename}.log"
    file_handler = logging.FileHandler(file_path)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    return file_path
