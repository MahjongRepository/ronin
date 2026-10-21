import pytest
from pydantic import ValidationError

from game.server.settings import GameServerSettings


class TestGameServerSettings:
    def test_cors_origins__when_json_array__should_parse_list(self, monkeypatch):
        monkeypatch.setenv("GAME_CORS_ORIGINS", '["http://a.com","http://b.com"]')
        settings = GameServerSettings()
        assert settings.cors_origins == ["http://a.com", "http://b.com"]

    def test_cors_origins__when_comma_separated__should_parse_list(self, monkeypatch):
        monkeypatch.setenv("GAME_CORS_ORIGINS", "http://a.com,http://b.com")
        settings = GameServerSettings()
        assert settings.cors_origins == ["http://a.com", "http://b.com"]

    def test_cors_origins__when_empty__should_raise_validation_error(self, monkeypatch):
        monkeypatch.setenv("GAME_CORS_ORIGINS", "")
        with pytest.raises(ValidationError, match="cors_origins"):
            GameServerSettings()

    @pytest.mark.parametrize("value", [0, -1])
    def test_max_capacity__when_non_positive__should_raise_validation_error(self, value):
        with pytest.raises(ValidationError, match="max_capacity"):
            GameServerSettings(max_capacity=value)

    def test_replay_dir__when_empty__should_raise_validation_error(self):
        with pytest.raises(ValidationError, match="replay_dir"):
            GameServerSettings(replay_dir="")

    def test_game_server_settings__when_deployment_values_unset__should_raise_for_each(self, monkeypatch):
        for name in ("GAME_CORS_ORIGINS", "GAME_REPLAY_DIR", "AUTH_DATABASE_PATH", "AUTH_GAME_TICKET_SECRET"):
            monkeypatch.delenv(name)

        with pytest.raises(ValidationError) as exc_info:
            GameServerSettings()

        missing = {error["loc"][0] for error in exc_info.value.errors() if error["type"] == "missing"}
        assert missing == {"cors_origins", "replay_dir", "AUTH_DATABASE_PATH", "AUTH_GAME_TICKET_SECRET"}

    def test_database_path__when_env_set__should_use_env_value(self, monkeypatch):
        monkeypatch.setenv("AUTH_DATABASE_PATH", "custom/auth.db")
        settings = GameServerSettings()
        assert settings.database_path == "custom/auth.db"
