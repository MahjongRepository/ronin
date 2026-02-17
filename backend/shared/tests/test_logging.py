import logging
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from shared.logging import LOG_DATE_FORMAT, LOG_FORMAT, rotate_log_file, setup_logging


@pytest.fixture(autouse=True)
def _cleanup_root_logger():
    """
    Close and remove all handlers from the root logger after each test.

    Prevents file handlers from leaking across tests.
    """
    yield
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
        root.removeHandler(handler)


@pytest.fixture(autouse=True)
def _allow_file_logging():
    """
    Disable the _is_test guard so logging tests can create real file handlers.
    """
    with patch("shared.logging._is_test", return_value=False):
        yield


class TestSetupLogging:
    def test_configures_stdout_handler(self):
        setup_logging()
        root = logging.getLogger()

        assert root.level == logging.INFO
        assert len(root.handlers) == 1

        handler = root.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert handler.formatter is not None
        assert handler.formatter._fmt == LOG_FORMAT
        assert handler.formatter.datefmt == LOG_DATE_FORMAT

    def test_configures_file_handler_in_log_dir(self, tmp_path):
        log_dir = tmp_path / "game"
        setup_logging(log_dir=log_dir)
        root = logging.getLogger()

        assert len(root.handlers) == 2

        stream_handler = root.handlers[0]
        file_handler = root.handlers[1]
        assert isinstance(stream_handler, logging.StreamHandler)
        assert isinstance(file_handler, logging.FileHandler)
        assert Path(file_handler.baseFilename).parent == log_dir

    def test_log_file_has_datetime_in_name(self, tmp_path):
        fixed_time = datetime(2025, 3, 15, 10, 30, 45, tzinfo=UTC)
        with patch("shared.logging.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_time
            mock_dt.strftime = datetime.strftime
            log_path = setup_logging(log_dir=tmp_path / "game")

        expected_name = "2025-03-15_10-30-45.log"
        assert log_path is not None
        assert log_path.name == expected_name

    def test_returns_log_file_path(self, tmp_path):
        log_path = setup_logging(log_dir=tmp_path / "game")

        assert log_path is not None
        assert log_path.parent == tmp_path / "game"
        assert log_path.suffix == ".log"

    def test_returns_none_without_log_dir(self):
        result = setup_logging()

        assert result is None

    def test_writes_to_file(self, tmp_path):
        log_path = setup_logging(log_dir=tmp_path / "game")

        test_logger = logging.getLogger("test.writes_to_file")
        test_logger.info("hello from test")

        assert log_path is not None
        content = log_path.read_text()
        assert "hello from test" in content

    def test_creates_log_directory(self, tmp_path):
        log_dir = tmp_path / "nested" / "dir"
        log_path = setup_logging(log_dir=log_dir)

        test_logger = logging.getLogger("test.creates_log_dir")
        test_logger.info("nested log")

        assert log_dir.exists()
        assert log_path is not None
        assert "nested log" in log_path.read_text()

    def test_accepts_string_path(self, tmp_path):
        log_dir = str(tmp_path / "string_dir")
        setup_logging(log_dir=log_dir)
        root = logging.getLogger()

        file_handler = root.handlers[1]
        assert isinstance(file_handler, logging.FileHandler)

    def test_clears_existing_handlers_on_repeated_calls(self):
        setup_logging()
        setup_logging()
        root = logging.getLogger()

        assert len(root.handlers) == 1

    def test_custom_log_level(self):
        setup_logging(level=logging.DEBUG)
        root = logging.getLogger()

        assert root.level == logging.DEBUG


class TestRotateLogFile:
    def test_creates_new_log_file(self, tmp_path):
        log_dir = tmp_path / "game"
        setup_logging(log_dir=log_dir)

        new_path = rotate_log_file(log_dir)
        assert new_path is not None

        assert new_path.exists()
        assert new_path.parent == log_dir

    def test_replaces_file_handler(self, tmp_path):
        log_dir = tmp_path / "game"
        setup_logging(log_dir=log_dir)

        later_time = datetime(2099, 1, 1, 0, 0, 0, tzinfo=UTC)
        with patch("shared.logging.datetime") as mock_dt:
            mock_dt.now.return_value = later_time
            mock_dt.strftime = datetime.strftime
            new_path = rotate_log_file(log_dir)
        assert new_path is not None

        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        assert Path(file_handlers[0].baseFilename) == new_path
        assert new_path.name == "2099-01-01_00-00-00.log"

    def test_preserves_stdout_handler(self, tmp_path):
        log_dir = tmp_path / "game"
        setup_logging(log_dir=log_dir)

        rotate_log_file(log_dir)

        root = logging.getLogger()
        stream_handlers = [
            h for h in root.handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 1

    def test_writes_to_new_file(self, tmp_path):
        log_dir = tmp_path / "game"
        setup_logging(log_dir=log_dir)

        new_path = rotate_log_file(log_dir)
        assert new_path is not None
        test_logger = logging.getLogger("test.rotate")
        test_logger.info("after rotation")

        assert "after rotation" in new_path.read_text()
