import pytest
from pydantic import ValidationError

from game.server.settings import GameServerSettings


class TestGameServerSettings:
    def test_cors_origins_json_array(self, monkeypatch):
        monkeypatch.setenv("GAME_CORS_ORIGINS", '["http://a.com","http://b.com"]')
        settings = GameServerSettings()
        assert settings.cors_origins == ["http://a.com", "http://b.com"]

    def test_cors_origins_csv(self, monkeypatch):
        monkeypatch.setenv("GAME_CORS_ORIGINS", "http://a.com,http://b.com")
        settings = GameServerSettings()
        assert settings.cors_origins == ["http://a.com", "http://b.com"]

    def test_cors_origins_invalid_raises(self, monkeypatch):
        monkeypatch.setenv("GAME_CORS_ORIGINS", "")
        with pytest.raises(ValidationError, match="cors_origins"):
            GameServerSettings()

    @pytest.mark.parametrize("value", [0, -1])
    def test_max_capacity_non_positive_rejected(self, value):
        with pytest.raises(ValidationError, match="max_capacity"):
            GameServerSettings(max_capacity=value)

    def test_replay_dir_empty_rejected(self):
        with pytest.raises(ValidationError, match="replay_dir"):
            GameServerSettings(replay_dir="")

    def test_database_path_defaults(self, monkeypatch):
        monkeypatch.delenv("AUTH_DATABASE_PATH", raising=False)
        settings = GameServerSettings()
        assert settings.database_path == "backend/storage.db"

    def test_database_path_from_env(self, monkeypatch):
        monkeypatch.setenv("AUTH_DATABASE_PATH", "custom/auth.db")
        settings = GameServerSettings()
        assert settings.database_path == "custom/auth.db"
