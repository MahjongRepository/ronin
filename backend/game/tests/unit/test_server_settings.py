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

    def test_max_capacity_zero_rejected(self):
        with pytest.raises(ValidationError, match="max_capacity"):
            GameServerSettings(max_capacity=0)

    def test_max_capacity_negative_rejected(self):
        with pytest.raises(ValidationError, match="max_capacity"):
            GameServerSettings(max_capacity=-1)

    def test_log_dir_empty_rejected(self):
        with pytest.raises(ValidationError, match="log_dir"):
            GameServerSettings(log_dir="")

    def test_replay_dir_empty_rejected(self):
        with pytest.raises(ValidationError, match="replay_dir"):
            GameServerSettings(replay_dir="")

    def test_database_path_defaults(self, monkeypatch):
        monkeypatch.delenv("GAME_DATABASE_PATH", raising=False)
        monkeypatch.delenv("AUTH_DATABASE_PATH", raising=False)
        settings = GameServerSettings()
        assert settings.database_path == "backend/storage.db"

    def test_database_path_from_game_env(self, monkeypatch):
        monkeypatch.setenv("GAME_DATABASE_PATH", "custom/game.db")
        settings = GameServerSettings()
        assert settings.database_path == "custom/game.db"

    def test_database_path_from_auth_env(self, monkeypatch):
        monkeypatch.delenv("GAME_DATABASE_PATH", raising=False)
        monkeypatch.setenv("AUTH_DATABASE_PATH", "custom/auth.db")
        settings = GameServerSettings()
        assert settings.database_path == "custom/auth.db"
