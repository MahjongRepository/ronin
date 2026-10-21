from pathlib import Path

import pytest
from pydantic import ValidationError

from lobby.server.settings import LobbyServerSettings


class TestLobbyServerSettings:
    def test_lobby_server_settings__should_use_defaults_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("LOBBY_LOG_DIR", raising=False)
        monkeypatch.delenv("LOBBY_CORS_ORIGINS", raising=False)
        monkeypatch.delenv("LOBBY_CONFIG_PATH", raising=False)
        monkeypatch.delenv("LOBBY_GAME_CLIENT_URL", raising=False)
        monkeypatch.delenv("LOBBY_GAME_ASSETS_DIR", raising=False)
        settings = LobbyServerSettings()
        assert settings.log_dir == ""
        assert settings.cors_origins == []
        assert settings.config_path is None
        assert settings.game_client_url == "/play"
        assert settings.game_assets_dir == "frontend/dist"

    def test_lobby_server_settings__when_config_path_env_set__should_override_config_path(self, monkeypatch):
        monkeypatch.setenv("LOBBY_CONFIG_PATH", "/etc/servers.yaml")
        settings = LobbyServerSettings()
        assert settings.config_path == Path("/etc/servers.yaml")

    def test_lobby_server_settings__when_log_dir_env_set__should_override_log_dir(self, monkeypatch):
        monkeypatch.setenv("LOBBY_LOG_DIR", "custom/lobby-logs")
        settings = LobbyServerSettings()
        assert settings.log_dir == "custom/lobby-logs"

    def test_lobby_server_settings__when_cors_origins_json_array__should_parse_list(self, monkeypatch):
        monkeypatch.setenv("LOBBY_CORS_ORIGINS", '["http://x.com","http://y.com"]')
        settings = LobbyServerSettings()
        assert settings.cors_origins == ["http://x.com", "http://y.com"]

    def test_lobby_server_settings__when_cors_origins_csv__should_parse_list(self, monkeypatch):
        monkeypatch.setenv("LOBBY_CORS_ORIGINS", "http://x.com,http://y.com")
        settings = LobbyServerSettings()
        assert settings.cors_origins == ["http://x.com", "http://y.com"]

    def test_lobby_server_settings__when_cors_origins_empty__should_raise_validation_error(self, monkeypatch):
        monkeypatch.setenv("LOBBY_CORS_ORIGINS", "")
        with pytest.raises(ValidationError, match="cors_origins"):
            LobbyServerSettings()

    def test_lobby_server_settings__when_vite_dev_url_unset__should_be_empty(self, monkeypatch):
        monkeypatch.delenv("LOBBY_VITE_DEV_URL", raising=False)
        settings = LobbyServerSettings()
        assert settings.vite_dev_url == ""

    def test_lobby_server_settings__when_vite_dev_url_env_set__should_override_vite_dev_url(self, monkeypatch):
        monkeypatch.setenv("LOBBY_VITE_DEV_URL", "http://localhost:5173")
        settings = LobbyServerSettings()
        assert settings.vite_dev_url == "http://localhost:5173"
