from pathlib import Path

import pytest
from pydantic import ValidationError

from lobby.server.settings import LobbyServerSettings


class TestLobbyServerSettings:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("LOBBY_LOG_DIR", raising=False)
        monkeypatch.delenv("LOBBY_CORS_ORIGINS", raising=False)
        monkeypatch.delenv("LOBBY_CONFIG_PATH", raising=False)
        settings = LobbyServerSettings()
        assert settings.log_dir == "backend/logs/lobby"
        assert settings.cors_origins == ["http://localhost:8712"]
        assert settings.config_path is None

    def test_config_path_override(self, monkeypatch):
        monkeypatch.setenv("LOBBY_CONFIG_PATH", "/etc/servers.yaml")
        settings = LobbyServerSettings()
        assert settings.config_path == Path("/etc/servers.yaml")

    def test_log_dir_override(self, monkeypatch):
        monkeypatch.setenv("LOBBY_LOG_DIR", "custom/lobby-logs")
        settings = LobbyServerSettings()
        assert settings.log_dir == "custom/lobby-logs"

    def test_cors_origins_json_array(self, monkeypatch):
        monkeypatch.setenv("LOBBY_CORS_ORIGINS", '["http://x.com","http://y.com"]')
        settings = LobbyServerSettings()
        assert settings.cors_origins == ["http://x.com", "http://y.com"]

    def test_cors_origins_csv(self, monkeypatch):
        monkeypatch.setenv("LOBBY_CORS_ORIGINS", "http://x.com,http://y.com")
        settings = LobbyServerSettings()
        assert settings.cors_origins == ["http://x.com", "http://y.com"]

    def test_cors_origins_invalid_raises(self, monkeypatch):
        monkeypatch.setenv("LOBBY_CORS_ORIGINS", "")
        with pytest.raises(ValidationError, match="cors_origins"):
            LobbyServerSettings()
