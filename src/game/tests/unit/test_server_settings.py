import pytest
from pydantic import ValidationError

from game.server.settings import GameServerSettings


class TestGameServerSettings:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("GAME_MAX_GAMES", raising=False)
        monkeypatch.delenv("GAME_LOG_DIR", raising=False)
        monkeypatch.delenv("GAME_CORS_ORIGINS", raising=False)
        monkeypatch.delenv("GAME_REPLAY_DIR", raising=False)
        settings = GameServerSettings()
        assert settings.max_games == 100
        assert settings.log_dir == "logs/game"
        assert settings.cors_origins == ["http://localhost:3000"]
        assert settings.replay_dir == "data/replays"

    def test_max_games_override(self, monkeypatch):
        monkeypatch.setenv("GAME_MAX_GAMES", "50")
        settings = GameServerSettings()
        assert settings.max_games == 50

    def test_log_dir_override(self, monkeypatch):
        monkeypatch.setenv("GAME_LOG_DIR", "custom/game-logs")
        settings = GameServerSettings()
        assert settings.log_dir == "custom/game-logs"

    def test_replay_dir_override(self, monkeypatch):
        monkeypatch.setenv("GAME_REPLAY_DIR", "custom/replays")
        settings = GameServerSettings()
        assert settings.replay_dir == "custom/replays"

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
