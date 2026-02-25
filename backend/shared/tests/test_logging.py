import json
import logging
from enum import Enum
from unittest.mock import patch

import pytest
import structlog

from shared.logging import _serialize_enums, setup_logging


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

    def test_clears_existing_handlers_on_repeated_calls(self):
        setup_logging()
        setup_logging()
        root = logging.getLogger()

        assert len(root.handlers) == 1

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
