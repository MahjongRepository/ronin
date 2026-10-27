import json
import logging
import logging.handlers
import warnings
from enum import Enum

import pytest
import structlog

from shared.logging import _serialize_enums, setup_logging


@pytest.fixture(autouse=True)
def _cleanup_root_logger():
    yield
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
        root.removeHandler(handler)
    logging.captureWarnings(capture=False)


class TestSetupLogging:
    def test_setup_logging__when_log_dir_given__should_write_app_log(self, tmp_path):
        log_path = setup_logging(log_dir=tmp_path / "game")

        test_logger = structlog.get_logger("test.writes_to_file")
        test_logger.info("hello from test")
        assert log_path is not None
        assert log_path.name == "app.log"
        content = log_path.read_text()
        assert "hello from test" in content

    def test_setup_logging__when_stdlib_logger_or_warnings_warn__should_write_level_and_logger(self, tmp_path):
        log_path = setup_logging(log_dir=tmp_path / "game")

        logging.getLogger("websockets.server").warning("stdlib warning")
        with warnings.catch_warnings():
            warnings.simplefilter("always")
            warnings.warn("coroutine was never awaited", RuntimeWarning, stacklevel=1)
        assert log_path is not None
        stdlib_line, warning_line, *_ = log_path.read_text().splitlines()
        assert stdlib_line.split(" ", 1)[1].split() == ["[warning", "]", "stdlib", "warning", "[websockets.server]"]
        assert "[warning  ]" in warning_line
        assert warning_line.endswith("RuntimeWarning: coroutine was never awaited")
        assert log_path.read_text().endswith(" [py.warnings]\n")

    def test_setup_logging__when_log_dir_missing__should_create_it(self, tmp_path):
        log_dir = tmp_path / "nested" / "dir"
        log_path = setup_logging(log_dir=log_dir)

        test_logger = structlog.get_logger("test.creates_log_dir")
        test_logger.info("nested log")
        assert log_dir.exists()
        assert log_path is not None
        assert log_path.name == "app.log"
        assert "nested log" in log_path.read_text()

    def test_setup_logging__when_log_dir_empty__should_skip_file_handler(self, tmp_path):
        log_path = setup_logging(log_dir="")
        root = logging.getLogger()
        assert log_path is None
        assert len(root.handlers) == 1  # stdout only
        assert not any(isinstance(h, logging.handlers.WatchedFileHandler) for h in root.handlers)

    def test_setup_logging__when_called_repeatedly__should_keep_single_handler(self):
        setup_logging()
        setup_logging()
        root = logging.getLogger()
        assert len(root.handlers) == 1

    def test_setup_logging__when_log_level_env_set__should_apply_level(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "debug")

        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_setup_logging__when_log_level_invalid__should_raise(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "bogus")
        with pytest.raises(ValueError, match="Invalid LOG_LEVEL"):
            setup_logging()

    def test_setup_logging__when_json_format__should_write_json_lines_with_context(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        log_path = setup_logging(log_dir=tmp_path / "game")

        structlog.contextvars.bind_contextvars(game_id="test-game")
        test_logger = structlog.get_logger("test.json")
        test_logger.info("json test event", extra_field="value")
        structlog.contextvars.clear_contextvars()
        assert log_path is not None
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["event"] == "json test event"
        assert parsed["game_id"] == "test-game"
        assert parsed["extra_field"] == "value"

    def test_setup_logging__when_log_format_invalid__should_raise(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "invalid_value")
        with pytest.raises(ValueError, match="Invalid LOG_FORMAT"):
            setup_logging()


class TestSerializeEnums:
    class _Color(Enum):
        RED = "red"
        BLUE = "blue"

    def test_serialize_enums__when_value_is_enum__should_replace_with_value(self):
        event_dict = {"action": self._Color.RED, "msg": "hello"}
        result = _serialize_enums(None, "", event_dict)
        assert result["action"] == "red"
        assert result["msg"] == "hello"

    def test_serialize_enums__when_enum_nested_in_dict__should_replace_with_value(self):
        event_dict = {"data": {"color": self._Color.BLUE, "count": 3}}
        result = _serialize_enums(None, "", event_dict)
        assert result["data"] == {"color": "blue", "count": 3}
