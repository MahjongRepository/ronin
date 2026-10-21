from pathlib import Path

import pytest
from pydantic import ValidationError

from lobby.settings import LobbyServerSettings


class TestLobbyServerSettings:
    def test_lobby_server_settings__when_deployment_values_unset__should_raise_for_each(self, monkeypatch):
        for name in ("LOBBY_ALLOWED_HOSTS", "LOBBY_CONFIG_PATH", "LOBBY_REPLAY_DIR", "LOBBY_WS_ALLOWED_ORIGIN"):
            monkeypatch.delenv(name)
        with pytest.raises(ValidationError) as exc_info:
            LobbyServerSettings()
        missing = {error["loc"][0] for error in exc_info.value.errors() if error["type"] == "missing"}
        assert missing == {"allowed_hosts", "config_path", "replay_dir", "ws_allowed_origin"}

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
