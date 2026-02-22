import json
import logging
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from unittest.mock import patch

import pytest
import structlog

from shared.logging import _serialize_enums, rotate_log_file, setup_logging


@pytest.fixture(autouse=True)
def _cleanup_root_logger():
    """Close and remove all handlers from the root logger after each test."""
    yield
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
        root.removeHandler(handler)


@pytest.fixture(autouse=True)
def _allow_file_logging():
    """Disable the _is_test guard so logging tests can create real file handlers."""
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
        assert isinstance(handler.formatter, structlog.stdlib.ProcessorFormatter)

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

        test_logger = structlog.get_logger("test.writes_to_file")
        test_logger.info("hello from test")

        assert log_path is not None
        content = log_path.read_text()
        assert "hello from test" in content

    def test_creates_log_directory(self, tmp_path):
        log_dir = tmp_path / "nested" / "dir"
        log_path = setup_logging(log_dir=log_dir)

        test_logger = structlog.get_logger("test.creates_log_dir")
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

    def test_log_level_from_env(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "debug")
        setup_logging()
        root = logging.getLogger()

        assert root.level == logging.DEBUG

    def test_invalid_log_level_raises(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "bogus")
        with pytest.raises(ValueError, match="Invalid LOG_LEVEL"):
            setup_logging()

    def test_json_mode_produces_valid_json(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        log_path = setup_logging(log_dir=tmp_path / "game")

        structlog.contextvars.bind_contextvars(game_id="test-game")
        test_logger = structlog.get_logger("test.json")
        test_logger.info("json test event", extra_field="value")
        structlog.contextvars.clear_contextvars()

        assert log_path is not None
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) >= 1
        parsed = json.loads(lines[0])
        assert parsed["event"] == "json test event"
        assert parsed["game_id"] == "test-game"
        assert parsed["extra_field"] == "value"

    def test_console_mode_produces_readable_output(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "console")
        log_path = setup_logging(log_dir=tmp_path / "game")

        test_logger = structlog.get_logger("test.console")
        test_logger.info("console test event")

        assert log_path is not None
        content = log_path.read_text()
        assert "console test event" in content

    def test_invalid_log_format_raises(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "invalid_value")
        with pytest.raises(ValueError, match="Invalid LOG_FORMAT"):
            setup_logging()


class TestSerializeEnums:
    class _Color(Enum):
        RED = "red"
        BLUE = "blue"

    def test_replaces_enum_with_value(self):
        event_dict = {"action": self._Color.RED, "msg": "hello"}
        result = _serialize_enums(None, "", event_dict)
        assert result["action"] == "red"
        assert result["msg"] == "hello"

    def test_replaces_enum_inside_dict_value(self):
        event_dict = {"data": {"color": self._Color.BLUE, "count": 3}}
        result = _serialize_enums(None, "", event_dict)
        assert result["data"] == {"color": "blue", "count": 3}

    def test_leaves_non_enum_values_unchanged(self):
        event_dict = {"count": 42, "name": "test"}
        result = _serialize_enums(None, "", event_dict)
        assert result == {"count": 42, "name": "test"}


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
        test_logger = structlog.get_logger("test.rotate")
        test_logger.info("after rotation")

        assert "after rotation" in new_path.read_text()

    def test_rotate_with_custom_name(self, tmp_path):
        log_dir = tmp_path / "game"
        setup_logging(log_dir=log_dir)

        new_path = rotate_log_file(log_dir, name="my-game-id")
        assert new_path is not None
        assert new_path.name == "my-game-id.log"
